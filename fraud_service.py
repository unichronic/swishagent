"""
Fraud Detection Service — Live Capture Verification

Uses lightweight, explainable signals:
- frame motion / similarity checks to catch static screens or loops
- perceptual hash reuse detection per user
- optional multimodal food/content verification
- behavioral risk from trust profile

Returns simple JSON with valid/invalid plus a brief reason.
"""

from __future__ import annotations

import io
import json
import os
import sqlite3
import time
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

import imagehash
import numpy as np
from fastapi import FastAPI, File, Form, UploadFile
from PIL import Image
from skimage.metrics import structural_similarity as skimage_ssim

from llm_client import call_gemini_multimodal, call_text
from tools import get_trust_score

app = FastAPI()

DB_PATH = os.getenv("FRAUD_DB_PATH", "/tmp/swish_fraud.db")
STATIC_SSIM_THRESHOLD = 0.97
STATIC_DIFF_THRESHOLD = 2.0
REUSE_HASH_DISTANCE_THRESHOLD = 5
ELA_HIGH_DIFF_THRESHOLD = 30.0   # raised from 18.0 — PNG→JPEG75 baseline is ~13.4, 30.0 gives safe margin
ELA_HOTSPOT_RATIO_THRESHOLD = 0.015
_last_prune_time = 0


def _get_db() -> sqlite3.Connection:
    global _last_prune_time
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS claim_frames (
            user_id TEXT, order_id TEXT, frame_hash TEXT, created_at INTEGER
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_claim_frames_user ON claim_frames(user_id)")
    conn.commit()
    now = int(time.time())
    if now - _last_prune_time > 3600:
        conn.execute("DELETE FROM claim_frames WHERE created_at < ?", (now - 90 * 86400,))
        conn.commit()
        _last_prune_time = now
    return conn


def _load_image(data: bytes) -> Image.Image:
    if len(data) > 5 * 1024 * 1024:  # 5MB cap
        raise ValueError("frame too large")
    image = Image.open(io.BytesIO(data))
    return image.convert("RGB")


def _to_gray_array(image: Image.Image, size: Tuple[int, int] = (128, 128)) -> np.ndarray:
    gray = image.convert("L").resize(size, Image.LANCZOS)
    return np.asarray(gray, dtype=np.float32)


def _ssim(arr1: np.ndarray, arr2: np.ndarray) -> float:
    """Correct SSIM using skimage's windowed implementation."""
    score, _ = skimage_ssim(arr1, arr2, full=True, data_range=255.0)
    return float(np.clip(score, 0.0, 1.0))


def _mean_abs_diff(arr1: np.ndarray, arr2: np.ndarray) -> float:
    return float(np.mean(np.abs(arr1 - arr2)))


def _dhash(image: Image.Image) -> str:
    """64-bit dHash using imagehash — always produces fixed 16-char hex string."""
    return str(imagehash.dhash(image, hash_size=8))


def _hamming_distance(hash_a: str, hash_b: str) -> int:
    if not hash_a or not hash_b:
        return 64
    return imagehash.hex_to_hash(hash_a) - imagehash.hex_to_hash(hash_b)


def _temporal_flags(images: List[Image.Image]) -> Dict[str, Any]:
    arrays = [_to_gray_array(img) for img in images]
    if len(arrays) < 2:
        return {"static_flag": False, "insufficient_frames": True, "ssim_0_2": None, "mean_diff": None}

    ssim_0_2 = _ssim(arrays[0], arrays[-1])
    diffs = [_mean_abs_diff(arrays[i], arrays[i + 1]) for i in range(len(arrays) - 1)]
    mean_diff = float(sum(diffs) / len(diffs))
    static_flag = ssim_0_2 >= STATIC_SSIM_THRESHOLD and mean_diff <= STATIC_DIFF_THRESHOLD
    return {
        "static_flag": static_flag,
        "insufficient_frames": False,
        "ssim_0_2": round(ssim_0_2, 4),
        "mean_diff": round(mean_diff, 3),
    }


def _reuse_flags(user_id: str, order_id: str, images: List[Image.Image]) -> Dict[str, Any]:
    hashes = [_dhash(img) for img in images]
    if not user_id:
        return {"reuse_flag": False, "hashes": hashes, "min_hash_distance": None}

    conn = _get_db()
    try:
        cutoff = int(time.time()) - 180 * 86400
        existing = [
            row[0]
            for row in conn.execute(
                "SELECT frame_hash FROM claim_frames WHERE user_id = ? AND order_id != ? AND created_at > ?",
                (user_id, order_id or "", cutoff),
            ).fetchall()
        ]
        min_distance = None
        reuse_flag = False
        for current_hash in hashes:
            for old_hash in existing:
                dist = _hamming_distance(current_hash, old_hash)
                if min_distance is None or dist < min_distance:
                    min_distance = dist
                if dist <= REUSE_HASH_DISTANCE_THRESHOLD:
                    reuse_flag = True
        return {
            "reuse_flag": reuse_flag,
            "hashes": hashes,
            "min_hash_distance": min_distance,
        }
    finally:
        conn.close()


def _persist_hashes(user_id: str, order_id: str, hashes: List[str]) -> None:
    if not user_id or not hashes:
        return
    conn = _get_db()
    try:
        now = int(time.time())
        conn.executemany(
            "INSERT INTO claim_frames (user_id, order_id, frame_hash, created_at) VALUES (?, ?, ?, ?)",
            [(user_id, order_id or "", frame_hash, now) for frame_hash in hashes],
        )
        conn.commit()
    finally:
        conn.close()


def _behavior_flag(user_id: str) -> Dict[str, Any]:
    if not user_id:
        return {"behavior_flag": False, "trust_score": None, "complaint_rate": None}
    try:
        trust = get_trust_score(user_id)
    except Exception:
        trust = {}
    score = float(trust.get("score", 50))
    total_orders = max(int(trust.get("total_orders", 0) or 0), 1)
    refund_requests = int(trust.get("refund_requests", 0) or 0)
    complaint_rate = refund_requests / total_orders
    behavior_flag = complaint_rate >= 0.3 and score < 60
    return {
        "behavior_flag": behavior_flag,
        "trust_score": score,
        "complaint_rate": round(complaint_rate, 3),
    }


@lru_cache(maxsize=256)
def _assess_visual_claim(complaint: str) -> Dict[str, Any]:
    text = (complaint or "").strip()
    if not text:
        return {"expected_visual_claim": "generic_food_evidence", "requires_food_evidence": False, "confidence": 0.0}

    # Pre-filter: complaints that are never visually verifiable — skip LLM entirely
    non_visual_keywords = ["cold", "hot", "temperature", "late", "delay", "price", "charge",
                           "spicy", "bland", "taste", "salty", "sweet", "bitter", "smell",
                           "portion", "quantity", "small", "less"]
    text_lower = text.lower()
    if any(kw in text_lower for kw in non_visual_keywords):
        # Check if there's also a visual signal (e.g. "cold AND wrong item")
        visual_keywords = ["wrong", "different", "insect", "hair", "foreign", "damaged", "broken",
                           "crushed", "spilled", "mold", "mould", "raw", "uncooked", "missing"]
        if not any(kw in text_lower for kw in visual_keywords):
            return {"expected_visual_claim": "generic_food_evidence", "requires_food_evidence": False, "confidence": 0.9}
    messages = [
        {
            "role": "system",
            "content": (
                "You classify food-delivery complaints for visual verification. "
                "Return JSON only. "
                'Use expected_visual_claim from ["damage_or_spill","wrong_item","missing_item","contamination_or_foreign_object","generic_food_evidence"]. '
                "Set requires_food_evidence=true only when an image or live capture would materially help verify the complaint. "
                "Use generic_food_evidence when the complaint is about food but does not map cleanly to a more specific visual class. "
                "Set confidence from 0 to 1."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Complaint: {text}\n"
                'Return JSON only with keys: expected_visual_claim, requires_food_evidence, confidence.'
            ),
        },
    ]
    try:
        raw = call_text(messages)
        start = raw.find("{")
        end = raw.rfind("}") + 1
        payload = json.loads(raw[start:end]) if start != -1 and end > 0 else {}
        expected = payload.get("expected_visual_claim")
        if expected not in {
            "damage_or_spill",
            "wrong_item",
            "missing_item",
            "contamination_or_foreign_object",
            "generic_food_evidence",
        }:
            expected = "generic_food_evidence"
        requires = payload.get("requires_food_evidence")
        confidence = payload.get("confidence")
        try:
            confidence = float(confidence)
        except Exception:
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))
        return {
            "expected_visual_claim": expected,
            "requires_food_evidence": bool(requires),
            "confidence": confidence,
        }
    except Exception:
        return {
            "expected_visual_claim": "generic_food_evidence",
            "requires_food_evidence": bool(text),
            "confidence": 0.0,
        }


def _ela_signal(image: Image.Image) -> Dict[str, Any]:
    original = image.convert("RGB")
    reencoded = io.BytesIO()
    try:
        original.save(reencoded, format="JPEG", quality=75)
    except Exception:
        return {"ela_flag": False, "ela_mean": 0.0, "ela_hotspot_ratio": 0.0, "ela_reason": "ELA unavailable"}
    recompressed = Image.open(io.BytesIO(reencoded.getvalue())).convert("RGB")

    diff = np.abs(np.asarray(original, dtype=np.float32) - np.asarray(recompressed, dtype=np.float32))
    ela_map = diff.mean(axis=2)
    ela_mean = float(ela_map.mean())
    ela_std = float(ela_map.std())
    threshold = ela_mean + (2.5 * ela_std)
    hotspot_ratio = float(np.mean(ela_map > threshold)) if threshold > 0 else 0.0
    ela_flag = ela_mean >= ELA_HIGH_DIFF_THRESHOLD and hotspot_ratio >= ELA_HOTSPOT_RATIO_THRESHOLD
    return {
        "ela_flag": ela_flag,
        "ela_mean": round(ela_mean, 3),
        "ela_hotspot_ratio": round(hotspot_ratio, 4),
        "ela_reason": "localized compression anomalies detected" if ela_flag else "no strong compression anomaly detected",
    }


def _content_check(image: Image.Image, complaint: str, claim_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    variance = float(np.asarray(image.convert("L")).var())
    if variance < 20:
        return {"content_flag": True, "content_reason": "frame content too flat or low-detail"}

    claim_info = claim_info or _assess_visual_claim(complaint)
    if not claim_info["requires_food_evidence"]:
        return {"content_flag": False, "content_reason": "content check skipped"}

    try:
        from google.genai import types as genai_types
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=85)
        expected_claim = claim_info["expected_visual_claim"]
        response = call_gemini_multimodal(
            [
                genai_types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg"),
                (
                    "You verify food-complaint evidence. Return JSON only: "
                    '{"shows_food": true/false, "relevant": true/false, "supports_claim": true/false, "notes": "brief"} . '
                    f"The expected claim type is {expected_claim}. "
                    "Relevant means the image plausibly shows food or packaging related to the complaint. "
                    "supports_claim should be true only if the visible evidence plausibly matches that complaint type."
                ),
            ]
        )
        text = response.text.strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        payload = json.loads(text[start:end]) if start != -1 and end > 0 else {}
        shows_food = bool(payload.get("shows_food"))
        relevant = bool(payload.get("relevant"))
        supports_claim = bool(payload.get("supports_claim"))
        return {
            "content_flag": not (shows_food and relevant and supports_claim),
            "content_reason": payload.get("notes", "content verification complete"),
        }
    except Exception as e:
        print(f"   ⚠️ content check unavailable: {e}")
        return {
            "content_flag": True,
            "content_reason": "content verification unavailable for a complaint that needs visual proof",
        }


def _score_result(
    temporal: Dict[str, Any],
    reuse: Dict[str, Any],
    ela: Dict[str, Any],
    content: Dict[str, Any],
    behavior: Dict[str, Any],
) -> Dict[str, Any]:
    flags: List[str] = []
    score = 0
    if temporal.get("insufficient_frames"):
        score += 30
        flags.append("insufficient_frames")
    elif temporal["static_flag"]:
        score += 50   # strong signal but not instant-reject alone
        flags.append("static_or_loop_capture")
    if reuse["reuse_flag"]:
        score += 40
        flags.append("reused_media")
    if ela["ela_flag"]:
        score += 20
        flags.append("compression_anomaly")
    if content["content_flag"]:
        score += 15
        flags.append("content_not_relevant")
    if behavior["behavior_flag"]:
        score += 10
        flags.append("behavioral_risk")

    # Bands: <40 valid, 40-59 borderline (reject with soft reason), >=60 clearly suspicious
    if score < 40:
        valid = True
        reason = "capture looks consistent enough to continue"
    elif score < 60:
        valid = False
        reason = "capture could not be verified confidently"
    else:
        valid = False
        reason = "capture looks suspicious and could not be verified"

    return {
        "valid": valid,
        "risk_score": score,
        "flags": flags,
        "reason": reason,
    }


async def _read_frames(frames: List[UploadFile]) -> List[Image.Image]:
    images: List[Image.Image] = []
    for frame in frames:
        data = await frame.read()
        if not data:
            continue
        images.append(_load_image(data))
    return images


@app.post("/verify-capture")
async def verify_capture(
    frames: List[UploadFile] = File(...),
    user_id: Optional[str] = Form(default=None),
    order_id: Optional[str] = Form(default=None),
    complaint: Optional[str] = Form(default=None),
):
    if not frames:
        return {"valid": False, "reason": "no frames received"}

    try:
        images = await _read_frames(frames)
    except Exception as exc:
        return {"valid": False, "reason": f"frame decode failed: {exc}"}

    if len(images) < 3:
        return {"valid": False, "reason": "need at least 3 frames to verify live capture"}

    temporal = _temporal_flags(images)
    reuse = _reuse_flags(user_id or "", order_id or "", images)
    claim_info = _assess_visual_claim(complaint or "")

    # ELA: run on all frames, take worst-case (highest ela_mean)
    ela_results = [_ela_signal(img) for img in images]
    ela = max(ela_results, key=lambda r: r["ela_mean"])

    # Content check: run on all frames, flag if any frame fails
    content_results = [_content_check(img, complaint or "", claim_info=claim_info) for img in images]
    content_flag = any(r["content_flag"] for r in content_results)
    content = {
        "content_flag": content_flag,
        "content_reason": next((r["content_reason"] for r in content_results if r["content_flag"]),
                               content_results[0]["content_reason"])
    }

    behavior = _behavior_flag(user_id or "")
    scored = _score_result(temporal, reuse, ela, content, behavior)

    if scored["valid"]:
        _persist_hashes(user_id or "", order_id or "", reuse["hashes"])

    return {"valid": scored["valid"], "reason": scored["reason"]}


@app.get("/health")
def health():
    return {"status": "ok"}
