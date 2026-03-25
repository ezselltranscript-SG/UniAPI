import io
from typing import Any, Dict, List, Tuple

import cv2
import numpy as np
import fitz
from PIL import Image


class PDFChunkMarginCropperService:
    @staticmethod
    def _pil_to_bgr(image: Image.Image) -> np.ndarray:
        rgb = image.convert("RGB")
        arr = np.array(rgb)
        return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

    @staticmethod
    def _bgr_to_pil(bgr: np.ndarray) -> Image.Image:
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb)

    @staticmethod
    def _has_budget_logo(bgr: np.ndarray) -> bool:
        h, w = bgr.shape[:2]
        if h <= 0 or w <= 0:
            return False

        header_h = int(h * 0.22)
        if header_h < 20:
            return False

        roi = bgr[0:header_h, 0:w]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        th = cv2.morphologyEx(
            th,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_RECT, (max(18, w // 90), max(6, header_h // 60))),
            iterations=2,
        )
        th = cv2.morphologyEx(
            th,
            cv2.MORPH_OPEN,
            cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)),
            iterations=1,
        )

        contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return False

        header_area = float(header_h * w)
        min_area = header_area * 0.004
        max_area = header_area * 0.28
        min_x = int(w * 0.12)
        max_x = int(w * 0.88)

        best_score = 0.0
        for cnt in contours:
            area = float(cv2.contourArea(cnt))
            if area < min_area or area > max_area:
                continue
            x, y, ww, hh = cv2.boundingRect(cnt)
            if ww <= 0 or hh <= 0:
                continue
            cx = x + ww * 0.5
            if not (min_x <= cx <= max_x):
                continue

            width_ratio = ww / max(1.0, float(w))
            height_ratio = hh / max(1.0, float(header_h))
            if width_ratio < 0.18 or width_ratio > 0.85:
                continue
            if height_ratio < 0.10 or height_ratio > 0.75:
                continue

            box_area = float(ww * hh)
            if box_area <= 0:
                continue
            fill = area / box_area
            if fill < 0.05:
                continue

            y_ratio = y / max(1.0, float(header_h))
            score = (
                width_ratio * 3.0
                + height_ratio * 2.0
                + min(1.0, fill) * 3.5
                + max(0.0, 0.55 - abs(0.38 - y_ratio)) * 2.0
            )
            if score > best_score:
                best_score = score

        return best_score >= 2.0

    @staticmethod
    def _detect_budget_template_id(bgr: np.ndarray) -> int:
        h, w = bgr.shape[:2]
        if h <= 0 or w <= 0:
            return 3

        bottom = int(h * 0.40)
        if bottom <= 10:
            return 3

        roi = bgr[0:bottom, 0:w]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        th = cv2.morphologyEx(
            th,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_RECT, (5, 3)),
            iterations=1,
        )

        contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return 3

        roi_h, roi_w = th.shape[:2]
        roi_area = float(max(roi_h * roi_w, 1))
        logo_like_blocks = 0
        for cnt in contours:
            x, y, ww, hh = cv2.boundingRect(cnt)
            if ww <= 0 or hh <= 0:
                continue
            bbox_area = float(ww * hh)
            if bbox_area < (roi_area * 0.02):
                continue
            cnt_area = float(cv2.contourArea(cnt))
            fill_ratio = cnt_area / (bbox_area + 1e-6)
            if fill_ratio >= 0.25:
                logo_like_blocks += 1

        if logo_like_blocks == 0:
            return 3

        mid = roi_w // 2
        left_ink = int(np.sum(th[:, :mid] > 0))
        right_ink = int(np.sum(th[:, mid:] > 0))
        left_ratio = left_ink / float((roi_h * max(mid, 1)) + 1e-6)
        right_ratio = right_ink / float((roi_h * max(roi_w - mid, 1)) + 1e-6)

        if left_ratio > right_ratio * 1.10:
            return 2
        return 1

    @staticmethod
    def _apply_budget_header_floor(
        box: Tuple[int, int, int, int],
        h: int,
        template_id: int,
    ) -> Tuple[int, int, int, int]:
        x1, y1, x2, y2 = box
        if h <= 0:
            return box
        if template_id == 2:
            floor_y = int(h * 0.25)
        else:
            floor_y = int(h * 0.27)
        y1 = max(y1, floor_y)
        if y2 <= y1:
            y2 = min(h, y1 + int(h * 0.10))
        return x1, y1, x2, y2

    @staticmethod
    def _force_full_width_box(
        box: Tuple[int, int, int, int],
        h: int,
        w: int,
    ) -> Tuple[int, int, int, int]:
        if h <= 0 or w <= 0:
            return box
        _, y1, _, y2 = box
        y1 = max(0, min(int(y1), h))
        y2 = max(0, min(int(y2), h))
        if y2 <= y1:
            y2 = min(h, y1 + int(h * 0.10))
        return 0, y1, w, y2

    @staticmethod
    def _stabilize_budget_box(
        box: Tuple[int, int, int, int],
        h: int,
        w: int,
        template_id: int,
    ) -> Tuple[int, int, int, int]:
        if h <= 0 or w <= 0:
            return box

        x1, y1, x2, y2 = box
        x1 = max(0, min(int(x1), w))
        x2 = max(0, min(int(x2), w))
        y1 = max(0, min(int(y1), h))
        y2 = max(0, min(int(y2), h))

        height = max(0, y2 - y1)

        floor_y = int(h * (0.25 if template_id == 2 else 0.27))
        safe_x1 = 0
        safe_x2 = w
        safe_y1 = floor_y
        safe_y2 = int(h * 0.97)

        unstable = False
        if height < int(h * 0.30):
            unstable = True

        if unstable:
            return safe_x1, safe_y1, safe_x2, safe_y2

        x1 = safe_x1
        x2 = safe_x2
        y1 = max(y1, safe_y1)
        y2 = min(y2, safe_y2)
        if y2 <= y1:
            y2 = safe_y2
        return x1, y1, x2, y2

    @staticmethod
    def _preprocess(bgr: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape

        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        blurred = cv2.GaussianBlur(enhanced, (3, 3), 0)
        denoised = cv2.fastNlMeansDenoising(
            blurred,
            None,
            h=12,
            templateWindowSize=7,
            searchWindowSize=21,
        )

        bin_adapt = cv2.adaptiveThreshold(
            denoised,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            blockSize=25,
            C=8,
        )
        _, bin_fixed = cv2.threshold(denoised, 185, 255, cv2.THRESH_BINARY_INV)
        _, bin_otsu = cv2.threshold(
            denoised,
            0,
            255,
            cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU,
        )

        line_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(40, w // 15), 1))
        blackhat = cv2.morphologyEx(denoised, cv2.MORPH_BLACKHAT, line_kernel)
        _, bin_blackhat = cv2.threshold(
            blackhat,
            0,
            255,
            cv2.THRESH_BINARY + cv2.THRESH_OTSU,
        )

        combined = cv2.bitwise_or(bin_adapt, bin_fixed)
        combined = cv2.bitwise_or(combined, bin_otsu)
        combined = cv2.bitwise_or(combined, bin_blackhat)
        combined = cv2.morphologyEx(
            combined,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_RECT, (5, 1)),
        )
        return combined

    @staticmethod
    def _extract_hlines(binary: np.ndarray, h_page: int, w_page: int) -> np.ndarray:
        kernel_width = max(28, w_page // 18)
        bridge_width = max(18, w_page // 45)

        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_width, 1))
        bridge_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (bridge_width, 1))

        binary_lines = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, bridge_kernel)
        return cv2.morphologyEx(binary_lines, cv2.MORPH_OPEN, h_kernel)

    @staticmethod
    def _find_box_by_hlines(
        binary: np.ndarray,
        h_page: int,
        w_page: int,
        h_lines: np.ndarray | None = None,
    ) -> Tuple[int, int, int, int] | None:
        if h_lines is None:
            h_lines = PDFChunkMarginCropperService._extract_hlines(binary, h_page, w_page)

        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(40, h_page // 4)))
        v_bridge = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(20, h_page // 30)))
        binary_v = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, v_bridge)
        v_lines = cv2.morphologyEx(binary_v, cv2.MORPH_OPEN, v_kernel)
        left_border = right_border = None
        border_ok = False

        contours, _ = cv2.findContours(v_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        segments: List[Tuple[float, int, int]] = []
        for cnt in contours:
            x, y, ww, hh = cv2.boundingRect(cnt)
            if hh < h_page * 0.25:
                continue
            if hh < ww * 2.5:
                continue
            segments.append((x + ww / 2.0, y, y + hh))

        if segments:
            segments.sort(key=lambda s: s[0])
            clusters: List[Dict[str, float]] = []
            cluster_tol = max(6, int(w_page * 0.006))

            for x_center, y_top, y_bottom in segments:
                if clusters and abs(x_center - clusters[-1]["x"]) <= cluster_tol:
                    c = clusters[-1]
                    c["x_sum"] += x_center
                    c["count"] += 1.0
                    c["x"] = c["x_sum"] / c["count"]
                    c["top"] = min(c["top"], float(y_top))
                    c["bottom"] = max(c["bottom"], float(y_bottom))
                else:
                    clusters.append(
                        {
                            "x": float(x_center),
                            "x_sum": float(x_center),
                            "count": 1.0,
                            "top": float(y_top),
                            "bottom": float(y_bottom),
                        }
                    )

            best_pair = None
            best_score = -1.0
            for i in range(len(clusters)):
                for j in range(i + 1, len(clusters)):
                    left = clusters[i]
                    right = clusters[j]
                    width = right["x"] - left["x"]
                    if width < w_page * 0.45:
                        continue
                    overlap_top = max(left["top"], right["top"])
                    overlap_bottom = min(left["bottom"], right["bottom"])
                    overlap = overlap_bottom - overlap_top
                    if overlap < h_page * 0.30:
                        continue
                    height_score = (left["bottom"] - left["top"]) + (right["bottom"] - right["top"])
                    score = overlap + 0.2 * height_score
                    if score > best_score:
                        best_score = score
                        best_pair = (left, right)

            if best_pair is not None:
                left, right = best_pair
                left_border = int(left["x"])
                right_border = int(right["x"])
                border_ok = True

        row_sums = np.sum(h_lines > 0, axis=1)
        nonzero = row_sums[row_sums > 0]
        if len(nonzero) == 0:
            return None
        row_threshold = max(w_page * 0.04, float(np.percentile(nonzero, 80)) * 0.45)
        line_rows = np.where(row_sums > row_threshold)[0]

        if len(line_rows) < 4:
            row_threshold = max(w_page * 0.03, float(np.percentile(nonzero, 70)) * 0.35)
            line_rows = np.where(row_sums > row_threshold)[0]
            if len(line_rows) < 4:
                return None

        logical_lines: List[int] = []
        line_extents: List[Tuple[int, int]] = []
        group = [int(line_rows[0])]
        for r in line_rows[1:]:
            if int(r) - group[-1] <= 6:
                group.append(int(r))
            else:
                y_center = int(np.mean(group))
                logical_lines.append(y_center)
                row_band = h_lines[group[0] : group[-1] + 1, :]
                cols_lit = np.where(np.any(row_band > 0, axis=0))[0]
                if len(cols_lit) > 0:
                    line_extents.append((int(cols_lit[0]), int(cols_lit[-1])))
                else:
                    line_extents.append((0, 0))
                group = [int(r)]

        y_center = int(np.mean(group))
        logical_lines.append(y_center)
        row_band = h_lines[group[0] : group[-1] + 1, :]
        cols_lit = np.where(np.any(row_band > 0, axis=0))[0]
        if len(cols_lit) > 0:
            line_extents.append((int(cols_lit[0]), int(cols_lit[-1])))
        else:
            line_extents.append((0, 0))

        if len(logical_lines) < 4:
            return None

        full_idx: List[int] = []
        if border_ok and left_border is not None and right_border is not None:
            border_tol = max(25, int(w_page * 0.05))
            full_idx = [
                i
                for i, (xmin, xmax) in enumerate(line_extents)
                if xmin <= left_border + border_tol and xmax >= right_border - border_tol
            ]

        if len(full_idx) < 4:
            lengths = np.array([xmax - xmin for xmin, xmax in line_extents])
            valid = lengths[lengths > 0]
            max_len = int(np.percentile(valid, 90)) if valid.size else 0
            min_len = int(max_len * 0.70)
            long_idx = [i for i, length in enumerate(lengths) if length >= min_len]
            if len(long_idx) < 4:
                return None
            long_extents = [line_extents[i] for i in long_idx]
            med_xmin = int(np.median([x[0] for x in long_extents]))
            med_xmax = int(np.median([x[1] for x in long_extents]))
            margin_tol = int(w_page * 0.08)
            full_idx = [
                i
                for i in long_idx
                if abs(line_extents[i][0] - med_xmin) <= margin_tol
                and abs(line_extents[i][1] - med_xmax) <= margin_tol
            ]
            if len(full_idx) < 4:
                full_idx = long_idx

        fw_lines = [logical_lines[i] for i in full_idx]
        fw_extents = [line_extents[i] for i in full_idx]
        gaps = np.diff(fw_lines)
        if len(gaps) < 3:
            return None

        rounded = (np.array(gaps) / 5).astype(int) * 5
        unique, counts = np.unique(rounded, return_counts=True)
        mode_gap = int(unique[np.argmax(counts)])
        if mode_gap < 5:
            return None

        while len(fw_lines) >= 4:
            gaps = np.diff(fw_lines)
            max_gap_idx = int(np.argmax(gaps))
            max_gap = float(gaps[max_gap_idx])
            if max_gap <= float(mode_gap) * 3.0:
                break
            grp_a_lines = fw_lines[: max_gap_idx + 1]
            grp_a_ext = fw_extents[: max_gap_idx + 1]
            grp_b_lines = fw_lines[max_gap_idx + 1 :]
            grp_b_ext = fw_extents[max_gap_idx + 1 :]
            if len(grp_a_lines) >= len(grp_b_lines):
                fw_lines, fw_extents = grp_a_lines, grp_a_ext
            else:
                fw_lines, fw_extents = grp_b_lines, grp_b_ext

        if len(fw_lines) < 4:
            return None

        y1, y2 = fw_lines[0], fw_lines[-1]
        if border_ok and left_border is not None and right_border is not None:
            x1, x2 = left_border, right_border
            x1_ext = min(ext[0] for ext in fw_extents)
            x2_ext = max(ext[1] for ext in fw_extents)
            x1 = min(x1, x1_ext)
            x2 = max(x2, x2_ext)
        else:
            x1 = min(ext[0] for ext in fw_extents)
            x2 = max(ext[1] for ext in fw_extents)

        m_top = max(8, int(mode_gap * 0.5))
        m_bottom = max(16, int(mode_gap * 0.85))
        m_x = max(24, int(mode_gap * 0.75))
        x = max(0, x1 - m_x)
        y = max(0, y1 - m_top)
        ww = min(w_page, x2 + m_x) - x
        hh = min(h_page, y2 + m_bottom) - y
        if ww <= 0 or hh <= 0:
            return None
        return x, y, ww, hh

    @staticmethod
    def _find_box_by_line_contours(
        binary: np.ndarray,
        h_lines_img: np.ndarray,
        h_page: int,
        w_page: int,
    ) -> Tuple[int, int, int, int] | None:
        min_area_ratio = 0.15
        max_area_ratio = 0.90

        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(1, h_page // 5)))
        v_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel)
        lines = cv2.bitwise_or(h_lines_img, v_lines)
        ck = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 25))
        lines = cv2.morphologyEx(lines, cv2.MORPH_CLOSE, ck, iterations=1)

        contours, _ = cv2.findContours(lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        page_area = float(max(h_page * w_page, 1))
        candidates: List[Tuple[int, float, int, int, int, int]] = []
        for cnt in contours:
            area = float(cv2.contourArea(cnt))
            ratio = area / page_area
            if not (min_area_ratio < ratio < max_area_ratio):
                continue
            x, y, ww, hh = cv2.boundingRect(cnt)
            if ww <= 0 or hh <= 0:
                continue
            aspect = ww / float(hh)
            if not (0.3 < aspect < 3.0):
                continue
            region = h_lines_img[y : y + hh, x : x + ww]
            row_hits = np.sum(region > 0, axis=1)
            n_lines = int(np.sum(row_hits > ww * 0.2))
            candidates.append((n_lines, area, x, y, ww, hh))

        if not candidates:
            return None

        candidates.sort(reverse=True)
        _, _, x, y, ww, hh = candidates[0]
        return x, y, ww, hh

    @staticmethod
    def _find_text_box(bgr: np.ndarray) -> Tuple[int, int, int, int] | None:
        h_page, w_page = bgr.shape[:2]
        binary = PDFChunkMarginCropperService._preprocess(bgr)
        h_lines = PDFChunkMarginCropperService._extract_hlines(binary, h_page, w_page)
        box = PDFChunkMarginCropperService._find_box_by_hlines(binary, h_page, w_page, h_lines)
        if box is not None:
            return box
        return PDFChunkMarginCropperService._find_box_by_line_contours(binary, h_lines, h_page, w_page)

    @staticmethod
    def _detect_handwriting_box(bgr: np.ndarray, ignore_top_ratio: float) -> Tuple[int, int, int, int]:
        h, w = bgr.shape[:2]
        y0 = int(h * ignore_top_ratio)
        roi = bgr[y0:h, 0:w]

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        h_ch, s_ch, v_ch = cv2.split(hsv)

        blue_mask = cv2.inRange(h_ch, 85, 145)
        sat_mask = cv2.inRange(s_ch, 35, 255)
        val_mask = cv2.inRange(v_ch, 0, 230)
        ink = cv2.bitwise_and(blue_mask, cv2.bitwise_and(sat_mask, val_mask))

        if int(np.sum(ink > 0)) < int(roi.shape[0] * roi.shape[1] * 0.0005):
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (5, 5), 0)
            dark = cv2.adaptiveThreshold(
                gray,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV,
                31,
                7,
            )
            horiz_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(int(w * 0.25), 25), 1))
            ruled = cv2.morphologyEx(dark, cv2.MORPH_OPEN, horiz_kernel, iterations=1)
            ink = cv2.subtract(dark, ruled)

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        ink = cv2.morphologyEx(ink, cv2.MORPH_OPEN, kernel, iterations=1)
        ink = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, kernel, iterations=2)

        contours, _ = cv2.findContours(ink, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return 0, 0, w, h

        xs: List[int] = []
        ys: List[int] = []
        xes: List[int] = []
        yes: List[int] = []

        min_area = float(w * h) * 0.00025
        for cnt in contours:
            area = float(cv2.contourArea(cnt))
            if area < min_area:
                continue
            x, y, cw, ch = cv2.boundingRect(cnt)
            if cw <= 0 or ch <= 0:
                continue
            xs.append(x)
            ys.append(y)
            xes.append(x + cw)
            yes.append(y + ch)

        if not xs:
            return 0, 0, w, h

        x1 = min(xs)
        y1 = min(ys) + y0
        x2 = max(xes)
        y2 = max(yes) + y0

        pad_x = int(w * 0.04)
        pad_y = int(h * 0.02)
        x1 = max(0, x1 - pad_x)
        x2 = min(w, x2 + pad_x)
        y1 = max(0, y1 - pad_y)
        y2 = min(h, y2 + pad_y)

        if (x2 - x1) < int(w * 0.25) or (y2 - y1) < int(h * 0.12):
            return 0, 0, w, h

        return x1, y1, x2, y2

    @staticmethod
    def _detect_text_region_box(bgr: np.ndarray, ignore_top_ratio: float = 0.0) -> Tuple[int, int, int, int]:
        h, w = bgr.shape[:2]
        y0 = int(h * ignore_top_ratio)
        roi = bgr[y0:h, 0:w]

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)

        th = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            31,
            7,
        )

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, kernel, iterations=2)
        th = cv2.dilate(th, kernel, iterations=1)

        contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return 0, 0, w, h

        xs: List[int] = []
        ys: List[int] = []
        xes: List[int] = []
        yes: List[int] = []

        min_area = float(w * h) * 0.0003
        for cnt in contours:
            area = float(cv2.contourArea(cnt))
            if area < min_area:
                continue
            x, y, cw, ch = cv2.boundingRect(cnt)
            if cw <= 0 or ch <= 0:
                continue
            xs.append(x)
            ys.append(y)
            xes.append(x + cw)
            yes.append(y + ch)

        if not xs:
            return 0, 0, w, h

        x1 = min(xs)
        y1 = min(ys) + y0
        x2 = max(xes)
        y2 = max(yes) + y0

        pad_x = int(w * 0.02)
        pad_y = int(h * 0.02)

        x1 = max(0, x1 - pad_x)
        y1 = max(0, y1 - pad_y)
        x2 = min(w, x2 + pad_x)
        y2 = min(h, y2 + pad_y)

        if (x2 - x1) < int(w * 0.35) or (y2 - y1) < int(h * 0.35):
            return 0, 0, w, h

        return x1, y1, x2, y2

    @staticmethod
    def _handwriting_score_in_box(bgr: np.ndarray, box: Tuple[int, int, int, int]) -> Tuple[float, float]:
        h, w = bgr.shape[:2]
        x1, y1, x2, y2 = box
        x1 = max(0, min(int(x1), w))
        x2 = max(0, min(int(x2), w))
        y1 = max(0, min(int(y1), h))
        y2 = max(0, min(int(y2), h))
        if x2 <= x1 or y2 <= y1:
            return 0.0, 0.0

        roi = bgr[y1:y2, x1:x2]
        rh, rw = roi.shape[:2]
        if rh <= 0 or rw <= 0:
            return 0.0, 0.0

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        h_ch, s_ch, v_ch = cv2.split(hsv)
        blue_mask = cv2.inRange(h_ch, 85, 145)
        sat_mask = cv2.inRange(s_ch, 35, 255)
        val_mask = cv2.inRange(v_ch, 0, 230)
        ink = cv2.bitwise_and(blue_mask, cv2.bitwise_and(sat_mask, val_mask))

        if int(np.sum(ink > 0)) < int(rh * rw * 0.0005):
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (5, 5), 0)
            dark = cv2.adaptiveThreshold(
                gray,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV,
                31,
                7,
            )
            horiz_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(int(rw * 0.25), 25), 1))
            ruled = cv2.morphologyEx(dark, cv2.MORPH_OPEN, horiz_kernel, iterations=1)
            ink = cv2.subtract(dark, ruled)

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        ink = cv2.morphologyEx(ink, cv2.MORPH_OPEN, kernel, iterations=1)
        ink = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, kernel, iterations=2)

        area = float(rh * rw)
        if area <= 0:
            return 0.0, 0.0
        ink_ratio = float(np.sum(ink > 0)) / area

        contours, _ = cv2.findContours(ink, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return ink_ratio, 0.0

        largest = 0.0
        for cnt in contours:
            a = float(cv2.contourArea(cnt))
            if a > largest:
                largest = a
        largest_ratio = largest / area
        return ink_ratio, largest_ratio

    @staticmethod
    def _is_handwriting_box_valid(bgr: np.ndarray, box: Tuple[int, int, int, int]) -> bool:
        ink_ratio, largest_ratio = PDFChunkMarginCropperService._handwriting_score_in_box(bgr, box)
        return (largest_ratio >= 0.010) or (ink_ratio >= 0.006)

    @staticmethod
    def _refine_box_to_handwriting(
        bgr: np.ndarray,
        box: Tuple[int, int, int, int],
        ignore_top_ratio: float,
        pad_x_ratio: float = 0.02,
        pad_y_ratio: float = 0.02,
    ) -> Tuple[int, int, int, int] | None:
        h, w = bgr.shape[:2]
        x1, y1, x2, y2 = box
        x1 = max(0, min(int(x1), w))
        x2 = max(0, min(int(x2), w))
        y1 = max(0, min(int(y1), h))
        y2 = max(0, min(int(y2), h))
        if x2 <= x1 or y2 <= y1:
            return None

        roi = bgr[y1:y2, x1:x2]
        rh, rw = roi.shape[:2]
        if rh <= 0 or rw <= 0:
            return None

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        h_ch, s_ch, v_ch = cv2.split(hsv)
        blue_mask = cv2.inRange(h_ch, 85, 145)
        sat_mask = cv2.inRange(s_ch, 35, 255)
        val_mask = cv2.inRange(v_ch, 0, 230)
        ink = cv2.bitwise_and(blue_mask, cv2.bitwise_and(sat_mask, val_mask))

        if int(np.sum(ink > 0)) < int(rh * rw * 0.0005):
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (5, 5), 0)
            dark = cv2.adaptiveThreshold(
                gray,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV,
                31,
                7,
            )
            horiz_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(int(rw * 0.25), 25), 1))
            ruled = cv2.morphologyEx(dark, cv2.MORPH_OPEN, horiz_kernel, iterations=1)
            ink = cv2.subtract(dark, ruled)

        ignore_px = int(h * ignore_top_ratio) - y1
        if ignore_px > 0:
            ink[: min(ignore_px, ink.shape[0]), :] = 0

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        ink = cv2.morphologyEx(ink, cv2.MORPH_OPEN, kernel, iterations=1)
        ink = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, kernel, iterations=2)

        contours, _ = cv2.findContours(ink, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None

        min_keep_area = float(rw * rh) * 0.001
        xs: list[int] = []
        ys: list[int] = []
        xes: list[int] = []
        yes: list[int] = []
        for cnt in contours:
            a = float(cv2.contourArea(cnt))
            if a < min_keep_area:
                continue
            cx, cy, cww, chh = cv2.boundingRect(cnt)
            if cww <= 0 or chh <= 0:
                continue
            xs.append(cx)
            ys.append(cy)
            xes.append(cx + cww)
            yes.append(cy + chh)

        if not xs:
            return None

        rx1 = min(xs)
        ry1 = min(ys)
        rx2 = max(xes)
        ry2 = max(yes)

        pad_x = int(rw * pad_x_ratio)
        pad_y = int(rh * pad_y_ratio)
        rx1 = max(0, rx1 - pad_x)
        rx2 = min(rw, rx2 + pad_x)
        ry1 = max(0, ry1 - pad_y)
        ry2 = min(rh, ry2 + pad_y)

        out_x1 = x1 + rx1
        out_y1 = y1 + ry1
        out_x2 = x1 + rx2
        out_y2 = y1 + ry2
        if out_x2 <= out_x1 or out_y2 <= out_y1:
            return None

        if (out_x2 - out_x1) < int(w * 0.25) or (out_y2 - out_y1) < int(h * 0.12):
            return None

        return out_x1, out_y1, out_x2, out_y2

    @staticmethod
    def _detect_target_box(bgr: np.ndarray) -> Tuple[int, int, int, int]:
        h, w = bgr.shape[:2]

        ignore_top_ratio = 0.18

        box = PDFChunkMarginCropperService._find_text_box(bgr)
        if box is not None:
            x, y, ww, hh = box
            pad = 10
            x1 = max(0, x - pad)
            y1 = max(0, y - pad)
            x2 = min(w, x + ww + pad)
            y2 = min(h, y + hh + pad)
            if x2 > x1 and y2 > y1:
                if PDFChunkMarginCropperService._is_handwriting_box_valid(bgr, (x1, y1, x2, y2)):
                    refined = PDFChunkMarginCropperService._refine_box_to_handwriting(
                        bgr,
                        (x1, y1, x2, y2),
                        ignore_top_ratio=ignore_top_ratio,
                    )
                    if refined is not None:
                        return refined
                    return x1, y1, x2, y2

        hx1, hy1, hx2, hy2 = PDFChunkMarginCropperService._detect_handwriting_box(
            bgr, ignore_top_ratio=ignore_top_ratio
        )
        is_full_page = hx1 == 0 and hy1 == 0 and hx2 == w and hy2 == h
        if (hx2 - hx1) > 0 and (hy2 - hy1) > 0 and not is_full_page:
            refined = PDFChunkMarginCropperService._refine_box_to_handwriting(
                bgr,
                (hx1, hy1, hx2, hy2),
                ignore_top_ratio=ignore_top_ratio,
            )
            if refined is not None:
                return refined
            return hx1, hy1, hx2, hy2

        tx1, ty1, tx2, ty2 = PDFChunkMarginCropperService._detect_text_region_box(bgr, ignore_top_ratio=ignore_top_ratio)
        text_full = tx1 == 0 and ty1 == 0 and tx2 == w and ty2 == h
        if (tx2 - tx1) > 0 and (ty2 - ty1) > 0 and not text_full:
            refined = PDFChunkMarginCropperService._refine_box_to_handwriting(
                bgr,
                (tx1, ty1, tx2, ty2),
                ignore_top_ratio=ignore_top_ratio,
            )
            if refined is not None:
                return refined
            return tx1, ty1, tx2, ty2

        return int(w * 0.05), int(h * 0.25), int(w * 0.95), int(h * 0.92)

    @staticmethod
    def _crop_to_box(image: Image.Image, box: Tuple[int, int, int, int]) -> Image.Image:
        bgr = PDFChunkMarginCropperService._pil_to_bgr(image)
        x1, y1, x2, y2 = box
        x1 = max(0, min(x1, bgr.shape[1]))
        x2 = max(0, min(x2, bgr.shape[1]))
        y1 = max(0, min(y1, bgr.shape[0]))
        y2 = max(0, min(y2, bgr.shape[0]))
        if x2 <= x1 or y2 <= y1:
            return image.convert("RGB")
        cropped = bgr[y1:y2, x1:x2]
        return PDFChunkMarginCropperService._bgr_to_pil(cropped)

    @staticmethod
    def _mark_box(image: Image.Image, box: Tuple[int, int, int, int]) -> Image.Image:
        bgr = PDFChunkMarginCropperService._pil_to_bgr(image)
        x1, y1, x2, y2 = box
        x1 = max(0, min(x1, bgr.shape[1] - 1))
        x2 = max(0, min(x2, bgr.shape[1] - 1))
        y1 = max(0, min(y1, bgr.shape[0] - 1))
        y2 = max(0, min(y2, bgr.shape[0] - 1))
        if x2 <= x1 or y2 <= y1:
            return image.convert("RGB")

        thickness = max(3, int(min(bgr.shape[0], bgr.shape[1]) * 0.004))
        cv2.rectangle(bgr, (x1, y1), (x2, y2), (0, 0, 255), thickness)
        return PDFChunkMarginCropperService._bgr_to_pil(bgr)

    @staticmethod
    def _render_pdf_to_images(pdf_bytes: bytes, dpi: int) -> List[Image.Image]:
        if dpi <= 0:
            raise ValueError("dpi must be > 0")

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        images: List[Image.Image] = []

        zoom = float(dpi) / 72.0
        matrix = fitz.Matrix(zoom, zoom)

        for page in doc:
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            mode = "RGB" if pix.n < 4 else "RGBA"
            img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
            images.append(img)

        doc.close()
        return images

    @staticmethod
    def process_pdf(pdf_bytes: bytes, chunk_size: int, dpi: int = 200, mode: str = "crop") -> Dict[str, Any]:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be > 0")

        mode = (mode or "crop").lower().strip()
        if mode not in {"crop", "mark"}:
            raise ValueError("mode must be 'crop' or 'mark'")

        images = PDFChunkMarginCropperService._render_pdf_to_images(pdf_bytes=pdf_bytes, dpi=dpi)
        if not images:
            raise ValueError("No pages found in PDF")

        out_images: List[Image.Image] = []
        for idx, img in enumerate(images):
            page_number = idx + 1
            is_first_of_chunk = ((page_number - 1) % chunk_size) == 0
            if is_first_of_chunk:
                out_images.append(img.convert("RGB"))
            else:
                bgr = PDFChunkMarginCropperService._pil_to_bgr(img)
                if not PDFChunkMarginCropperService._has_budget_logo(bgr):
                    out_images.append(img.convert("RGB"))
                else:
                    box = PDFChunkMarginCropperService._detect_target_box(bgr)
                    template_id = PDFChunkMarginCropperService._detect_budget_template_id(bgr)
                    box = PDFChunkMarginCropperService._apply_budget_header_floor(box, bgr.shape[0], template_id)
                    box = PDFChunkMarginCropperService._stabilize_budget_box(
                        box,
                        h=bgr.shape[0],
                        w=bgr.shape[1],
                        template_id=template_id,
                    )
                    box = PDFChunkMarginCropperService._force_full_width_box(box, h=bgr.shape[0], w=bgr.shape[1])
                    if mode == "mark":
                        out_images.append(PDFChunkMarginCropperService._mark_box(img, box).convert("RGB"))
                    else:
                        out_images.append(PDFChunkMarginCropperService._crop_to_box(img, box).convert("RGB"))

        pdf_buffer = io.BytesIO()
        first = out_images[0]
        rest = out_images[1:]
        first.save(pdf_buffer, format="PDF", save_all=True, append_images=rest)
        pdf_buffer.seek(0)

        return {
            "pdf_bytes": pdf_buffer.getvalue(),
            "page_count": len(out_images),
            "chunk_size": chunk_size,
        }
