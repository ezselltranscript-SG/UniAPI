import io
import os
import tempfile
from typing import List, Tuple, Dict, Any, Optional

from PIL import Image
from pdf2image import convert_from_bytes
import pytesseract
try:
    # Prefer pypdf if available (newer API), fallback to PyPDF2
    import pypdf as _pypdf
except Exception:
    _pypdf = None
try:
    import PyPDF2 as _PyPDF2
except Exception:
    _PyPDF2 = None

# Optional fallback renderer that doesn't require Poppler
try:
    import fitz  # PyMuPDF
except Exception:
    fitz = None


class AnchoredPdfCropperService:
    """
    OCR-only cropper. It locates the 'Mail to / Lancaster Farming / Mailbox Markets ...'
    block via Tesseract and builds a panel crop from that position.
    """

    @staticmethod
    def _normalize(s: str) -> str:
        import re
        return re.sub(r"[^a-z0-9 ]+", "", (s or "").lower()).strip()

    @staticmethod
    def _fuzzy_match(txt: str, keywords: List[str], min_ratio: float = 0.75) -> bool:
        from difflib import SequenceMatcher
        t = AnchoredPdfCropperService._normalize(txt)
        if not t:
            return False
        for k in keywords:
            kk = AnchoredPdfCropperService._normalize(k)
            if not kk:
                continue
            r = SequenceMatcher(a=t, b=kk).ratio()
            if r >= min_ratio or kk in t:
                return True
        return False

    @staticmethod
    def _render_pdf_pages(pdf_bytes: bytes, dpi: int, poppler_path: Optional[str]) -> List[Image.Image]:
        """
        Try pdf2image+Poppler first; if unavailable, try PyMuPDF (fitz) as a fallback.
        Returns list of PIL.Image pages at approximately the requested DPI.
        """
        # Primary path: pdf2image
        try:
            effective_poppler = poppler_path or os.environ.get("POPPLER_PATH")
            if effective_poppler:
                return convert_from_bytes(pdf_bytes, dpi=dpi, poppler_path=effective_poppler)
            return convert_from_bytes(pdf_bytes, dpi=dpi)
        except Exception:
            # Fallback: PyMuPDF if available
            if fitz is None:
                raise
            try:
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                zoom = dpi / 72.0
                mat = fitz.Matrix(zoom, zoom)
                pages: List[Image.Image] = []
                for page in doc:
                    pix = page.get_pixmap(matrix=mat, alpha=False)
                    mode = "RGB"
                    img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
                    pages.append(img)
                return pages
            except Exception as e:
                # Re-raise a clearer error
                raise Exception(
                    "Unable to render PDF pages with both Poppler and PyMuPDF. "
                    "Install Poppler and set POPPLER_PATH, or install 'pymupdf'."
                ) from e

    @staticmethod
    def _find_header_top(pil_img: Image.Image, lang: str = "eng") -> Optional[int]:
        """
        Find approximate TOP of the form panel by looking for header tokens
        such as 'Account Number', 'Name', 'Address', or the 'If you don't know...' band.
        Returns the y coordinate (int) of the first match's top, or None.
        """
        try:
            data = pytesseract.image_to_data(pil_img, lang=lang, output_type=pytesseract.Output.DICT, config="--psm 6")
            n = len(data.get("text", []))
            if n == 0:
                return None
            h = pil_img.size[1]
            keys = [
                "account", "name", "address", "if you don't know", "if you dont know",
                "check one", "for sale", "notice", "wanted",
            ]
            ys = []
            for i in range(n):
                txt = (data["text"][i] or "").strip().lower()
                if not txt:
                    continue
                if any(k in txt for k in keys):
                    ys.append(data["top"][i])
            if not ys:
                return None
            top = max(0, min(ys) - int(0.01 * h))
            return top
        except Exception:
            return None

    @staticmethod
    def _find_mailto_block(pil_img: Image.Image, lang: str = "eng") -> Optional[Tuple[int, int, int, int]]:
        """
        Find the 'Mail to / Lancaster Farming / Mailbox Markets ...' block using OCR tokens only.
        Returns a bounding box (x1,y1,x2,y2) if found.
        """
        try:
            data = pytesseract.image_to_data(pil_img, lang=lang, output_type=pytesseract.Output.DICT, config="--psm 6")
            n = len(data.get("text", []))
            if n == 0:
                return None
            w, h = pil_img.size
            min_y = int(0.5 * h)
            keys = [
                "mail to",
                "lancaster",
                "mailbox markets",
                "po box",
                "lancaster, pa",
            ]
            boxes: List[Tuple[int,int,int,int]] = []
            for i in range(n):
                txt = (data["text"][i] or "").strip()
                if not txt:
                    continue
                y = data["top"][i]
                if y < min_y:
                    continue
                if AnchoredPdfCropperService._fuzzy_match(txt, keys):
                    x, y, bw, bh = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
                    boxes.append((x, y, x + bw, y + bh))
            if not boxes:
                return None
            xs = [b[0] for b in boxes]
            ys = [b[1] for b in boxes]
            xe = [b[2] for b in boxes]
            ye = [b[3] for b in boxes]
            # Expand slightly to include the logo that OCR may miss
            pad_x = int(0.02 * w)
            pad_y = int(0.01 * h)
            left = max(int(0.45 * w), min(xs) - pad_x)
            top = max(0, min(ys) - pad_y)
            right = min(w, max(xe) + int(0.06 * w))
            bottom = min(h, max(ye) + int(0.03 * h))
            # Ensure a minimum height to encompass logo + address line
            min_h = int(0.10 * h)
            if bottom - top < min_h:
                bottom = min(h, top + min_h)
            return (left, top, right, bottom)
        except Exception:
            return None

    @staticmethod
    def _panel_bounds_from_ocr(pil_img: Image.Image, lang: str = "eng") -> Optional[Tuple[int,int,int,int]]:
        """
        Dynamic panel detection using OCR only:
        - Find a top anchor using header tokens.
        - Find a bottom anchor using mail-to/address tokens.
        - Use all OCR words between anchors on the right-half to compute left/right.
        Returns (x1, y1, x2, y2) or None on failure.
        """
        try:
            data = pytesseract.image_to_data(
                pil_img, lang=lang, output_type=pytesseract.Output.DICT, config="--psm 6"
            )
            n = len(data.get("text", []))
            if n == 0:
                return None
            w, h = pil_img.size
            header_keys = ["account", "name", "address", "check one", "for sale", "notice", "wanted"]
            bottom_keys = ["mail to", "lancaster", "mailbox markets", "po box", "lancaster, pa", "17608"]
            header_y: Optional[int] = None
            bottom_y: Optional[int] = None
            for i in range(n):
                txt = (data["text"][i] or "").strip().lower()
                if not txt:
                    continue
                y = data["top"][i]
                if any(k in txt for k in header_keys):
                    header_y = y if header_y is None else min(header_y, y)
                if any(k in txt for k in bottom_keys):
                    bottom_y = y if bottom_y is None else max(bottom_y, y)
            if header_y is None or bottom_y is None or bottom_y <= header_y:
                return None
            # Collect words between header and bottom anchors; include much more left side
            # while still avoiding the far-left requirements column.
            min_x_limit = int(0.22 * w)
            xs: List[int] = []
            ys: List[int] = []
            xe: List[int] = []
            ye: List[int] = []
            for i in range(n):
                txt = (data["text"][i] or "").strip()
                if not txt:
                    continue
                x = data["left"][i]
                y = data["top"][i]
                bw = data["width"][i]
                bh = data["height"][i]
                if y < header_y or y > bottom_y + int(0.02 * h):
                    continue
                if x < min_x_limit:
                    continue
                xs.append(x)
                ys.append(y)
                xe.append(x + bw)
                ye.append(y + bh)
            if not xs:
                return None
            # Increase horizontal padding to pull left boundary further
            pad_x = int(0.08 * w)
            top = max(0, header_y - int(0.01 * h))
            bottom = min(h, bottom_y + int(0.02 * h))
            left = max(min_x_limit, max(0, min(xs) - pad_x))
            right = min(w, max(xe) + pad_x)
            if bottom - top < int(0.40 * h):
                bottom = min(h, top + int(0.40 * h))
            return (left, top, right, bottom)
        except Exception:
            return None

    @staticmethod
    def _panel_bounds_hybrid(pil_img: Image.Image, lang: str = "eng") -> Optional[Tuple[int,int,int,int]]:
        """
        Hybrid approach that uses page size to propose a panel region first,
        then refines/expands with OCR anchors and word extents. Designed to
        consistently include more of the left side while avoiding the left
        requirements column.
        """
        try:
            w, h = pil_img.size
            # Baseline panel by page size
            left_base = int(0.20 * w)
            right_base = int(0.985 * w)
            # Anchors
            header_top = AnchoredPdfCropperService._find_header_top(pil_img, lang=lang)
            if header_top is None:
                header_top = int(0.16 * h)
            mailto_box = AnchoredPdfCropperService._find_mailto_block(pil_img, lang=lang)
            if mailto_box is None:
                bottom_base = int(0.92 * h)
            else:
                bottom_base = min(h, mailto_box[3])

            # OCR extents between anchors
            data = pytesseract.image_to_data(
                pil_img, lang=lang, output_type=pytesseract.Output.DICT, config="--psm 6"
            )
            n = len(data.get("text", []))
            xs: List[int] = []
            xe: List[int] = []
            min_x_limit = int(0.20 * w)  # allow much more left when text exists
            for i in range(n):
                txt = (data["text"][i] or "").strip()
                if not txt:
                    continue
                x = data["left"][i]
                y = data["top"][i]
                bw = data["width"][i]
                if y < header_top or y > bottom_base:
                    continue
                if x < min_x_limit:
                    continue
                xs.append(x)
                xe.append(x + bw)
            pad_x = int(0.10 * w)
            left_ocr = (min(xs) - pad_x) if xs else left_base
            right_ocr = (max(xe) + pad_x) if xe else right_base

            left = max(min_x_limit, min(left_base, max(0, left_ocr)))
            right = min(w, max(right_base, right_ocr))
            top = max(0, header_top - int(0.01 * h))
            bottom = min(h, max(bottom_base, top + int(0.55 * h)))
            if bottom - top < int(0.55 * h):
                bottom = min(h, top + int(0.55 * h))
            return (left, top, right, bottom)
        except Exception:
            return None

    @staticmethod
    def crop_pdfs(
        pdf_files: List[Tuple[bytes, str]],
        lang: str = "eng",
        dpi: int = 300,
        poppler_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process PDFs. For each page, OCR-find the Mail-to/Lancaster Farming block
        and crop a panel region on the right based solely on those coordinates.
        Returns a ZIP buffer with PNG crops.
        """

        zip_buffer = io.BytesIO()
        import zipfile
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
            for pdf_index, (pdf_bytes, original_name) in enumerate(pdf_files, start=1):
                base = os.path.splitext(os.path.basename(original_name or f"file_{pdf_index}.pdf"))[0]
                # Convert pages to images (with fallback)
                pages = AnchoredPdfCropperService._render_pdf_pages(pdf_bytes, dpi=dpi, poppler_path=poppler_path)
                # Read original PDF page sizes in points (1 pt = 1/72 inch)
                page_sizes_pts: List[Tuple[float, float]] = []
                reader = None
                try:
                    if _pypdf is not None:
                        reader = _pypdf.PdfReader(io.BytesIO(pdf_bytes))
                    elif _PyPDF2 is not None:
                        reader = _PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
                except Exception:
                    reader = None
                if reader is not None:
                    try:
                        for p in reader.pages:
                            # p.mediabox.width/height may be Decimals or Numbers
                            try:
                                w_pt = float(p.mediabox.width)
                                h_pt = float(p.mediabox.height)
                            except Exception:
                                # Fallback in case of alternative attributes
                                w_pt = float(getattr(p, "mediaBox").getWidth()) if hasattr(p, "mediaBox") else 0.0
                                h_pt = float(getattr(p, "mediaBox").getHeight()) if hasattr(p, "mediaBox") else 0.0
                            page_sizes_pts.append((w_pt, h_pt))
                    except Exception:
                        page_sizes_pts = []

                for page_idx, pil_img in enumerate(pages, start=1):
                    img_w, img_h = pil_img.size
                    # If we have original page size, compute px/pt scale and print debug info
                    if 1 <= page_idx <= len(page_sizes_pts):
                        orig_w_pt, orig_h_pt = page_sizes_pts[page_idx - 1]
                        # Expected: px_per_pt ~= dpi/72
                        px_per_pt_x = (img_w / orig_w_pt) if orig_w_pt else 0.0
                        px_per_pt_y = (img_h / orig_h_pt) if orig_h_pt else 0.0
                        # ASCII-only to avoid Windows console encoding errors
                        print(
                            f"Page size (pt): {orig_w_pt:.2f} x {orig_h_pt:.2f}; "
                            f"px_per_pt=({px_per_pt_x:.3f}, {px_per_pt_y:.3f})"
                        )
                    else:
                        orig_w_pt = orig_h_pt = 0.0

                    # OCR-only: find the Mail-to block and build the crop from it
                    mailto_box = AnchoredPdfCropperService._find_mailto_block(pil_img, lang=lang)
                    if mailto_box is not None:
                        mx1, my1, mx2, my2 = mailto_box
                        # Left: move slightly right (reduce left coverage a bit)
                        left = max(int(0.22 * img_w), mx1 - int(0.30 * img_w))
                        # Right: a bit tighter to reduce extra margin
                        right = min(img_w, max(mx2 + int(0.10 * img_w), int(0.965 * img_w)))
                        # Bottom: just above the footer bar under the address line
                        bottom = min(img_h, my2 + int(0.004 * img_h))
                        # Top: use detected header, but cap around ~14% of page height
                        header_top = AnchoredPdfCropperService._find_header_top(pil_img, lang=lang)
                        header_cap = int(0.14 * img_h)
                        if header_top is None:
                            header_top = header_cap
                        top_target = min(header_top, header_cap)
                        # Height targets ~64% with a minimum 58% to drop the top slightly
                        target_h = int(0.64 * img_h)
                        min_h = int(0.58 * img_h)
                        top_from_height = max(0, bottom - target_h)
                        top = max(0, min(top_target, top_from_height))
                        if bottom - top < min_h:
                            top = max(0, bottom - min_h)
                        crop_box = (left, top, right, bottom)
                    else:
                        # Fallback: take right portion if mail-to not detected
                        left = int(0.25 * img_w)
                        crop_box = (left, int(0.12 * img_h), img_w, int(0.92 * img_h))
                    cropped = pil_img.crop(crop_box)
                    buff = io.BytesIO()
                    cropped.save(buff, format="PNG")
                    buff.seek(0)
                    zip_name = f"{base}_p{page_idx:02d}.png"
                    zipf.writestr(zip_name, buff.getvalue())
        zip_buffer.seek(0)
        return {
            "buffer": zip_buffer,
            "filename": "anchored_crops.zip"
        }
