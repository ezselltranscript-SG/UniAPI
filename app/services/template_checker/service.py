import io
from typing import Dict, Any

import numpy as np
import cv2
from PIL import Image


class TemplateCheckerService:
    """Detects which page template is present using OpenCV on the header region.

    Heuristic:
    - Template 2 (NT): large rectangular box anchored on the right side of the header.
    - Template 1: a wide centered box across the header (not right-anchored).
    """

    @staticmethod
    def detect_template(image_bytes: bytes) -> Dict[str, Any]:
        # Decode image to OpenCV BGR
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            # Fallback via PIL if imdecode fails
            pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

        H, W = img.shape[:2]

        # Header ROI
        top = int(H * 0.02)
        bottom = int(H * 0.45)
        roi = img[top:bottom, 0:W]
        roi_h, roi_w = roi.shape[:2]

        # Preprocess
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        # Light blur to stabilize edges
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blur, 60, 180)
        # Dilate to connect lines
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        edges = cv2.dilate(edges, kernel, iterations=1)

        # Find contours
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        candidates = []
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            area = w * h
            area_ratio = area / float(roi_w * roi_h)
            if area_ratio < 0.01 or area_ratio > 0.6:
                continue
            ar = w / float(h + 1e-6)
            # Rectangles that could be header boxes/tables
            if 0.8 <= ar <= 5.0 and h > roi_h * 0.07:
                candidates.append({
                    "x": x, "y": y, "w": w, "h": h,
                    "area_ratio": area_ratio,
                    "x_center": x + w / 2.0
                })

        # Decision rules
        template_id = 1
        reason = "Default to Template 1"

        if candidates:
            # Right-anchored box present? (x starting beyond 55% of width or center beyond 62%)
            right_boxes = [c for c in candidates if c["x"] > 0.55 * roi_w or c["x_center"] > 0.62 * roi_w]
            centered_wide = [c for c in candidates if c["x"] < 0.2 * roi_w and c["w"] > 0.5 * roi_w]

            if right_boxes and not centered_wide:
                template_id = 2
                rb = max(right_boxes, key=lambda c: c["area_ratio"])  # most prominent
                reason = f"Right-anchored header box detected at x={rb['x']},w={rb['w']} (Template 2)"
            elif centered_wide and not right_boxes:
                template_id = 1
                cb = max(centered_wide, key=lambda c: c["area_ratio"])
                reason = f"Centered wide header box detected at x={cb['x']},w={cb['w']} (Template 1)"
            else:
                # If both types appear, prefer right-anchored as Template 2
                if right_boxes:
                    template_id = 2
                    rb = max(right_boxes, key=lambda c: c["area_ratio"])  # most prominent
                    reason = f"Both patterns; prefer right-anchored at x={rb['x']} (Template 2)"
                else:
                    template_id = 1
                    reason = "Ambiguous; defaulting to Template 1"

        return {
            "template_id": template_id,
            "reason": reason,
            "image_size": {"width": W, "height": H},
            "roi": {"top": top, "bottom": bottom, "left": 0, "right": W},
            "candidates": candidates[:10],
        }
