import json
import logging
import os
import threading
from typing import Any, Callable, Optional

import redis


logger = logging.getLogger("swish.session_store")

SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "3600"))
REDIS_ADDR = os.getenv("REDIS_ADDR", "localhost:6379")
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
SESSION_STORE_PREFIX = os.getenv("SESSION_STORE_PREFIX", "swish:support")


def _parse_redis_addr(addr: str) -> tuple[str, int]:
    if "://" in addr:
        raise ValueError("REDIS_ADDR should be host:port")
    host, _, port = addr.partition(":")
    return host or "localhost", int(port or "6379")


class PersistentList(list):
    def __init__(self, values: list[dict[str, str]], save_callback: Callable[[], None]):
        super().__init__(values)
        self._save_callback = save_callback

    def append(self, value):
        super().append(value)
        self._save_callback()

    def extend(self, values):
        super().extend(values)
        self._save_callback()

    def insert(self, index, value):
        super().insert(index, value)
        self._save_callback()

    def pop(self, index=-1):
        value = super().pop(index)
        self._save_callback()
        return value

    def clear(self):
        super().clear()
        self._save_callback()

    def remove(self, value):
        super().remove(value)
        self._save_callback()

    def __setitem__(self, index, value):
        super().__setitem__(index, value)
        self._save_callback()

    def __delitem__(self, index):
        super().__delitem__(index)
        self._save_callback()


class PersistentDict(dict):
    def __init__(self, values: dict[str, Any], save_callback: Callable[[], None]):
        super().__init__(values)
        self._save_callback = save_callback

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self._save_callback()

    def __delitem__(self, key):
        super().__delitem__(key)
        self._save_callback()

    def clear(self):
        super().clear()
        self._save_callback()

    def pop(self, key, default=None):
        value = super().pop(key, default)
        self._save_callback()
        return value

    def setdefault(self, key, default=None):
        if key not in self:
            super().__setitem__(key, default)
            self._save_callback()
        return super().get(key)

    def update(self, *args, **kwargs):
        super().update(*args, **kwargs)
        self._save_callback()


class SessionStore:
    def __init__(self):
        self._lock = threading.RLock()
        self._redis: Optional[redis.Redis] = None
        self._redis_checked = False
        self._redis_failed = False
        self._history_cache: dict[str, PersistentList] = {}
        self._meta_cache: dict[str, PersistentDict] = {}

    def _history_key(self, session_id: str) -> str:
        return f"{SESSION_STORE_PREFIX}:history:{session_id}"

    def _meta_key(self, session_id: str) -> str:
        return f"{SESSION_STORE_PREFIX}:meta:{session_id}"

    def _get_redis(self) -> Optional[redis.Redis]:
        if self._redis_checked:
            return self._redis
        self._redis_checked = True
        try:
            host, port = _parse_redis_addr(REDIS_ADDR)
            client = redis.Redis(
                host=host,
                port=port,
                db=REDIS_DB,
                decode_responses=True,
                socket_connect_timeout=0.5,
                socket_timeout=0.5,
            )
            client.ping()
            self._redis = client
            self._redis_failed = False
        except Exception as exc:
            self._redis = None
            if not self._redis_failed:
                logger.warning("session_store_redis_unavailable error=%s", exc)
                self._redis_failed = True
        return self._redis

    def _save_history(self, session_id: str) -> None:
        history = self._history_cache.get(session_id)
        if history is None:
            return
        client = self._get_redis()
        if not client:
            return
        try:
            client.setex(self._history_key(session_id), SESSION_TTL_SECONDS, json.dumps(list(history), ensure_ascii=True))
        except Exception as exc:
            logger.warning("session_store_history_save_failed session_id=%s error=%s", session_id, exc)

    def _save_meta(self, session_id: str) -> None:
        meta = self._meta_cache.get(session_id)
        if meta is None:
            return
        client = self._get_redis()
        if not client:
            return
        try:
            client.setex(self._meta_key(session_id), SESSION_TTL_SECONDS, json.dumps(dict(meta), ensure_ascii=True))
        except Exception as exc:
            logger.warning("session_store_meta_save_failed session_id=%s error=%s", session_id, exc)

    def _load_json(self, key: str, default: Any) -> Any:
        client = self._get_redis()
        if not client:
            return default
        try:
            payload = client.get(key)
            if not payload:
                return default
            return json.loads(payload)
        except Exception as exc:
            logger.warning("session_store_load_failed key=%s error=%s", key, exc)
            return default

    def _touch(self, session_id: str) -> None:
        client = self._get_redis()
        if not client:
            return
        try:
            client.expire(self._history_key(session_id), SESSION_TTL_SECONDS)
            client.expire(self._meta_key(session_id), SESSION_TTL_SECONDS)
        except Exception as exc:
            logger.warning("session_store_touch_failed session_id=%s error=%s", session_id, exc)

    def get_session(self, session_id: str) -> PersistentList:
        with self._lock:
            history = self._history_cache.get(session_id)
            if history is None:
                loaded = self._load_json(self._history_key(session_id), [])
                history = PersistentList(loaded if isinstance(loaded, list) else [], lambda: self._save_history(session_id))
                self._history_cache[session_id] = history
            self._touch(session_id)
            return history

    def get_state(self, session_id: Optional[str]) -> dict[str, Any]:
        if not session_id:
            return {}
        with self._lock:
            meta = self._meta_cache.get(session_id)
            if meta is None:
                loaded = self._load_json(
                    self._meta_key(session_id),
                    {
                        "pending": None,
                        "desired_resolution": None,
                        "coupon_amount": None,
                        "photo_provided": False,
                        "coupon_push_count": 0,
                    },
                )
                if not isinstance(loaded, dict):
                    loaded = {}
                merged = {
                    "pending": None,
                    "desired_resolution": None,
                    "coupon_amount": None,
                    "photo_provided": False,
                    "coupon_push_count": 0,
                }
                merged.update(loaded)
                meta = PersistentDict(merged, lambda: self._save_meta(session_id))
                self._meta_cache[session_id] = meta
            self._touch(session_id)
            return meta

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._history_cache.pop(session_id, None)
            self._meta_cache.pop(session_id, None)
            client = self._get_redis()
            if not client:
                return
            try:
                client.delete(self._history_key(session_id), self._meta_key(session_id))
            except Exception as exc:
                logger.warning("session_store_clear_failed session_id=%s error=%s", session_id, exc)

    def mark_photo_provided(self, session_id: str) -> None:
        meta = self.get_state(session_id)
        meta["photo_provided"] = True

    def session_has_photo(self, session_id: str) -> bool:
        return bool(self.get_state(session_id).get("photo_provided"))


store = SessionStore()
