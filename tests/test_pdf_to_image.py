"""/pdf-to-image renders one page at a time to disk and builds the ZIP in a temp file."""
import asyncio
import io
import os
import tempfile
import threading
import time
import zipfile

import httpx
import pytest
from PIL import Image

from app.services.pdf_to_image import service as pdf_service

PAGE_COLORS = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]


@pytest.fixture
def fake_poppler(monkeypatch):
    """Stand-in for pdfinfo/pdftoppm: writes one PPM per call, like pdf2image with output_folder."""
    calls = []
    written = []

    def fake_pdfinfo(pdf_path, **kwargs):
        assert os.path.exists(pdf_path)
        return {"Pages": len(PAGE_COLORS)}

    def fake_convert(pdf_path, output_folder=None, first_page=None, last_page=None, paths_only=False, **kwargs):
        calls.append((first_page, last_page))
        assert paths_only and output_folder
        # The previous page must already be removed from disk.
        assert not [p for p in written if os.path.exists(p)]
        path = os.path.join(output_folder, f"page-{first_page}.ppm")
        Image.new("RGB", (40, 30), PAGE_COLORS[first_page - 1]).save(path)
        written.append(path)
        return [path]

    monkeypatch.setattr(pdf_service, "pdfinfo_from_path", fake_pdfinfo)
    monkeypatch.setattr(pdf_service, "convert_from_path", fake_convert)
    return calls, written


@pytest.fixture
def temp_files(monkeypatch):
    created = []
    real = tempfile.TemporaryFile

    def tracking(*args, **kwargs):
        f = real(*args, **kwargs)
        created.append(f)
        return f

    monkeypatch.setattr(pdf_service.tempfile, "TemporaryFile", tracking)
    return created


def _assert_pages(zip_bytes):
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        assert zf.namelist() == ["page_1.png", "page_2.png", "page_3.png"]
        for name, color in zip(zf.namelist(), PAGE_COLORS):
            with Image.open(io.BytesIO(zf.read(name))) as img:
                assert img.format == "PNG"
                assert img.getpixel((0, 0)) == color


def test_converts_one_page_at_a_time_into_a_zip_on_disk(fake_poppler, temp_files):
    calls, written = fake_poppler

    result = pdf_service.PDFToImageService.convert_pdf_to_images(b"%PDF-1.4", "png")

    assert calls == [(1, 1), (2, 2), (3, 3)]
    assert written and not any(os.path.exists(p) for p in written)
    assert result["page_count"] == 3
    assert result["content"] is temp_files[0]
    assert not isinstance(result["content"], io.BytesIO)
    _assert_pages(result["content"].read())
    result["content"].close()


def test_endpoint_streams_the_zip_and_closes_the_temp_file(fake_poppler, temp_files):
    from main import app

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/pdf-to-image/convert/", files={"file": ("a.pdf", b"%PDF-1.4", "application/pdf")}
            )

    response = asyncio.run(scenario())

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    _assert_pages(response.content)
    assert len(temp_files) == 1 and temp_files[0].closed


def test_endpoint_runs_at_most_the_configured_number_of_conversions(monkeypatch):
    from main import app
    from app.services.pdf_to_image import router as pdf_router

    lock = threading.Lock()
    running = {"now": 0, "max": 0}

    def slow_convert(self, pdf_bytes, format="png"):
        with lock:
            running["now"] += 1
            running["max"] = max(running["max"], running["now"])
        time.sleep(0.3)
        with lock:
            running["now"] -= 1
        return {"content": io.BytesIO(b"zip"), "media_type": "application/zip", "filename": "converted_images.zip"}

    monkeypatch.setattr(pdf_service.PDFToImageService, "convert_pdf_to_images", slow_convert)
    monkeypatch.setattr(pdf_router, "CONVERSION_SLOTS", asyncio.Semaphore(2))

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await asyncio.gather(*[
                client.post("/pdf-to-image/convert/", files={"file": ("a.pdf", b"%PDF-1.4", "application/pdf")})
                for _ in range(6)
            ])

    responses = asyncio.run(scenario())

    assert all(r.status_code == 200 for r in responses)
    assert running["max"] == 2


def test_release_memory_is_safe_on_any_platform():
    from app.memory import release_memory

    release_memory()


def test_temp_file_is_closed_when_conversion_fails(monkeypatch, temp_files):
    monkeypatch.setattr(pdf_service, "pdfinfo_from_path", lambda *a, **k: {"Pages": 2})

    def broken_convert(*args, **kwargs):
        raise RuntimeError("pdftoppm crashed")

    monkeypatch.setattr(pdf_service, "convert_from_path", broken_convert)

    with pytest.raises(Exception, match="pdftoppm crashed"):
        pdf_service.PDFToImageService.convert_pdf_to_images(b"%PDF-1.4", "png")
    assert len(temp_files) == 1 and temp_files[0].closed
