from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import fitz
import numpy as np
from PIL import Image

from .vision import BatchHeader, PDFVisionReviewer


@dataclass(frozen=True)
class PageAnalysis:
    """Visual signals used to determine where one scanned letter ends."""

    source_page_number: int
    correction: int
    header_score: float
    header_signature: np.ndarray
    writing_signature: np.ndarray


@dataclass(frozen=True)
class RotationSignal:
    """A local orientation decision used to validate the vision result."""

    correction: int
    confidence: float
    source: str


class PDFNormalizerService:
    """Normalize scanned PDFs before they are processed as two-sided letters."""

    _PREVIEW_DPI = 100
    _MIN_AXIS_CONFIDENCE = 0.08
    _MIN_DIRECTION_CONFIDENCE = 0.03
    _STRONG_LOCAL_HINT_CONFIDENCE = 0.15
    _MIN_LETTERHEAD_SCORE = 0.55
    _CONSECUTIVE_HEADER_DISTANCE = 0.08
    _DIFFERENT_HEADER_DISTANCE = 0.42
    _DIFFERENT_WRITING_DISTANCE = 0.55

    @classmethod
    def normalize_pdf(
        cls,
        pdf_bytes: bytes,
        *,
        auto_rotate: bool = True,
        ensure_page_pairs: bool = True,
        review_mode: str = "vision",
        vision_provider: str | None = None,
        vision_model: str | None = None,
        vision_reviewer: PDFVisionReviewer | None = None,
        judge: bool = True,
        split_letters: bool = False,
    ) -> Dict[str, Any]:
        """Return an upright PDF with an even number of pages.

        A missing reverse side is represented by a black page matching the size
        of its preceding scanned page. Vision review is the default because it
        can evaluate the full document sequence; image heuristics are available
        only when callers explicitly choose ``review_mode="heuristic"``.
        ``judge`` has the vision model check the finished document page by
        page and retry the pages it flags; it does not apply to heuristics.
        ``split_letters`` also returns one PDF per detected letter, each with
        its black page, in ``letter_pdfs``.
        """
        if not pdf_bytes:
            raise ValueError("The uploaded PDF is empty")
        if review_mode not in {"vision", "heuristic"}:
            raise ValueError("review_mode must be 'vision' or 'heuristic'")

        try:
            source = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as exc:
            raise ValueError("The uploaded file is not a valid PDF") from exc

        try:
            if source.needs_pass:
                raise ValueError("Password-protected PDFs are not supported")
            if source.page_count == 0:
                raise ValueError("The uploaded PDF has no pages")

            previews: list[Image.Image] = []
            for page_number in range(source.page_count):
                page = source.load_page(page_number)
                preview = cls._render_preview(page)
                previews.append(preview)

            if review_mode == "vision":
                reviewer = vision_reviewer or PDFVisionReviewer()
                plan = reviewer.review(
                    previews,
                    provider=vision_provider,
                    model=vision_model,
                    rotation_hints=cls._local_rotation_hints(previews) if auto_rotate else None,
                    judge=judge and (auto_rotate or ensure_page_pairs),
                    judge_rotations=auto_rotate,
                    judge_page_pairs=ensure_page_pairs,
                    read_batch_header=True,
                )
                if auto_rotate:
                    page_numbers = range(1, source.page_count + 1)
                    corrections = [plan.rotations[page] for page in page_numbers]
                    rotation_sources = [plan.rotation_sources.get(page, "vision") for page in page_numbers]
                else:
                    corrections = [0] * source.page_count
                    rotation_sources = ["disabled"] * source.page_count
                blank_after_source_pages = plan.blank_after_source_pages if ensure_page_pairs else []
                letter_start_pages = plan.letter_start_pages
                review_model = plan.model
                review_provider = plan.provider
                judge_status = plan.judge_status
                judge_retries = plan.judge_retries
                judge_issues = plan.judge_issues
                batch = plan.batch
            else:
                analyses: list[PageAnalysis] = []
                for page_number, preview in enumerate(previews):
                    correction = cls._detect_rotation_from_preview(preview) if auto_rotate else 0
                    upright_preview = cls._rotate_image_clockwise(preview, correction)
                    analyses.append(
                        cls._analyze_page(
                            page_number=page_number,
                            correction=correction,
                            preview=upright_preview,
                        )
                    )
                corrections = [analysis.correction for analysis in analyses]
                rotation_sources = ["heuristic" if auto_rotate else "disabled"] * source.page_count
                blank_after_source_pages = (
                    cls._find_missing_reverse_sides(analyses) if ensure_page_pairs else []
                )
                letter_start_pages = [1]
                review_model = "heuristic"
                review_provider = "heuristic"
                judge_status = "skipped"
                judge_retries = 0
                judge_issues = []
                batch = BatchHeader()

            blank_after_page_set = set(blank_after_source_pages)

            normalized = fitz.open()
            applied_rotations: list[int] = []
            output_page_of_source: dict[int, int] = {}

            for page_number in range(source.page_count):
                page = source.load_page(page_number)
                rotation = corrections[page_number]
                output_page_of_source[page_number + 1] = normalized.page_count + 1

                # insert_pdf keeps the source page vector-based. Its `rotate`
                # argument replaces the source page's /Rotate value, so retain
                # that value and apply the visual correction relative to it.
                output_rotation = (page.rotation + rotation) % 360
                normalized.insert_pdf(
                    source,
                    from_page=page_number,
                    to_page=page_number,
                    rotate=output_rotation,
                )
                applied_rotations.append(rotation)

                if page_number + 1 in blank_after_page_set:
                    last_page = normalized.load_page(normalized.page_count - 1)
                    cls._append_missing_reverse_side(
                        normalized,
                        width=last_page.rect.width,
                        height=last_page.rect.height,
                    )

            letter_first_pages = [output_page_of_source[page] for page in letter_start_pages]
            letter_page_ranges = list(
                zip(
                    letter_first_pages,
                    [page - 1 for page in letter_first_pages[1:]] + [normalized.page_count],
                )
            )
            letter_pdfs: list[bytes] = []
            if split_letters:
                for first, last in letter_page_ranges:
                    letter = fitz.open()
                    try:
                        letter.insert_pdf(normalized, from_page=first - 1, to_page=last - 1)
                        letter_pdfs.append(letter.tobytes(garbage=4, deflate=True))
                    finally:
                        letter.close()

            output_bytes = normalized.tobytes(garbage=4, deflate=True)
            return {
                "pdf_bytes": output_bytes,
                "input_page_count": source.page_count,
                "output_page_count": normalized.page_count,
                "blank_pages_added": len(blank_after_source_pages),
                "blank_after_source_pages": blank_after_source_pages,
                "applied_rotations": applied_rotations,
                "rotation_sources": rotation_sources,
                "letter_start_pages": letter_start_pages,
                "review_mode": review_mode,
                "review_provider": review_provider,
                "review_model": review_model,
                "judge_status": judge_status,
                "judge_retries": judge_retries,
                "judge_issues": judge_issues,
                "batch": batch,
                "letter_page_ranges": letter_page_ranges,
                "letter_pdfs": letter_pdfs,
            }
        finally:
            source.close()
            if "normalized" in locals():
                normalized.close()

    @classmethod
    def _detect_rotation(cls, page: fitz.Page) -> int:
        """Return the clockwise rotation required to make a page upright.

        Tesseract OSD is used when it is installed and confident. Scanners are
        commonly deployed without the Tesseract executable, so a conservative
        image-layout fallback is always available. Ambiguous pages are left
        unchanged rather than risking an incorrect rotation.
        """
        return cls._detect_rotation_from_preview(cls._render_preview(page))

    @classmethod
    def _detect_rotation_from_preview(cls, image: Image.Image) -> int:
        return cls._detect_rotation_signal(image).correction

    @classmethod
    def _local_rotation_hints(cls, previews: list[Image.Image]) -> dict[int, int]:
        """Return strong local orientation signals for the vision review to double-check.

        These are hints only. Gray-toned scans and pages whose writing sits in
        the lower half produce confident but wrong layout results, so a
        disagreement earns the page a second vision look instead of overriding
        the model.
        """
        hints: dict[int, int] = {}
        for page_number, preview in enumerate(previews, start=1):
            local = cls._detect_rotation_signal(preview)
            if local.source == "tesseract" or local.confidence >= cls._STRONG_LOCAL_HINT_CONFIDENCE:
                hints[page_number] = local.correction
        return hints

    @classmethod
    def _detect_rotation_signal(cls, image: Image.Image) -> RotationSignal:
        tesseract_signal = cls._detect_rotation_with_tesseract_signal(image)
        if tesseract_signal is not None:
            return tesseract_signal
        return cls._detect_rotation_from_layout_signal(image)

    @classmethod
    def _render_preview(cls, page: fitz.Page) -> Image.Image:
        scale = cls._PREVIEW_DPI / 72.0
        pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)

    @staticmethod
    def _append_missing_reverse_side(document: fitz.Document, *, width: float, height: float) -> None:
        placeholder = document.new_page(width=width, height=height)
        placeholder.draw_rect(
            placeholder.rect,
            color=(0, 0, 0),
            fill=(0, 0, 0),
            overlay=True,
        )

    @staticmethod
    def _rotate_image_clockwise(image: Image.Image, rotation: int) -> Image.Image:
        if rotation == 0:
            return image
        return image.rotate(-rotation, expand=True)

    @classmethod
    def _analyze_page(
        cls,
        *,
        page_number: int,
        correction: int,
        preview: Image.Image,
    ) -> PageAnalysis:
        mask = cls._ink_mask(preview)
        header_end = max(1, int(mask.shape[0] * 0.28))
        body_start = max(1, int(mask.shape[0] * 0.25))
        return PageAnalysis(
            source_page_number=page_number + 1,
            correction=correction,
            header_score=cls._letterhead_score(mask),
            header_signature=cls._thumbnail(mask[:header_end, :], width=160, height=60),
            writing_signature=cls._writing_signature(preview, mask[body_start:, :]),
        )

    @classmethod
    def _find_missing_reverse_sides(cls, analyses: list[PageAnalysis]) -> list[int]:
        """Return 1-based source-page numbers that need a blank page after them.

        We only need to identify a boundary when the pages since the previous
        inserted side are odd. Even-sized letters already retain their correct
        alignment, so finding their boundaries is unnecessary and would add
        avoidable false positives.
        """
        blank_after: list[int] = []
        current_letter_start = 0

        for next_index in range(1, len(analyses)):
            pages_in_current_letter = next_index - current_letter_start
            if pages_in_current_letter % 2 == 0:
                continue
            if cls._looks_like_new_letter(analyses[next_index - 1], analyses[next_index]):
                blank_after.append(analyses[next_index - 1].source_page_number)
                current_letter_start = next_index

        if (len(analyses) - current_letter_start) % 2:
            blank_after.append(analyses[-1].source_page_number)
        return blank_after

    @classmethod
    def _looks_like_new_letter(cls, previous: PageAnalysis, candidate: PageAnalysis) -> bool:
        """Recognize a new letter without treating normal continuation pages as one."""
        if candidate.header_score < cls._MIN_LETTERHEAD_SCORE:
            return False

        header_distance = cls._signature_distance(
            previous.header_signature,
            candidate.header_signature,
        )
        writing_distance = cls._signature_distance(
            previous.writing_signature,
            candidate.writing_signature,
        )

        # Consecutive letterheads are a strong signal when their visible
        # header differs at all. If the preceding page is a continuation,
        # require a much more distinct new header or substantially different
        # writing before inserting a side.
        if previous.header_score >= cls._MIN_LETTERHEAD_SCORE:
            return (
                header_distance >= cls._CONSECUTIVE_HEADER_DISTANCE
                or writing_distance >= cls._DIFFERENT_WRITING_DISTANCE
            )

        return (
            header_distance >= cls._DIFFERENT_HEADER_DISTANCE
            or writing_distance >= cls._DIFFERENT_WRITING_DISTANCE
        )

    @staticmethod
    def _thumbnail(mask: np.ndarray, *, width: int, height: int) -> np.ndarray:
        thumbnail = Image.fromarray((mask.astype(np.uint8) * 255), mode="L").resize(
            (width, height),
            Image.Resampling.BILINEAR,
        )
        return np.asarray(thumbnail, dtype=np.float32) / 255.0

    @classmethod
    def _writing_signature(cls, preview: Image.Image, body_mask: np.ndarray) -> np.ndarray:
        rgb = np.asarray(preview.convert("RGB"), dtype=np.uint8)
        body_start = rgb.shape[0] - body_mask.shape[0]
        body_rgb = rgb[body_start:, :, :]
        red = body_rgb[:, :, 0].astype(np.int16)
        green = body_rgb[:, :, 1].astype(np.int16)
        blue = body_rgb[:, :, 2].astype(np.int16)
        blue_ink = (blue > red + 18) & (blue > green + 10) & (blue > 70)

        # Blue ink is common in the supplied workflow. For monochrome scans,
        # use the body layout as a conservative handwriting/style proxy.
        if blue_ink.mean() < 0.0002:
            blue_ink = body_mask
        # Keep fine stroke detail: averaging a thumbnail turns different
        # handwritten letters into nearly identical horizontal text bands.
        # Sampling caps memory while retaining enough detail for a stable Dice
        # distance between adjacent pages.
        stride = max(1, int(np.ceil(max(blue_ink.shape) / 450)))
        return blue_ink[::stride, ::stride]

    @staticmethod
    def _signature_distance(first: np.ndarray, second: np.ndarray) -> float:
        if first.shape != second.shape:
            first = PDFNormalizerService._thumbnail(first, width=160, height=160)
            second = PDFNormalizerService._thumbnail(second, width=160, height=160)
        first_ink = first > 0.08
        second_ink = second > 0.08
        denominator = int(first_ink.sum() + second_ink.sum())
        if denominator == 0:
            return 0.0
        overlap = int(np.logical_and(first_ink, second_ink).sum())
        return 1.0 - (2.0 * overlap / denominator)

    @staticmethod
    def _letterhead_score(mask: np.ndarray) -> float:
        height = mask.shape[0]
        header_end = max(1, int(height * 0.25))
        row_density = mask.mean(axis=1)

        header_density = float(mask[:header_end, :].mean())
        longest_gap = 0
        current_gap = 0
        scan_start = max(1, int(height * 0.05))
        scan_end = max(scan_start + 1, int(height * 0.75))
        occupied = row_density > 0.001
        for row_number in range(scan_start, scan_end):
            density = row_density[row_number]
            if density < 0.001:
                current_gap += 1
            else:
                candidate_start = row_number - current_gap
                has_content_before = np.any(occupied[scan_start:candidate_start])
                has_content_after = np.any(occupied[row_number:scan_end])
                if has_content_before and has_content_after:
                    if current_gap > longest_gap:
                        longest_gap = current_gap
                current_gap = 0

        if current_gap:
            candidate_start = scan_end - current_gap
            has_content_before = np.any(occupied[scan_start:candidate_start])
            has_content_after = np.any(occupied[scan_end:])
            if has_content_before and has_content_after and current_gap > longest_gap:
                longest_gap = current_gap

        has_top_content = min(1.0, header_density / 0.012)
        has_separator = float(longest_gap >= max(1, int(height * 0.06)))
        return 0.45 * has_top_content + 0.55 * has_separator

    @staticmethod
    def _detect_rotation_with_tesseract(image: Image.Image) -> Optional[int]:
        signal = PDFNormalizerService._detect_rotation_with_tesseract_signal(image)
        return signal.correction if signal is not None else None

    @staticmethod
    def _detect_rotation_with_tesseract_signal(image: Image.Image) -> Optional[RotationSignal]:
        try:
            import pytesseract

            osd = pytesseract.image_to_osd(
                image,
                config="--psm 0",
                output_type=pytesseract.Output.DICT,
            )
            confidence = float(osd.get("orientation_conf", 0))
            if confidence < 5:
                return None

            # Tesseract reports the counter-clockwise correction. PyMuPDF's
            # insert_pdf uses a clockwise rotation.
            return RotationSignal(
                correction=(-int(osd["rotate"])) % 360,
                confidence=min(1.0, confidence / 15.0),
                source="tesseract",
            )
        except Exception:
            # The Python wrapper can be installed while the system binary is
            # absent. Orientation normalization must still work in that setup.
            return None

    @classmethod
    def _detect_rotation_from_layout(cls, image: Image.Image) -> int:
        return cls._detect_rotation_from_layout_signal(image).correction

    @classmethod
    def _detect_rotation_from_layout_signal(cls, image: Image.Image) -> RotationSignal:
        mask = cls._ink_mask(image)
        if not np.any(mask):
            return RotationSignal(correction=0, confidence=0.0, source="layout")

        candidates: list[tuple[int, float, float]] = []
        for rotation in (0, 90, 180, 270):
            rotated = cls._rotate_clockwise(mask, rotation)
            candidates.append(
                (
                    rotation,
                    cls._horizontal_text_score(rotated),
                    cls._top_first_score(rotated),
                )
            )

        axis_scores = [candidate[1] for candidate in candidates]
        strongest_axis = max(axis_scores)
        weakest_axis = min(axis_scores)
        axis_confidence = strongest_axis - weakest_axis
        if axis_confidence < cls._MIN_AXIS_CONFIDENCE:
            return RotationSignal(correction=0, confidence=0.0, source="layout")

        # 0/180 and 90/270 have the same text-line score. Use the document's
        # natural top-to-bottom layout to select a direction within the best
        # pair; most letters begin near the top and leave a larger lower margin.
        best_axis = [
            candidate
            for candidate in candidates
            if candidate[1] >= strongest_axis - 0.01
        ]
        best_axis.sort(key=lambda candidate: candidate[2], reverse=True)
        selected = best_axis[0]

        if len(best_axis) > 1:
            direction_gap = selected[2] - best_axis[1][2]
            if direction_gap < cls._MIN_DIRECTION_CONFIDENCE:
                return RotationSignal(
                    correction=0,
                    confidence=max(0.0, direction_gap),
                    source="layout",
                )
        else:
            direction_gap = axis_confidence

        return RotationSignal(
            correction=selected[0],
            confidence=min(1.0, max(0.0, float(direction_gap))),
            source="layout",
        )

    @staticmethod
    def _rotate_clockwise(mask: np.ndarray, rotation: int) -> np.ndarray:
        return np.rot90(mask, k=(-rotation // 90) % 4)

    @staticmethod
    def _ink_mask(image: Image.Image) -> np.ndarray:
        grayscale = np.asarray(image.convert("L"), dtype=np.uint8)
        histogram = np.bincount(grayscale.ravel(), minlength=256).astype(np.float64)
        total = histogram.sum()
        if total == 0:
            return np.zeros_like(grayscale, dtype=bool)

        cumulative_weight = np.cumsum(histogram)
        cumulative_mean = np.cumsum(histogram * np.arange(256))
        total_mean = cumulative_mean[-1]
        denominator = cumulative_weight * (total - cumulative_weight)
        between_class_variance = np.divide(
            (total_mean * cumulative_weight - cumulative_mean) ** 2,
            denominator,
            out=np.zeros(256),
            where=denominator > 0,
        )
        threshold = min(int(np.argmax(between_class_variance)), 225)
        threshold = max(threshold, 80)
        mask = grayscale < threshold

        # Ignore a thin scan border and full-width / full-height rules, which
        # otherwise dominate the layout score on form-style pages.
        border_y = max(1, int(mask.shape[0] * 0.01))
        border_x = max(1, int(mask.shape[1] * 0.01))
        mask[:border_y, :] = False
        mask[-border_y:, :] = False
        mask[:, :border_x] = False
        mask[:, -border_x:] = False

        row_fill = mask.mean(axis=1)
        col_fill = mask.mean(axis=0)
        mask[row_fill > 0.8, :] = False
        mask[:, col_fill > 0.8] = False
        return mask

    @staticmethod
    def _horizontal_text_score(mask: np.ndarray) -> float:
        occupied_rows, occupied_columns = np.nonzero(mask)
        if occupied_rows.size == 0:
            return 0.0

        # Page margins distort the projection variance for a short handwritten
        # note positioned on one side of an otherwise empty page. Score only
        # the visible content box when deciding whether text runs horizontally.
        mask = mask[
            occupied_rows.min() : occupied_rows.max() + 1,
            occupied_columns.min() : occupied_columns.max() + 1,
        ]
        rows = mask.mean(axis=1)
        columns = mask.mean(axis=0)
        row_variation = float(np.std(rows))
        column_variation = float(np.std(columns))
        return (row_variation - column_variation) / (row_variation + column_variation + 1e-9)

    @staticmethod
    def _top_first_score(mask: np.ndarray) -> float:
        row_density = mask.mean(axis=1)
        occupied_rows = np.flatnonzero(row_density > 0.001)
        if occupied_rows.size == 0:
            return 0.0

        height = mask.shape[0]
        top_margin = occupied_rows[0] / height
        bottom_margin = (height - 1 - occupied_rows[-1]) / height
        third = max(1, height // 3)
        top_density = float(mask[:third, :].mean())
        bottom_density = float(mask[-third:, :].mean())
        density_bias = (top_density - bottom_density) / (top_density + bottom_density + 1e-9)

        return 0.7 * (bottom_margin - top_margin) + 0.3 * density_bias
