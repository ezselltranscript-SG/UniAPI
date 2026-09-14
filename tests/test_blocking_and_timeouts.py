"""Blocking work must not freeze the API, and AI calls must have a timeout."""
import asyncio
import io
import sys
import threading
import time
import types
import zipfile

import httpx
import pytest

from app import concurrency
from app.config import AI_MAX_RETRIES, AI_REQUEST_TIMEOUT_SECONDS


def test_run_blocking_runs_calls_in_parallel_without_a_lock():
    async def scenario():
        start = time.perf_counter()
        await asyncio.gather(*[concurrency.run_blocking(time.sleep, 0.3) for _ in range(3)])
        return time.perf_counter() - start

    assert asyncio.run(scenario()) < 0.8


def test_run_blocking_serializes_calls_that_share_a_lock():
    lock = threading.Lock()

    async def scenario():
        start = time.perf_counter()
        await asyncio.gather(
            *[concurrency.run_blocking(time.sleep, 0.2, serialize_with=lock) for _ in range(3)]
        )
        return time.perf_counter() - start

    assert asyncio.run(scenario()) >= 0.6


def test_slow_conversion_does_not_block_other_requests(monkeypatch):
    from main import app
    from app.services.pdf_to_image import service as pdf_service

    def slow_convert(self, pdf_bytes, format="png"):
        time.sleep(1.0)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("page_1.png", b"x")
        buf.seek(0)
        return {"content": buf, "media_type": "application/zip", "filename": "converted_images.zip"}

    monkeypatch.setattr(pdf_service.PDFToImageService, "convert_pdf_to_images", slow_convert)

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            async def convert():
                return await client.post(
                    "/pdf-to-image/convert/", files={"file": ("a.pdf", b"%PDF-1.4", "application/pdf")}
                )

            async def health():
                await asyncio.sleep(0.2)
                t = time.perf_counter()
                r = await client.get("/pdf-to-image/health")
                return r, time.perf_counter() - t

            results = await asyncio.gather(convert(), convert(), convert(), health())
            return results

    *converts, (health_response, health_seconds) = asyncio.run(scenario())
    assert all(r.status_code == 200 for r in converts)
    assert health_response.status_code == 200
    assert health_seconds < 0.5  # before the change it waited for every conversion


def test_word_normalizer_ai_clients_get_timeout_and_retry_limit(monkeypatch):
    from app.services.word_normalizer import service

    seen = {}

    class FakeAnthropic:
        def __init__(self, **kwargs):
            seen.update(kwargs)
            self.messages = types.SimpleNamespace(create=self._create)

        def _create(self, **_):
            return types.SimpleNamespace(content=[types.SimpleNamespace(text="[]")])

    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=FakeAnthropic))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    matches = [{"id": 0, "short_form": "Aug", "expansion": "August", "notes": "", "context": "Aug 3"}]
    service._ai_context_decisions("Aug 3", matches)

    assert seen["timeout"] == AI_REQUEST_TIMEOUT_SECONDS == 60.0
    assert seen["max_retries"] == AI_MAX_RETRIES
