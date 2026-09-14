"""Run blocking work off the event loop.

Every endpoint here is `async def`, but the actual work (pdf2image/poppler,
PIL, OpenCV, Tesseract, LibreOffice, sync Anthropic/OpenAI calls) is
blocking. Called directly, one slow request froze the whole API -- every
other client's crop, conversion and health check waited behind it. Routers
now hand that work to Starlette's thread pool with ``run_blocking``.

Two tools are not safe to run concurrently, so their calls share a lock:
they still leave the event loop free, but run one at a time among themselves
(which is how they effectively ran before):
- PyMuPDF (fitz) does not support multithreading and can crash the process.
- Headless LibreOffice runs share one user profile; a second concurrent
  `libreoffice --convert-to` exits without converting.
"""
from __future__ import annotations

import threading
from typing import Any, Callable, Optional

from fastapi.concurrency import run_in_threadpool

PYMUPDF_LOCK = threading.Lock()
LIBREOFFICE_LOCK = threading.Lock()


def _call_locked(lock: threading.Lock, func: Callable[..., Any], args: tuple, kwargs: dict) -> Any:
    with lock:
        return func(*args, **kwargs)


async def run_blocking(
    func: Callable[..., Any],
    *args: Any,
    serialize_with: Optional[threading.Lock] = None,
    **kwargs: Any,
) -> Any:
    """Await ``func(*args, **kwargs)`` in the thread pool.

    Pass ``serialize_with`` for tools that must not run concurrently.
    """
    if serialize_with is None:
        return await run_in_threadpool(func, *args, **kwargs)
    return await run_in_threadpool(_call_locked, serialize_with, func, args, kwargs)
