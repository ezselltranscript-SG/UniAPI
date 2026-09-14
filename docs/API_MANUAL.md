# Unified Document Services API — Integration Manual

This is the implementation-level reference for the API currently registered in
`main.py`. It is intended as source material for a customer-facing user guide:
it describes the purpose and boundary of every service, request fields, response
types, and copy-ready examples.

> **Important route note:** four routers define their own prefix *and* are
> mounted with the same prefix. Their production routes intentionally appear
> duplicated in this document: `/ocr/ocr/...`,
> `/image-to-pdf/image-to-pdf/...`,
> `/pdf-text-extractor/pdf-text-extractor/...`, and
> `/text-correction/text-correction/...`.

## 1. API conventions

### Base URL and interactive reference

Use the deployment URL as `BASE_URL`; for local development the default is
`http://localhost:8000`.

```bash
BASE_URL=http://localhost:8000
curl "$BASE_URL/"
```

The live Swagger UI is `GET /docs` and the OpenAPI description is normally
available at `GET /openapi.json` when the FastAPI server is running.

### Authentication, authorization, and scope

The application does **not** currently implement an API key, OAuth, user roles,
or endpoint-level permissions. Any network client that can reach the service can
call every endpoint. CORS is configured through `CORS_ORIGINS` (defaults to
`*`). Put the API behind an authenticated gateway or private network before
exposing documents containing sensitive information.

In this manual, **scope** means the job an endpoint is designed to perform and
its deliberate boundaries; it is not an access-control scope.

### Request formats

- Endpoints accepting files use `multipart/form-data`. In `curl`, send each
  file with `-F 'field=@path/to/file'`.
- JSON endpoints use `Content-Type: application/json` and `-d '...json...'`.
- Query options belong in the URL, for example `?format=jpeg`.
- Most processing endpoints return a downloaded binary file. Save it with
  `--output`; use `--remote-header-name` to honor the server filename.

```bash
# Generic binary-download pattern
curl --fail --remote-header-name \
  -F 'file=@./input.pdf;type=application/pdf' \
  "$BASE_URL/example" --output output.bin
```

### Status and error shape

Successful calls return `200 OK`. Validation and input errors normally return
`400`, FastAPI validation failures return `422`, service failures return
`500`, and vision-review availability errors from PDF Normalizer return `503`.

Representative JSON error:

```json
{"detail":"File must be a PDF"}
```

File-producing responses set `Content-Disposition: attachment; filename=...`.
Do not try to parse those response bodies as JSON. A `GET /health` endpoint,
where present, is a lightweight readiness check and returns a JSON status object.

## 2. Service catalogue

| Area | Primary endpoint(s) | Scope and primary output |
| --- | --- | --- |
| PDF splitting | `/pdf-splitter/split/`, `/pdf-pair-splitter/split-pairs/`, `/pdf-custom-splitter/split-custom/`, `/pdf-chunk-splitter/split-chunks/` | Break a PDF into page files or fixed-size page groups; ZIP download. |
| PDF processing | `/pdf-normalizer/normalize/`, `/pdf-chunk-margin-cropper/process/`, `/anchored-pdf-cropper/crop/` | Correct scans or crop content; PDF or ZIP download. |
| PDF conversion/extraction | `/pdf-to-image/convert/`, `/pdf-text-extractor/pdf-text-extractor/*`, `/ocr/ocr/pdf/` | Convert PDF pages, extract embedded text, or OCR scanned text. |
| Image processing | `/image-cropper/crop/`, fixed cropper variants, shower cropper, template checkers | Split or crop layout-specific images, or classify a template. |
| Image/PDF generation | `/image-to-pdf/image-to-pdf/*`, `/docx-generator/generate/` | Create a PDF from images or a DOCX from structured text. |
| Word/document workflow | `/word-to-pdf/convert/`, `/column-merger/*`, `/file-merger/merge/`, `/word-normalizer/normalize/` | Convert or merge Word/PDF files, or expand approved abbreviations. |
| Text processing | `/ocr/ocr/image/`, `/text-correction/text-correction/correct` | OCR an image or fuzzy-correct town/city names. |

## 3. Discovery and health endpoints

- `GET /` returns the registered service list and the relative documentation URL.
- The following informational endpoints return short service-specific descriptions
  (they do not process a file):

  | Route | Route | Route |
  | --- | --- | --- |
  | `GET /pdf-splitter/` | `GET /pdf-pair-splitter/` | `GET /pdf-custom-splitter/` |
  | `GET /pdf-chunk-splitter/` | `GET /pdf-chunk-margin-cropper/` | `GET /pdf-normalizer/` |
  | `GET /pdf-to-image/` | `GET /image-cropper/` | `GET /fixed-image-cropper/` |
  | `GET /fixed-image-cropper-nt/` | `GET /fixed-image-cropper-the-budget/` | `GET /fixed-image-cropper-the-budget-t2/` |
  | `GET /shower-cropper/` | `GET /word-to-pdf/` | `GET /file-merger/` |
  | `GET /column-merger/` | `GET /docx-generator/` | `GET /anchored-pdf-cropper/` |
  | `GET /template-checker/` | `GET /template-checker-the-budget/` | `GET /word-normalizer/` |

  OCR, Image-to-PDF, PDF Text Extractor, and Text Correction do not implement a
  service-root `GET` operation.
- The following exact health routes are available:

  | Service | Health route |
  | --- | --- |
  | PDF Pair Splitter | `GET /pdf-pair-splitter/health` |
  | PDF Custom Splitter | `GET /pdf-custom-splitter/health` |
  | PDF Chunk Splitter | `GET /pdf-chunk-splitter/health` |
  | Image Cropper | `GET /image-cropper/health` |
  | Fixed Image Cropper | `GET /fixed-image-cropper/health` |
  | Fixed Image Cropper NT | `GET /fixed-image-cropper-nt/health` |
  | Fixed Image Cropper The Budget | `GET /fixed-image-cropper-the-budget/health` |
  | Fixed Image Cropper The Budget T2 | `GET /fixed-image-cropper-the-budget-t2/health` |
  | Word to PDF | `GET /word-to-pdf/health` |
  | File Merger | `GET /file-merger/health` |
  | PDF to Image | `GET /pdf-to-image/health` |
  | Shower Cropper | `GET /shower-cropper/health` |
  | Column Merger | `GET /column-merger/health` |
  | PDF Normalizer | `GET /pdf-normalizer/health` |

Typical health response:

```json
{"status":"OK","service":"PDF Pair Splitter"}
```

Health response capitalization and the optional `service` field differ by
service; callers should check the HTTP status rather than depend on an exact
body.

## 4. PDF splitting APIs

All four endpoints require a `.pdf` filename and return `application/zip`.
They do not OCR, re-order, or alter page content.

### PDF Splitter — one PDF per page

`POST /pdf-splitter/split/`

**Scope:** split every source page into an individual PDF. Use it when later
workflow stages work one page at a time.

| Multipart field | Required | Description |
| --- | --- | --- |
| `pdf_file` | Yes | Source PDF. The filename must end in lowercase `.pdf`. |

```bash
curl --fail --remote-header-name \
  -F 'pdf_file=@./letters.pdf;type=application/pdf' \
  "$BASE_URL/pdf-splitter/split/" --output letters.zip
```

**Response:** ZIP, usually named `letters.zip`, containing files such as
`letters-Part1.pdf`, `letters-Part2.pdf`.

### PDF Pair Splitter — two pages per file

`POST /pdf-pair-splitter/split-pairs/`

**Scope:** group pages as sequential front/back pairs. A final odd page is
returned as the last (one-page) part; no blank page is inserted.

| Multipart field | Required | Description |
| --- | --- | --- |
| `pdf_file` | Yes | Source PDF. |

```bash
curl --fail --remote-header-name -F 'pdf_file=@./mail.pdf' \
  "$BASE_URL/pdf-pair-splitter/split-pairs/" --output mail.zip
```

**Response:** ZIP with names similar to `mail_Part1.pdf` (pages 1–2) and
`mail_Part2.pdf` (pages 3–4).

### PDF Custom Splitter — form-controlled group size

`POST /pdf-custom-splitter/split-custom/`

**Scope:** split by any positive number of consecutive pages. This endpoint
uses a multipart **form** field, not a query parameter.

| Multipart field | Required | Default | Description |
| --- | --- | --- | --- |
| `pdf_file` | Yes | — | Source PDF. |
| `pages_per_file` | No | `3` | Positive number of pages in each output file. |

```bash
curl --fail --remote-header-name \
  -F 'pdf_file=@./bulletin.pdf' -F 'pages_per_file=4' \
  "$BASE_URL/pdf-custom-splitter/split-custom/" --output bulletin.zip
```

**Response:** ZIP with names such as `bulletin_Group1_Pages1-4.pdf`.

### PDF Chunk Splitter — query-controlled group size

`POST /pdf-chunk-splitter/split-chunks/?chunk_size=2`

**Scope:** same fixed-size grouping concept as Custom Splitter, but exposes the
size as a query parameter. Use it when the client can set URL parameters more
easily than multipart fields.

| Input | Required | Default | Rules |
| --- | --- | --- | --- |
| multipart `pdf_file` | Yes | — | Source PDF. |
| query `chunk_size` | No | `2` | Integer at least `1`. |

```bash
curl --fail --remote-header-name -F 'pdf_file=@./batch.pdf' \
  "$BASE_URL/pdf-chunk-splitter/split-chunks/?chunk_size=5" \
  --output batch.zip
```

**Response:** ZIP of consecutive N-page PDFs.

## 5. PDF cleanup and crop APIs

### PDF Normalizer

`POST /pdf-normalizer/normalize/`

**Scope:** prepare scanned multi-letter PDFs for downstream front/back-letter
workflows. It reviews page orientation and letter boundaries, can rotate pages,
and inserts black reverse-side pages only after letters with an odd page count.
It is not a general OCR or layout-redesign service.

| Input | Required | Default | Description |
| --- | --- | --- | --- |
| multipart `file` | Yes | — | Source PDF. |
| query `auto_rotate` | No | `true` | Apply reviewed rotation corrections. |
| query `ensure_page_pairs` | No | `true` | Insert reviewed black missing-side pages. |
| query `review_mode` | No | `vision` | `vision` uses the configured vision model; `heuristic` is explicit non-LLM fallback. |
| query `vision_model` | No | configured model | Optional model override for vision review. |

```bash
curl --fail --remote-header-name -D normalizer-headers.txt \
  -F 'file=@./scanned_letters.pdf;type=application/pdf' \
  "$BASE_URL/pdf-normalizer/normalize/?auto_rotate=true&ensure_page_pairs=true&review_mode=vision" \
  --output scanned_letters_normalized.pdf
```

**Response:** `application/pdf`. Important response headers include:

| Header | Meaning |
| --- | --- |
| `X-Input-Pages`, `X-Output-Pages` | Page counts before and after processing. |
| `X-Rotated-Pages`, `X-Applied-Rotations` | Number and list of rotations, e.g. `2:90,5:180`. |
| `X-Blank-Pages-Added`, `X-Blank-After-Source-Pages` | Count and positions of black pages inserted. |
| `X-Letter-Start-Pages` | Detected 1-based letter starts. |
| `X-Review-Mode`, `X-Review-Model` | Review strategy and model used. |

Vision mode requires `OPENAI_API_KEY`; a review problem is returned as `503`.
The vision review supports PDFs up to 80 pages.

### PDF Chunk Margin Cropper

`POST /pdf-chunk-margin-cropper/process/`

**Scope:** process a PDF in repeated chunks. The first page of each chunk is
kept; other pages are cropped to their detected text area (`crop`) or marked for
inspection (`mark`). It returns one PDF, not a ZIP.

| Input | Required | Default | Rules |
| --- | --- | --- | --- |
| multipart `file` | Yes | — | Source PDF. |
| query `chunk_size` | No | `2` | Integer >= 1. |
| query `dpi` | No | `250` | Render DPI from 72 to 400. |
| query `mode` | No | `crop` | Either `crop` or `mark`. |
| query `debug` | No | `false` | Enables server-side diagnostic logging. |

```bash
curl --fail --remote-header-name -F 'file=@./forms.pdf' \
  "$BASE_URL/pdf-chunk-margin-cropper/process/?chunk_size=3&dpi=250&mode=crop" \
  --output forms_cropped.pdf
```

**Response:** `application/pdf`, filename `<source>_cropped.pdf`.

### Anchored PDF Cropper

`POST /anchored-pdf-cropper/crop/`

**Scope:** automatically locate a known visual/text anchor and crop its target
panel in one or more PDFs. Keywords and crop settings are internal service
defaults; this endpoint deliberately has no tuning parameters.

| Multipart field | Required | Description |
| --- | --- | --- |
| `files` | Yes | One or more PDF uploads. Repeat the field for each input. |

```bash
curl --fail --remote-header-name \
  -F 'files=@./letter-001.pdf' -F 'files=@./letter-002.pdf' \
  "$BASE_URL/anchored-pdf-cropper/crop/" --output cropped_panels.zip
```

**Response:** `application/zip` containing the automatic crop results.

## 6. PDF conversion, extraction, and OCR

### PDF to Image

`POST /pdf-to-image/convert/?format=png`

**Scope:** render each PDF page to an image; it does not extract text.

| Input | Required | Default | Allowed values |
| --- | --- | --- | --- |
| multipart `file` | Yes | — | PDF. |
| query `format` | No | `png` | `png`, `jpeg`, or `jpg`. |

```bash
curl --fail --remote-header-name -F 'file=@./proof.pdf' \
  "$BASE_URL/pdf-to-image/convert/?format=jpeg" --output proof-images.bin
```

**Response:** a direct image for a one-page PDF, otherwise a ZIP of page images.
Inspect `Content-Type`/ `Content-Disposition` rather than assuming a ZIP.

### PDF Text Extractor

**Scope:** extract an existing PDF text layer using PDFMiner. It does not OCR
scanned/image-only pages; use OCR PDF for those documents.

#### Basic text — `POST /pdf-text-extractor/pdf-text-extractor/extract/`

| Input | Required | Default | Description |
| --- | --- | --- | --- |
| multipart `file` | Yes | — | PDF with a text layer. |
| query `by_page` | No | `false` | Return `page_1`, `page_2`, etc. plus `full_text`. |

```bash
curl --fail -F 'file=@./digital.pdf;type=application/pdf' \
  "$BASE_URL/pdf-text-extractor/pdf-text-extractor/extract/?by_page=true"
```

Example response (`by_page=true`):

```json
{
  "page_1": "First page text\n",
  "page_2": "Second page text\n",
  "full_text": "First page text\n\nSecond page text\n"
}
```

With `by_page=false`, the response is `{"text":"..."}`.

#### Text plus metadata — `POST /pdf-text-extractor/pdf-text-extractor/extract-with-metadata/`

```bash
curl --fail -F 'file=@./digital.pdf;type=application/pdf' \
  "$BASE_URL/pdf-text-extractor/pdf-text-extractor/extract-with-metadata/"
```

Example response:

```json
{
  "page_1": "First page text\n",
  "full_text": "First page text\n",
  "metadata": {"num_pages": 1, "word_count": 3, "character_count": 16}
}
```

#### Download-style text — `POST /pdf-text-extractor/pdf-text-extractor/extract-to-file/?format=txt`

Only `txt` is accepted. Despite its attachment header, the endpoint currently
returns JSON rather than raw text bytes:

```json
{"text":"Extracted document text"}
```

### OCR

**Scope:** recognize text from images or scanned PDFs. The default Tesseract
language is Spanish (`spa`); installed language packs determine what values are
available (for example, `eng`). OCR accuracy depends on scan quality.

#### Image OCR — `POST /ocr/ocr/image/?lang=spa`

```bash
curl --fail -F 'file=@./scan.jpg;type=image/jpeg' \
  "$BASE_URL/ocr/ocr/image/?lang=eng"
```

Response:

```json
{"text":"Recognized text from the image"}
```

#### PDF OCR — `POST /ocr/ocr/pdf/?lang=spa&pages_only=false`

| Input | Required | Default | Description |
| --- | --- | --- | --- |
| multipart `file` | Yes | — | PDF to OCR. |
| query `lang` | No | `spa` | OCR language code. |
| query `pages_only` | No | `false` | Omit the combined `full_text` field when true. |

```bash
curl --fail -F 'file=@./scanned.pdf;type=application/pdf' \
  "$BASE_URL/ocr/ocr/pdf/?lang=spa&pages_only=true"
```

Representative response:

```json
{
  "page_1": "Text recognized on page 1",
  "page_2": "Text recognized on page 2",
  "full_text": "Text recognized on page 1\nText recognized on page 2"
}
```

`pages_only=true` returns the `page_1`, `page_2`, etc. fields without
`full_text`.

## 7. Image crop and template APIs

### Flexible Image Cropper

`POST /image-cropper/crop/`

**Scope:** divide one PNG/JPG image into a top header and a bottom body. The
API does not choose a semantic content region; it divides at a supplied position.

| Multipart field | Required | Default | Rules |
| --- | --- | --- | --- |
| `file` | Yes | — | PNG or JPEG/JPG image. |
| `split_point` | No | — | Non-negative pixel position from the top. |
| `split_percentage` | No | — | Fraction from `0.0` to `1.0` of image height. |

If neither split field is supplied, the split is at 50%. If both are supplied,
send only the value you intend to control the split; clients should not depend
on an undocumented precedence rule.

```bash
curl --fail --remote-header-name \
  -F 'file=@./form.jpg;type=image/jpeg' -F 'split_percentage=0.30' \
  "$BASE_URL/image-cropper/crop/" --output form_parts.zip
```

**Response:** `application/zip` with header/body image files.

### Fixed Image Croppers

All endpoints below accept `multipart/form-data` field `image_file` (PNG, JPG,
or JPEG) and return an `application/zip` with header/body crops. They are
template-specific, fixed-layout operations—not general configurable croppers.

| Endpoint | Scope |
| --- | --- |
| `POST /fixed-image-cropper/crop-fixed/` | Standard fixed crop. Header is 12%–30% of image height; body is 31%–100%. |
| `POST /fixed-image-cropper-nt/crop-fixed/` | NT variant; documented dimensions are the same 12%–30% / 31%–100%. |
| `POST /fixed-image-cropper-the-budget/crop-fixed-the-budget/` | The Budget layout; trims borders then creates fixed header/body crops. |
| `POST /fixed-image-cropper-the-budget-t2/crop-fixed-the-budget-t2/` | The Budget T2 layout; trims borders then creates fixed header/body crops. |

```bash
curl --fail --remote-header-name -F 'image_file=@./budget.jpg' \
  "$BASE_URL/fixed-image-cropper-the-budget/crop-fixed-the-budget/" \
  --output budget_parts.zip
```

### Shower Cropper

**Scope:** crop a single fixed vertical area where form content normally appears.
It is designed for known form layouts and returns a one-image ZIP.

| Endpoint | Crop scope | Required field |
| --- | --- | --- |
| `POST /shower-cropper/crop-shower/` | Shower form content region, approximately 32.5%–87.5% of height. | `image_file` |
| `POST /shower-cropper/crop-obituaries/` | Obituary content region, approximately 25%–81% of height. | `image_file` |

```bash
curl --fail --remote-header-name -F 'image_file=@./obituary.png' \
  "$BASE_URL/shower-cropper/crop-obituaries/" --output obituary_area.zip
```

### Template Checkers

**Scope:** inspect an image header and classify it as template `"1"` or `"2"`.
These are classifiers only; they do not crop or transform the image.

| Endpoint | Layout family | Required multipart field |
| --- | --- | --- |
| `POST /template-checker/detect` | Standard templates | `image_file` |
| `POST /template-checker-the-budget/detect` | The Budget templates | `image_file` |

```bash
curl --fail -F 'image_file=@./header.png;type=image/png' \
  "$BASE_URL/template-checker/detect"
```

Example response:

```json
{"template_id":"1","reason":"Matched the expected header pattern"}
```

`reason` is diagnostic and may vary. Treat `template_id` as a string with the
currently supported values `"1"` and `"2"`.

## 8. Document conversion and merging APIs

### Image to PDF

**Scope:** lay out one or several images in a PDF. This is an image conversion
operation, not an OCR operation.

| Endpoint | Required file field | Output |
| --- | --- | --- |
| `POST /image-to-pdf/image-to-pdf/convert/?page_size=A4` | `file` | One-page PDF, named after the image. |
| `POST /image-to-pdf/image-to-pdf/convert-multiple/?page_size=A4` | repeat `files` | One multi-page PDF, named `combined_images.pdf`. |

`page_size` defaults to `A4`; use `letter` for Letter-sized output.

```bash
curl --fail --remote-header-name \
  -F 'files=@./page1.png' -F 'files=@./page2.jpg' \
  "$BASE_URL/image-to-pdf/image-to-pdf/convert-multiple/?page_size=letter" \
  --output combined_images.pdf
```

### Word to PDF

`POST /word-to-pdf/convert/`

**Scope:** convert `.docx` or `.doc` to PDF. This service also removes existing
headers, standardizes fonts to Times New Roman 10pt, and adds its customized
headers; do not use it when an untouched Word-to-PDF rendering is required.

| Multipart field | Required | Description |
| --- | --- | --- |
| `file` | Yes | `.docx` or `.doc` Word document. |

```bash
curl --fail --remote-header-name -F 'file=@./letter.docx' \
  "$BASE_URL/word-to-pdf/convert/" --output letter.pdf
```

**Response:** `application/pdf` attachment.

### Column Merger

#### Merge archive — `POST /column-merger/merge-columns/`

**Scope:** merge Word documents packaged in an archive while preserving source
document format. Files are sorted by `partX` in their filenames when present.

| Multipart field | Required | Default | Description |
| --- | --- | --- | --- |
| `file` | Yes | — | Compressed archive containing Word documents. |
| `output_filename` | No | `merged_document` | Output basename; the service adds `.docx`. |

```bash
curl --fail --remote-header-name \
  -F 'file=@./parts.zip;type=application/zip' \
  -F 'output_filename=June_notices' \
  "$BASE_URL/column-merger/merge-columns/" --output June_notices.docx
```

**Response:** merged DOCX download.

#### Preserve-format conversion — `POST /column-merger/word-to-pdf/`

**Scope:** convert Word to PDF without the header/font transformations of the
separate Word to PDF service.

```bash
curl --fail --remote-header-name -F 'file=@./original.docx' \
  "$BASE_URL/column-merger/word-to-pdf/" --output original.pdf
```

**Response:** PDF attachment.

### File Merger

`POST /file-merger/merge/`

**Scope:** unpack an archive and merge PDF files or DOCX files into one output.
All source documents in an archive should be the same type. Files with `partX`
in their name are sorted by that part number.

| Multipart field | Required | Default | Description |
| --- | --- | --- | --- |
| `file` | One upload required | — | Preferred archive field. |
| `data` or `archive` | Alternative | — | Accepted aliases for integrations using a different field name. |
| `output_filename` | No | `merged_document` | Output basename. |

```bash
curl --fail --remote-header-name -F 'archive=@./pdf_parts.zip' \
  -F 'output_filename=complete_packet' \
  "$BASE_URL/file-merger/merge/" --output complete_packet.pdf
```

**Response:** attachment with a PDF or DOCX content type matching the archive
contents.

### DOCX Generator

`POST /docx-generator/generate/?as_base64=false`

**Scope:** create a simple DOCX from city, author, date, and body content. It is
a basic title/body template generator, not a generic DOCX-template merge API.

JSON request:

```json
{
  "city": "Bogotá",
  "authorName": "Ana Pérez",
  "date": "2026-08-31",
  "body": "Dear customer,\n\nYour request has been processed.",
  "documentName": "customer-letter.docx"
}
```

```bash
curl --fail --remote-header-name \
  -H 'Content-Type: application/json' \
  -d '{"city":"Bogotá","authorName":"Ana Pérez","date":"2026-08-31","body":"Hello","documentName":"customer-letter.docx"}' \
  "$BASE_URL/docx-generator/generate/" --output customer-letter.docx
```

With `as_base64=false` (default), the response is a DOCX attachment. With
`as_base64=true`, it returns JSON:

```json
{
  "success": true,
  "binary": {
    "data": {
      "data": "UEsDB...",
      "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "fileName": "customer-letter.docx"
    }
  }
}
```

Decode `binary.data.data` as base64 to obtain the `.docx` bytes.

## 9. Text processing APIs

### Text Correction

`POST /text-correction/text-correction/correct`

**Scope:** fuzzy-match and correct city/town names in supplied text using the
configured Supabase `towns` data. It does not perform general grammar or style
correction. The service requires `SUPABASE_URL` and `SUPABASE_KEY` to be
configured.

| JSON field | Required | Default | Description |
| --- | --- | --- | --- |
| `text` | Yes | — | Text to inspect. |
| `threshold` | No | `85` | Similarity threshold from 0 to 100; higher is more conservative. |

```bash
curl --fail -H 'Content-Type: application/json' \
  -d '{"text":"The service is in Medelin.","threshold":85}' \
  "$BASE_URL/text-correction/text-correction/correct"
```

Response:

```json
{"corrected_text":"The service is in Medellín."}
```

### Word Normalizer

`POST /word-normalizer/normalize/`

**Scope:** expand short forms in a letter date and body according to
client-specific rules from `Normalization_Words_List`. It returns the normalized
text plus a base64 DOCX audit report. It is not a general spell checker.

| JSON field | Required | Description |
| --- | --- | --- |
| `date` | Yes | Letter date, also subject to normalization. |
| `body` | Yes | Letter body. |
| `client` | Yes | Client name used to select rules. |

```bash
curl --fail -H 'Content-Type: application/json' \
  -d '{"date":"Jan. 15, 2024","body":"The pt was adm to the hosp.","client":"ExampleClient"}' \
  "$BASE_URL/word-normalizer/normalize/"
```

Example response:

```json
{
  "date": "January 15, 2024",
  "body": "The patient was admitted to the hospital.",
  "file": {
    "data": "UEsDB...",
    "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "fileName": "normalization_report.docx"
  }
}
```

The `file.data` value is base64. Decode it to save the substitution report as a
DOCX file.

## 10. Client implementation notes

1. Preserve the field names exactly. For example, splitters use `pdf_file`,
   most PDF services use `file`, and fixed croppers use `image_file`.
2. Upload a real filename with the expected extension. Several services validate
   extension case-sensitively (`.pdf`), while others validate MIME type.
3. Set the matching MIME type in multipart clients where feasible, especially
   for the text-extractor/OCR APIs that inspect `content_type`.
4. Always inspect response headers for binary endpoints. PDF-to-Image can
   validly return either one image or a ZIP, depending on source page count.
5. Save `X-*` headers from PDF Normalizer alongside the output PDF when audit
   information about rotations and inserted pages matters.
6. Treat file downloads as ephemeral results at the HTTP boundary. The server
   may keep internal copies in its `downloads` directory, but that directory is
   not a public API or a durable storage contract.

## 11. Configuration and dependencies

The core runtime configuration is supplied with environment variables:

```dotenv
API_HOST=0.0.0.0
API_PORT=8000
API_RELOAD=True
CORS_ORIGINS=*

# Required only by Text Correction
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key

# Required by PDF Normalizer when review_mode=vision (the default)
OPENAI_API_KEY=your_openai_api_key
# Optional; default is gpt-5.6-terra
PDF_NORMALIZER_VISION_MODEL=gpt-5.6-terra
```

Run locally with `python main.py`, then open `http://localhost:8000/docs` to
try the endpoints interactively.
