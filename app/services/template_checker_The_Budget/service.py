import io
from typing import Dict, Any

import numpy as np
import cv2
from PIL import Image


class TemplateCheckerTheBudgetService:
    """Detects which 'THE BUDGET' page layout is present.

    Heuristic (header-only):
    - Template 1: the prominent 'THE BUDGET' logo block is on the RIGHT side.
    - Template 2: the prominent 'THE BUDGET' logo block is on the LEFT side.

    Returns template_id as 1 or 2.
    """

    @staticmethod
    def detect_template(image_bytes: bytes) -> Dict[str, Any]:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

        H, W = img.shape[:2]

        top = int(H * 0.00)
        bottom = int(H * 0.40)
        roi = img[top:bottom, 0:W]
        roi_h, roi_w = roi.shape[:2]

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)

        _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 3))
        th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, kernel, iterations=1)

        mid = roi_w // 2
        left_ink = int(np.sum(th[:, :mid] > 0))
        right_ink = int(np.sum(th[:, mid:] > 0))

        left_ratio = left_ink / float((roi_h * max(mid, 1)) + 1e-6)
        right_ratio = right_ink / float((roi_h * max(roi_w - mid, 1)) + 1e-6)

        template_id = 1
        reason = "Default to Template 1 (logo right)"

        if left_ratio > right_ratio * 1.10:
            template_id = 2
            reason = f"More header ink on LEFT (left_ratio={left_ratio:.4f} > right_ratio={right_ratio:.4f}); Template 2"
        elif right_ratio > left_ratio * 1.10:
            template_id = 1
            reason = f"More header ink on RIGHT (right_ratio={right_ratio:.4f} > left_ratio={left_ratio:.4f}); Template 1"
        else:
            template_id = 1
            reason = f"Near-tie (left_ratio={left_ratio:.4f}, right_ratio={right_ratio:.4f}); default Template 1"

        return {
            "template_id": template_id,
            "reason": reason,
            "image_size": {"width": W, "height": H},
            "roi": {"top": top, "bottom": bottom, "left": 0, "right": W},
            "metrics": {"left_ratio": left_ratio, "right_ratio": right_ratio},
        }
