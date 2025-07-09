# Unified Services API

This project unifies various document processing, transcription, and letter generation services into a centralized API.

## Included Services

1. **PDF Splitter** - Splits PDF files into individual pages
2. **PDF Pair Splitter** - Splits PDF files into pairs of pages (2 pages per file)
3. **PDF Custom Splitter** - Splits PDF files into groups with a custom number of pages per file
4. **Image Cropper** - Divides images into two parts (header and body) based on a specified division point
5. **Fixed Image Cropper** - Divides images into two parts (header and body) with predefined dimensions
6. **Word to PDF** - Converts Word documents to PDF while maintaining the original formatting
7. **File Merger** - Merges multiple PDF or DOCX files contained in a compressed archive
8. **PDF to Image** - Converts PDF files to PNG or JPEG images
9. **OCR** - Performs Optical Character Recognition on images and PDFs
10. **Image to PDF** - Converts images to PDF format
11. **PDF Text Extractor** - Extracts text from PDF files
12. *Additional services to be added*

### Service Details

#### PDF Splitter
Splits a PDF file into individual pages and returns a ZIP file with all separated pages.
- **Endpoint**: `/pdf-splitter/split/`
- **Output Format**: Individual PDF files in a ZIP archive (example: `document-page1.pdf`, `document-page2.pdf`, etc.)

#### PDF Pair Splitter
Splits a PDF file into pairs of pages (2 pages per file) and returns a ZIP file with all pairs.
- **Endpoint**: `/pdf-pair-splitter/split-pairs/`
- **Output Format**: PDF files with page pairs in a ZIP archive (example: `document_Part1.pdf`, `document_Part2.pdf`, etc.)

#### PDF Custom Splitter
Splits a PDF file into groups with a custom number of pages per file, as specified by the user.
- **Endpoint**: `/pdf-custom-splitter/split-custom/`
- **Parameters**: `pages_per_file` - Number of pages per output file (default: 3)
- **Output Format**: PDF files with custom page groups in a ZIP archive (example: `document_Group1_Pages1-4.pdf`, `document_Group2_Pages5-8.pdf`, etc.)

#### Image Cropper
Divides an image into two parts: header (top) and body (bottom), based on a division point specified by the user.
- **Endpoint**: `/image-cropper/crop/`
- **Parameters**: Division point in pixels or percentage
- **Output Format**: Image files in a ZIP archive (example: `image_header.jpg`, `image_body.jpg`)

#### Fixed Image Cropper Die Botschaft Letters
Divides an image into two parts: header (top) and body (bottom), with fixed predefined dimensions.
- **Endpoint**: `/fixed-image-cropper/crop-fixed/`
- **Dimensions**: 
  - Header: from 12% to 30% of the image height
  - Body: from 31% to 100% of the image height
- **Output Format**: Image files in a ZIP archive (example: `image_header.jpg`, `image_body.jpg`)

#### Word to PDF
Converts Word documents (.doc, .docx) to PDF format while maintaining the original formatting.
- **Endpoint**: `/word-to-pdf/convert/`
- **Output Format**: PDF file with the same name as the original document

#### File Merger
Merges multiple PDF or DOCX files contained in a compressed archive (ZIP, RAR, etc.).
- **Endpoint**: `/file-merger/merge/`
- **Features**: Sorts files by part number in the filename
- **Output Format**: A single merged PDF or DOCX file

#### PDF to Image
Converts PDF files to PNG or JPEG images.
- **Endpoint**: `/pdf-to-image/convert/`
- **Parameters**: `format` - Output image format (png, jpeg, jpg). Default: png
- **Output Format**: 
  - Single page PDF: Direct image download
  - Multi-page PDF: ZIP file containing all pages as separate images

#### OCR
Performs Optical Character Recognition on images and PDFs to extract text.
- **Endpoint for Images**: `/ocr/image/`
- **Endpoint for PDFs**: `/ocr/pdf/`
- **Parameters**: 
  - `lang` - Language for OCR (default: spa for Spanish, can use eng for English)
  - `pages_only` - For PDFs, returns only text by pages without full text (default: false)
- **Output Format**: JSON with extracted text

#### Image to PDF
Converts images to PDF format.
- **Endpoint for Single Image**: `/image-to-pdf/convert/`
- **Endpoint for Multiple Images**: `/image-to-pdf/convert-multiple/`
- **Parameters**: `page_size` - Size of PDF page (A4 or letter, default: A4)
- **Output Format**: PDF file

#### PDF Text Extractor
Extracts text from PDF files without OCR (for PDFs with embedded text).
- **Endpoint for Basic Extraction**: `/pdf-text-extractor/extract/`
- **Endpoint for Extraction with Metadata**: `/pdf-text-extractor/extract-with-metadata/`
- **Endpoint for Text File Output**: `/pdf-text-extractor/extract-to-file/`
- **Parameters**: 
  - `by_page` - Return text separated by pages (default: false)
  - `format` - For text file output, format of the output file (currently only txt)
- **Output Format**: JSON with extracted text or text file

## Requirements

- Python 3.8+
- Dependencies listed in `requirements.txt`

## Installation

```bash
pip install -r requirements.txt
```

## Execution

```bash
python main.py
```

The API will be available at http://localhost:8000

## Documentation

API documentation is available at http://localhost:8000/docs once the server is running.
