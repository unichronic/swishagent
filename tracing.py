import json
import logging
import os
import time
import uuid
from contextlib import contextmanager, nullcontext
from typing import Any


TRACE_ENABLED = os.getenv("TRACE_ENABLED", "1") != "0"
LANGFUSE_ENABLED = os.getenv("LANGFUSE_ENABLED", "1") != "0"
_LANGFUSE_CLIENT = None
_LANGFUSE_AVAILABLE: bool | None = None


class NoopObservation:
    def update(self, **_fields: Any) -> None:
        return None

    def set_trace_io(self, **_fields: Any) -> None:
        return None


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]


def trace_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    if not TRACE_ENABLED:
        return
    payload = {
        "ts_ms": int(time.time() * 1000),
        "event": event,
    }
    for key, value in fields.items():
        if value is None:
            continue
        payload[key] = value
    logger.info(json.dumps(payload, ensure_ascii=True, sort_keys=True, default=str))


def _get_langfuse_client():
    global _LANGFUSE_AVAILABLE, _LANGFUSE_CLIENT
    if not LANGFUSE_ENABLED:
        return None
    if not (os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")):
        return None
    if _LANGFUSE_AVAILABLE is False:
        return None
    if _LANGFUSE_CLIENT is not None:
        return _LANGFUSE_CLIENT
    try:
        from langfuse import get_client

        _LANGFUSE_CLIENT = get_client()
        _LANGFUSE_AVAILABLE = True
        return _LANGFUSE_CLIENT
    except Exception:
        _LANGFUSE_AVAILABLE = False
        return None


@contextmanager
def langfuse_attributes(
    *,
    user_id: str | None = None,
    session_id: str | None = None,
    trace_name: str | None = None,
    metadata: dict[str, Any] | None = None,
    tags: list[str] | None = None,
):
    if _get_langfuse_client() is None:
        yield
        return
    try:
        from langfuse import propagate_attributes

        with propagate_attributes(
            user_id=user_id,
            session_id=session_id,
            trace_name=trace_name,
            metadata=metadata,
            tags=tags,
        ):
            yield
    except Exception:
        yield


@contextmanager
def langfuse_observation(
    name: str,
    *,
    as_type: str = "span",
    input: Any = None,
    metadata: dict[str, Any] | None = None,
    output: Any = None,
    model: str | None = None,
    trace_id_seed: str | None = None,
):
    client = _get_langfuse_client()
    if client is None:
        yield NoopObservation()
        return

    kwargs: dict[str, Any] = {
        "as_type": as_type,
        "name": name,
    }
    if input is not None:
        kwargs["input"] = input
    if metadata is not None:
        kwargs["metadata"] = metadata
    if model is not None:
        kwargs["model"] = model
    if trace_id_seed:
        try:
            kwargs["trace_context"] = {"trace_id": client.create_trace_id(seed=trace_id_seed)}
        except Exception:
            pass

    try:
        observation_context = client.start_as_current_observation(**kwargs)
    except Exception:
        observation_context = nullcontext(NoopObservation())

    with observation_context as observation:
        try:
            yield observation
            if output is not None:
                observation.update(output=output)
        except Exception as exc:
            try:
                observation.update(level="ERROR", status_message=str(exc))
            except Exception:
                pass
            raise


def flush_langfuse() -> None:
    client = _get_langfuse_client()
    if client is None:
        return
    try:
        client.flush()
    except Exception:
        pass
