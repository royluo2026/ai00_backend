"""Single-request bridge for governed Agent SSE streams.

The Capability provider opens an opaque channel and returns immediately.  The
web adapter claims that channel once and drives the original iterator, keeping
Gateway authorization ahead of the first emitted byte without buffering the
whole response in the Gateway call.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
import uuid
from typing import Any, AsyncIterator


@dataclass
class _Channel:
    iterator: Any
    media_type: str


_CHANNELS: dict[str, _Channel] = {}
_LOCK = Lock()


async def open_channel(iterator: Any, media_type: str) -> str:
    stream_id = f"agent-stream-{uuid.uuid4().hex}"
    with _LOCK:
        _CHANNELS[stream_id] = _Channel(iterator=iterator, media_type=media_type)
    return stream_id


async def claim_channel(stream_id: str) -> tuple[AsyncIterator[str | bytes], str]:
    with _LOCK:
        channel = _CHANNELS.pop(stream_id, None)
    if channel is None:
        raise ValueError("Agent stream is missing or already claimed")

    async def bounded() -> AsyncIterator[str | bytes]:
        count = 0
        iterator = channel.iterator
        try:
            async for chunk in iterator:
                count += 1
                if count > 500:
                    raise ValueError("stream response exceeds 500 events")
                yield chunk
        finally:
            closer = getattr(iterator, "aclose", None)
            if closer is not None:
                await closer()

    return bounded(), channel.media_type


def reset_channels() -> None:
    """Test-only reset for process-local, unclaimed channels."""
    with _LOCK:
        _CHANNELS.clear()


__all__ = ["claim_channel", "open_channel", "reset_channels"]
