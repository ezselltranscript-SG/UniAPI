"""Give freed memory back to the OS after big image work.

glibc keeps memory freed by worker threads in per-thread arenas instead of
returning it, so after a batch of PDF conversions the process sat at ~1.1 GB
while idle and every later batch started with less headroom. The Dockerfile
caps the arenas (MALLOC_ARENA_MAX); ``release_memory`` trims what is left.
"""
from __future__ import annotations

import ctypes
import ctypes.util

try:
    _libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6")
    _malloc_trim = _libc.malloc_trim
except (OSError, AttributeError):  # not glibc (Windows, macOS, musl)
    _malloc_trim = None


def release_memory() -> None:
    """Return free heap memory to the OS. No-op where malloc_trim is unavailable."""
    if _malloc_trim is not None:
        _malloc_trim(0)
