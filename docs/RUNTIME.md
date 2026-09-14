# UniAPI runtime: concurrency, retries, fallbacks, PDF conversion, configuration

Reference for developers and coding agents. Covers how requests run in parallel, which calls retry and how
long they may take, what each service does when something fails, how `/pdf-to-image` works, and every
setting and module-level variable that changes behavior.

Last verified against code: 2026-09-10. Endpoint usage below comes from the live n8n workflows at that
date. For the n8n workflows and the hub that call this API, see
`handwritten-transcription-hub/docs/runtime-behavior.md`.

---

## 1. Who calls what

Base URL in production: `https://uniapi-fjla.onrender.com`. No authentication (see Linear LTS-68).

| Endpoint | Called by (n8n) | n8n node settings |
| --- | --- | --- |
| `POST /pdf-to-image/convert/` | Diary worker `r2E3lN6xl54HIV8p`; Die Botschaft `RyPnxVYs5cMQuic1`, `3OrBVmwnCuyXW7RJ`; The Budget `ZSSJGm4H61nruIkz` | Diary: 3 tries, 5 s apart, 300 s timeout |
| `POST /word-normalizer/normalize/` | Diary worker; Die Botschaft and Budget letter workflows | Diary: 3 tries, 5 s apart, 120 s timeout; others 4 tries |
| `POST /fixed-image-cropper/crop-fixed/`, `/fixed-image-cropper-nt/crop-fixed/` | Die Botschaft | 4 tries |
| `POST /fixed-image-cropper-the-budget/crop-fixed-the-budget/`, `…-t2/crop-fixed-the-budget-t2/` | The Budget | 4 tries |
| `POST /template-checker/detect`, `/template-checker-the-budget/detect` | Die Botschaft, The Budget | 4 tries |
| `POST /shower-cropper/crop-shower/`, `/crop-obituaries/` | Ivverich & Ender | 4 tries |
| `POST /pdf-pair-splitter/split-pairs/` | Die Botschaft `3OrBVmwnCuyXW7RJ` | no retry |
| file merger, word-to-pdf | Document Merger workflows | — |

DOCX generation ("Generate Doc" nodes) is a different service, `thebudgetgenerateletter.onrender.com`.

---

## 2. Concurrency

### 2.1 Process and event loop

* Render starts `uvicorn main:app` with no `--workers` flag, so the worker count comes from
  `WEB_CONCURRENCY` (uvicorn's default), which is 1 unless set. Each extra worker is a separate process
  with its own memory and its own copy of every module-level variable (6.2). Raise it only if the Render
  plan has the RAM.
* Every endpoint is `async def`. Their real work (poppler/pdf2image, PIL, OpenCV, Tesseract,
  LibreOffice, sync Anthropic/OpenAI clients) is blocking, so it **must not** run on the event loop.
  Until 2026-09-10 it did, and one slow request froze the whole API: in a local test with 5 concurrent
  conversions, a health check waited 7.8 s; now it answers in 0.01 s.

### 2.2 `app/concurrency.py`

All routers call their service through `run_blocking`, which runs it in Starlette's thread pool
(default 40 threads):

```python
from app.concurrency import run_blocking, PYMUPDF_LOCK

result = await run_blocking(Service.method, arg, key=value)                          # parallel
result = await run_blocking(Service.method, arg, serialize_with=PYMUPDF_LOCK)        # one at a time
```

Rules for new endpoints:

1. Read the upload with `await file.read()` on the loop, then pass the bytes to `run_blocking`.
2. Never call a service method directly from an `async def` handler.
3. If the service uses PyMuPDF (`fitz`) or LibreOffice, pass the matching lock.

### 2.3 Locks

| Lock | Why | Endpoints |
| --- | --- | --- |
| `PYMUPDF_LOCK` | PyMuPDF does not support multithreading and can crash the process | `/anchored-pdf-cropper`, `/pdf-chunk-margin-cropper`, `/pdf-normalizer` |
| `LIBREOFFICE_LOCK` | concurrent headless `libreoffice --convert-to` runs share one user profile; the second exits without converting | `/column-merger` (both endpoints), `/word-to-pdf` |

Locked endpoints still leave the event loop free; they only queue behind each other. Note that
`/pdf-normalizer` holds `PYMUPDF_LOCK` during its vision calls, so two normalizations run one after the
other.

### 2.4 What this does and does not speed up

* Fixed: requests from different clients no longer wait for each other, and health checks stay fast.
* Not fixed: CPU-bound work still competes for the same CPU. Five PDF conversions at once take about as
  long in total as before (local test: 25.6 s → 22.7 s on 2 cores). The real lever for conversions is
  the output format (section 5).

---

## 3. Retries and timeouts

### 3.1 AI calls

Set in `app/config.py`, read once at import:

| Variable | Default | Applies to |
| --- | --- | --- |
| `AI_REQUEST_TIMEOUT_SECONDS` | `60` | each AI request attempt |
| `AI_MAX_RETRIES` | `3` | SDK retries per provider after the first attempt (so up to 4 attempts) |

Used by:

* `word_normalizer/service.py`: `anthropic.Anthropic(...)` (model `claude-haiku-4-5-20251001`) and the
  fallback `openai.OpenAI(...)` (`gpt-4o-mini`).
* `pdf_normalizer/vision.py`: `openai.OpenAI(...)`, model from `PDF_NORMALIZER_VISION_MODEL`
  (default `gpt-5.6-terra`).

The SDKs retry on connection errors, timeouts, 429 and 5xx, with backoff.

**Worst case per word-normalizer call.** The service makes up to 2 AI calls (date, then body), and each
can try Anthropic then OpenAI. That is 60 s × 4 attempts × 2 providers per text block, about 8 minutes,
and up to about 16 minutes for date + body. n8n's `Format Checker` gives up after 120 s and retries, while
the UniAPI thread keeps running. If that shows up in n8n, lower `AI_MAX_RETRIES` in Render (0 = the
fallback provider acts as the only retry; worst case about 2 minutes per block).

### 3.2 Other outbound calls

| Call | Timeout | Retry |
| --- | --- | --- |
| Word normalizer: `Normalization_Words_List` from Supabase REST (`urllib`) | 10 s | tries 2 column sets, no retry; failure means "no rules" |
| PDF conversion (`pdftoppm` subprocess) | none | none (n8n retries the request) |
| LibreOffice conversion (`subprocess.run`) | none | none |

---

## 4. Fallbacks

| Situation | Behavior |
| --- | --- |
| Word normalizer: no `ANTHROPIC_API_KEY` | uses OpenAI |
| Word normalizer: Anthropic call fails | logs and falls back to OpenAI |
| Word normalizer: no AI key, or both providers fail | every rule match is expanded (no context check); request still succeeds |
| Word normalizer: `SUPABASE_URL`/`SUPABASE_KEY` missing or Supabase unreachable | no rules loaded; text returned unchanged |
| Word normalizer: rules fetched recently | served from the per-process cache for 300 s |
| PDF normalizer: `OPENAI_API_KEY` missing, or vision call fails, with vision review on | HTTP 503 with the reason; `review_mode=heuristic` skips vision on purpose |
| Anchored PDF cropper: page rendering | pdf2image/poppler (using `POPPLER_PATH` if set); if that fails, PyMuPDF |
| Word to PDF on Windows (local dev only) | `docx2pdf` (needs Word), then LibreOffice. Running in a worker thread, the Word/COM path may fail and fall back to LibreOffice. Production (Linux) always uses LibreOffice |
| Template checker: image does not decode with OpenCV | decodes with PIL; defaults to template `1` when no box is found |
| Any service exception | router returns HTTP 500 with the message; n8n's per-node retry takes over |

---

## 5. PDF conversion (`/pdf-to-image/convert/`)

Files: `app/services/pdf_to_image/router.py`, `service.py` (CRLF line endings).

* Input: multipart `file` (must end in `.pdf`), query `format` = `png` (default), `jpeg` or `jpg`.
* Rendering: `pdf2image.convert_from_bytes(pdf_bytes)`, which runs poppler's `pdftoppm` at the library
  default of **200 DPI**. Every page is held in memory.
* Output: **always a ZIP** (`converted_images.zip`), entries `page_1.png`, `page_2.png`, … The router
  docstring says a single page returns a bare image; it does not.
* JPEG uses PIL's default quality (75) today; `format=jpeg` is accepted but no workflow uses it.
* Cost, 2-page handwritten-style scan (local benchmark):

| Setting | Time | Output |
| --- | --- | --- |
| 200 DPI PNG (today) | 1.9 s | 6.0 MB |
| 150 DPI PNG | 1.2 s | 3.4 MB |
| 200 DPI JPEG q85 | 0.3 s | 1.1 MB |
| 150 DPI JPEG q85 | 0.2 s | 0.6 MB |

  Rendering takes about 0.3 s; the rest is PNG compression. On Render, with several letters at once, the
  same conversion took 34–40 s (Diary run 2026-09-08).
* Downstream expectations: n8n unzips the entries, sorts them by the number in the name, and uploads them
  to Supabase Storage with `Content-Type: image/png`. The croppers keep the input format.
* Planned change (Linear LTS-83, not started): optional `dpi` and `jpeg_quality` query params with defaults
  that reproduce today's output, then `?format=jpeg` per workflow after an A/B on ~20 letters.

Other endpoints that render PDFs: `/pdf-chunk-margin-cropper` (`dpi` query, default 250, PyMuPDF),
`/pdf-normalizer` (PyMuPDF), `/ocr/pdf` (pdf2image at 200 DPI, then Tesseract).

---

## 6. Configuration and global variables

### 6.1 Environment variables

| Variable | Default | Read in | Effect |
| --- | --- | --- | --- |
| `AI_REQUEST_TIMEOUT_SECONDS` | `60` | `app/config.py` | AI request timeout (3.1) |
| `AI_MAX_RETRIES` | `3` | `app/config.py` | AI SDK retries (3.1) |
| `ANTHROPIC_API_KEY` | — | `word_normalizer/service.py` | enables Anthropic |
| `OPENAI_API_KEY` | — | `word_normalizer/service.py`, `pdf_normalizer/vision.py` | enables OpenAI |
| `PDF_NORMALIZER_VISION_MODEL` | `gpt-5.6-terra` | `pdf_normalizer/vision.py` | vision model |
| `SUPABASE_URL`, `SUPABASE_KEY` | `""` | `app/config.py` (client), `word_normalizer/service.py` (REST) | normalization rules and other lookups |
| `POPPLER_PATH` | — | `anchored_pdf_cropper/service.py` | poppler binaries location |
| `CORS_ORIGINS` | `*` | `app/config.py` | CORS |
| `API_HOST`, `API_PORT`, `API_RELOAD` | `0.0.0.0`, `8000`, `True` | `app/config.py` | only for `python main.py`; Render uses its own start command |
| `WEB_CONCURRENCY` | `1` | uvicorn | worker processes (2.1) |

Values in `app/config.py` and module constants are read once at startup. Change the variable in Render
and redeploy/restart for it to apply.

### 6.2 Module-level state

| Name | File | What it holds | Notes |
| --- | --- | --- | --- |
| `PYMUPDF_LOCK`, `LIBREOFFICE_LOCK` | `app/concurrency.py` | `threading.Lock` | per process; with 2 workers, two conversions of each kind can run at once (one per process) |
| `supabase` | `app/config.py` | Supabase client, or `None` if not configured | created at import |
| `DOWNLOADS_DIR` | `app/config.py` | `<repo>/downloads`, created at import | the docx-generator, file-merger, pdf-splitter, pair/chunk/custom splitter and word-to-pdf routers copy results here and **never delete them** (disk grows until the Render instance is replaced) |
| `_NORM_CACHE`, `_NORM_TTL_SECONDS` (300) | `word_normalizer/service.py` | normalization rules per client | per process; concurrent misses may fetch twice (harmless) |
| `DEFAULT_MODEL` | `pdf_normalizer/vision.py` | `gpt-5.6-terra` | overridden by `PDF_NORMALIZER_VISION_MODEL` |

### 6.3 Deployment files

* `Dockerfile`: `python:3.9-slim` with LibreOffice, poppler, Tesseract (spa, eng), MS core fonts. Start
  command `uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}`.
* `render.yaml`: declares a native Python 3.9 service without those system packages, and documents
  `WEB_CONCURRENCY`. If the live service is Docker-based, this file is out of date.

---

## 7. Tests

`python -m pytest tests -q`: 20 tests.

* `tests/test_pdf_normalizer.py` (16): PDF normalizer behavior.
* `tests/test_blocking_and_timeouts.py` (4):
  * `run_blocking` runs in parallel without a lock and serializes with one.
  * A slow conversion does not delay a health check.
  * The word normalizer's AI client gets the configured timeout and retry count.
