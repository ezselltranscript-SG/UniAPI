from __future__ import annotations

import base64
import io
import json
import os
from dataclasses import dataclass
from typing import Any, Sequence

from PIL import Image


class VisionReviewError(RuntimeError):
    """Raised when a PDF cannot be reviewed by the configured vision model."""


@dataclass(frozen=True)
class VisionReviewPlan:
    """Validated page-level actions returned by the vision workflow."""

    rotations: dict[int, int]
    letter_start_pages: list[int]
    blank_after_source_pages: list[int]
    model: str


class PDFVisionReviewer:
    """Review rotations and letter boundaries as separate vision tasks."""

    DEFAULT_MODEL = "gpt-5.6-terra"
    MAX_PAGES = 80
    ROTATION_BATCH_SIZE = 8
    BOUNDARY_BATCH_SIZE = 6
    BATCH_ATTEMPTS = 2

    _ROTATION_SCHEMA = {
        "type": "object",
        "properties": {
            "page_rotations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "page": {"type": "integer"},
                        "degrees_clockwise": {"type": "integer", "enum": [0, 90, 180, 270]},
                    },
                    "required": ["page", "degrees_clockwise"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["page_rotations"],
        "additionalProperties": False,
    }
    _BOUNDARY_SCHEMA = {
        "type": "object",
        "properties": {
            "boundaries": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "next_page": {"type": "integer"},
                        "starts_new_letter": {"type": "boolean"},
                    },
                    "required": ["next_page", "starts_new_letter"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["boundaries"],
        "additionalProperties": False,
    }

    def __init__(self, *, client: Any | None = None):
        self._client = client

    def review(self, previews: Sequence[Image.Image], *, model: str | None = None) -> VisionReviewPlan:
        if not previews:
            raise VisionReviewError("The uploaded PDF has no pages to review")
        if len(previews) > self.MAX_PAGES:
            raise VisionReviewError(
                f"Vision review supports up to {self.MAX_PAGES} pages per PDF; received {len(previews)}"
            )

        selected_model = (model or os.getenv("PDF_NORMALIZER_VISION_MODEL") or self.DEFAULT_MODEL).strip()
        if not selected_model:
            raise VisionReviewError("A vision model must be configured")

        client = self._client or self._create_client()
        try:
            rotations = self._review_rotations(client, previews, model=selected_model)
            letter_starts = self._review_letter_boundaries(client, previews, model=selected_model)
            payload = {
                "page_rotations": [
                    {"page": page, "degrees_clockwise": rotations[page]}
                    for page in sorted(rotations)
                ],
                "letter_start_pages": letter_starts,
            }
            return self._validate_plan(payload, page_count=len(previews), model=selected_model)
        except VisionReviewError:
            raise
        except Exception as exc:
            raise VisionReviewError(f"Vision review failed: {exc}") from exc

    @staticmethod
    def _create_client() -> Any:
        api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
        if not api_key:
            raise VisionReviewError(
                "OPENAI_API_KEY is required for vision review. "
                "Set review_mode=heuristic only when you intentionally want the non-LLM fallback."
            )
        try:
            import openai
        except ImportError as exc:
            raise VisionReviewError("The OpenAI SDK is not installed") from exc
        from app.config import AI_MAX_RETRIES, AI_REQUEST_TIMEOUT_SECONDS

        return openai.OpenAI(
            api_key=api_key,
            timeout=AI_REQUEST_TIMEOUT_SECONDS,
            max_retries=AI_MAX_RETRIES,
        )

    def _review_rotations(
        self,
        client: Any,
        previews: Sequence[Image.Image],
        *,
        model: str,
    ) -> dict[int, int]:
        rotations: dict[int, int] = {}
        page_numbers = list(range(1, len(previews) + 1))
        for offset in range(0, len(page_numbers), self.ROTATION_BATCH_SIZE):
            batch_pages = page_numbers[offset : offset + self.ROTATION_BATCH_SIZE]
            batch_previews = [previews[page - 1] for page in batch_pages]
            last_error: VisionReviewError | None = None
            for _attempt in range(self.BATCH_ATTEMPTS):
                try:
                    payload = self._request_json(
                        client,
                        model=model,
                        schema_name="pdf_page_rotations",
                        schema=self._ROTATION_SCHEMA,
                        content=self._build_rotation_input(batch_previews, batch_pages, model=model),
                    )
                    rotations.update(
                        self._validate_rotation_batch(payload, expected_pages=batch_pages)
                    )
                    break
                except VisionReviewError as exc:
                    last_error = exc
            else:
                raise VisionReviewError(
                    f"Rotation batch {batch_pages[0]}-{batch_pages[-1]} failed after "
                    f"{self.BATCH_ATTEMPTS} attempts: {last_error}"
                )
        return rotations

    def _review_letter_boundaries(
        self,
        client: Any,
        previews: Sequence[Image.Image],
        *,
        model: str,
    ) -> list[int]:
        if len(previews) == 1:
            return [1]

        letter_starts = [1]
        next_pages = list(range(2, len(previews) + 1))
        for offset in range(0, len(next_pages), self.BOUNDARY_BATCH_SIZE):
            batch_next_pages = next_pages[offset : offset + self.BOUNDARY_BATCH_SIZE]
            last_error: VisionReviewError | None = None
            for _attempt in range(self.BATCH_ATTEMPTS):
                try:
                    payload = self._request_json(
                        client,
                        model=model,
                        schema_name="pdf_letter_boundaries",
                        schema=self._BOUNDARY_SCHEMA,
                        content=self._build_boundary_input(previews, batch_next_pages, model=model),
                    )
                    decisions = self._validate_boundary_batch(
                        payload,
                        expected_next_pages=batch_next_pages,
                    )
                    break
                except VisionReviewError as exc:
                    last_error = exc
            else:
                raise VisionReviewError(
                    f"Boundary batch {batch_next_pages[0]}-{batch_next_pages[-1]} failed after "
                    f"{self.BATCH_ATTEMPTS} attempts: {last_error}"
                )
            letter_starts.extend(page for page, starts_new in decisions.items() if starts_new)
        return sorted(letter_starts)

    @classmethod
    def _request_json(
        cls,
        client: Any,
        *,
        model: str,
        schema_name: str,
        schema: dict[str, object],
        content: list[dict[str, object]],
    ) -> object:
        request: dict[str, object] = {
            "model": model,
            "store": False,
            "input": [{"role": "user", "content": content}],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        if model.startswith("gpt-5"):
            request["reasoning"] = {"effort": "medium"}

        try:
            response = client.responses.create(**request)
            return json.loads(response.output_text)
        except json.JSONDecodeError as exc:
            raise VisionReviewError(f"{schema_name} review returned invalid JSON") from exc
        except Exception as exc:
            raise VisionReviewError(f"{schema_name} review failed: {exc}") from exc

    @classmethod
    def _build_rotation_input(
        cls,
        previews: Sequence[Image.Image],
        page_numbers: Sequence[int],
        *,
        model: str,
    ) -> list[dict[str, object]]:
        instruction = (
            "Classify the displayed orientation of every scanned page independently. Return the clockwise rotation "
            "needed to make its text and handwriting readable from top to bottom: 0, 90, 180, or 270 degrees. "
            "Inspect the THE BUDGET logo, typed fax header, handwriting baselines, page numbers, signature, and footer. "
            "An upside-down page requires 180. Do not copy a neighboring page's decision. Return every listed page once."
        )
        content: list[dict[str, object]] = [{"type": "input_text", "text": instruction}]
        detail = cls._image_detail(model)
        for page_number, preview in zip(page_numbers, previews):
            content.append({"type": "input_text", "text": f"PDF page {page_number}:"})
            content.append(
                {
                    "type": "input_image",
                    "image_url": cls._image_data_url(preview),
                    "detail": detail,
                }
            )
        return content

    @classmethod
    def _build_boundary_input(
        cls,
        previews: Sequence[Image.Image],
        next_pages: Sequence[int],
        *,
        model: str,
    ) -> list[dict[str, object]]:
        instruction = (
            "For every adjacent-page pair, decide whether the candidate next page definitely starts a different letter. "
            "The front and back of one physical sheet are two pages of the same letter. Page 1/2 and page 2/2 are the "
            "same letter. Repeated THE BUDGET branding or standard form fields are not evidence of a new letter. A reverse "
            "side or continuation normally keeps the same handwriting, topic, sender, or page numbering. Mark true only "
            "when a changed handwritten sender identity/address/date/heading, a different writing style, or a completed "
            "signature followed by a fresh letter clearly proves a boundary. If uncertain, return false. Return every "
            "listed next_page exactly once."
        )
        content: list[dict[str, object]] = [{"type": "input_text", "text": instruction}]
        detail = cls._image_detail(model)
        for next_page in next_pages:
            content.append(
                {
                    "type": "input_text",
                    "text": f"Boundary before PDF page {next_page}; previous page {next_page - 1}:",
                }
            )
            content.append(
                {
                    "type": "input_image",
                    "image_url": cls._image_data_url(previews[next_page - 2]),
                    "detail": detail,
                }
            )
            content.append({"type": "input_text", "text": f"Candidate PDF page {next_page}:"})
            content.append(
                {
                    "type": "input_image",
                    "image_url": cls._image_data_url(previews[next_page - 1]),
                    "detail": detail,
                }
            )
        return content

    @staticmethod
    def _image_detail(model: str) -> str:
        return "original" if model.startswith("gpt-5.6") else "high"

    @staticmethod
    def _image_data_url(image: Image.Image) -> str:
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="JPEG", quality=88, optimize=True)
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{encoded}"

    @staticmethod
    def _validate_rotation_batch(payload: object, *, expected_pages: Sequence[int]) -> dict[int, int]:
        if not isinstance(payload, dict) or not isinstance(payload.get("page_rotations"), list):
            raise VisionReviewError("Rotation review returned an invalid plan")

        rotations: dict[int, int] = {}
        for item in payload["page_rotations"]:
            if not isinstance(item, dict):
                raise VisionReviewError("Rotation review returned an invalid entry")
            page = item.get("page")
            degrees = item.get("degrees_clockwise")
            if not isinstance(page, int) or not isinstance(degrees, int):
                raise VisionReviewError("Rotation review returned a non-integer decision")
            if page in rotations or degrees not in {0, 90, 180, 270}:
                raise VisionReviewError("Rotation review returned an invalid decision")
            rotations[page] = degrees

        if set(rotations) != set(expected_pages):
            raise VisionReviewError("Rotation review must decide every page in its batch exactly once")
        return rotations

    @staticmethod
    def _validate_boundary_batch(
        payload: object,
        *,
        expected_next_pages: Sequence[int],
    ) -> dict[int, bool]:
        if not isinstance(payload, dict) or not isinstance(payload.get("boundaries"), list):
            raise VisionReviewError("Letter-boundary review returned an invalid plan")

        decisions: dict[int, bool] = {}
        for item in payload["boundaries"]:
            if not isinstance(item, dict):
                raise VisionReviewError("Letter-boundary review returned an invalid entry")
            next_page = item.get("next_page")
            starts_new = item.get("starts_new_letter")
            if not isinstance(next_page, int) or not isinstance(starts_new, bool) or next_page in decisions:
                raise VisionReviewError("Letter-boundary review returned an invalid decision")
            decisions[next_page] = starts_new

        if set(decisions) != set(expected_next_pages):
            raise VisionReviewError("Letter-boundary review must decide every boundary in its batch exactly once")
        return decisions

    @staticmethod
    def _validate_plan(payload: object, *, page_count: int, model: str) -> VisionReviewPlan:
        if not isinstance(payload, dict):
            raise VisionReviewError("Vision review returned an invalid plan")

        rotations = PDFVisionReviewer._validate_rotation_batch(
            {"page_rotations": payload.get("page_rotations", [])},
            expected_pages=list(range(1, page_count + 1)),
        )

        letter_starts = payload.get("letter_start_pages", [])
        if not isinstance(letter_starts, list) or any(
            not isinstance(page, int) or page < 1 or page > page_count for page in letter_starts
        ):
            raise VisionReviewError("Vision review returned invalid letter-start pages")

        letter_start_pages = sorted(set(letter_starts))
        if not letter_start_pages or letter_start_pages[0] != 1:
            raise VisionReviewError("Vision review must identify page 1 as the first letter start")

        letter_ends = [page - 1 for page in letter_start_pages[1:]] + [page_count]
        blank_after = [
            end
            for start, end in zip(letter_start_pages, letter_ends)
            if (end - start + 1) % 2 == 1
        ]

        return VisionReviewPlan(
            rotations=rotations,
            letter_start_pages=letter_start_pages,
            blank_after_source_pages=blank_after,
            model=model,
        )
