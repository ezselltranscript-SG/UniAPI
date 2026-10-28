from __future__ import annotations

import base64
import io
import json
import os
import re
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Mapping, Sequence

from PIL import Image


class VisionReviewError(RuntimeError):
    """Raised when a PDF cannot be reviewed by the configured vision model."""


@dataclass(frozen=True)
class BatchHeader:
    """Batch details handwritten at the top of a batch's first page; 0 means not found."""

    number: int = 0
    received_month: int = 0
    received_day: int = 0
    sheets_per_letter: int = 0
    letter_count: int = 0


@dataclass(frozen=True)
class VisionReviewPlan:
    """Validated page-level actions returned by the vision workflow."""

    rotations: dict[int, int]
    letter_start_pages: list[int]
    blank_after_source_pages: list[int]
    model: str
    provider: str = "openai"
    rotation_sources: dict[int, str] = field(default_factory=dict)
    judge_status: str = "skipped"
    judge_retries: int = 0
    judge_issues: list[str] = field(default_factory=list)
    batch: BatchHeader = field(default_factory=BatchHeader)


@dataclass(frozen=True)
class _PageCheck:
    """The judge's reading of one scanned page in the finished document."""

    text_top_points: str
    starts_new_letter: bool
    note: str


class PDFVisionReviewer:
    """Review rotations and letter boundaries as separate vision tasks."""

    DEFAULT_MODEL = "gpt-5.6-terra"
    DEFAULT_PROVIDER = "openai"
    MAX_PAGES = 80
    ROTATION_BATCH_SIZE = 8
    BOUNDARY_BATCH_SIZE = 6
    JUDGE_BATCH_SIZE = 8
    BATCH_ATTEMPTS = 3
    JUDGE_RETRIES = 2

    _DIRECTIONS = ("up", "right", "down", "left")
    _ROTATION_SCHEMA = {
        "type": "object",
        "properties": {
            "page_orientations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "page": {"type": "integer"},
                        "text_top_points": {"type": "string", "enum": list(_DIRECTIONS)},
                    },
                    "required": ["page", "text_top_points"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["page_orientations"],
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
    _JUDGE_SCHEMA = {
        "type": "object",
        "properties": {
            "page_checks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "output_page": {"type": "integer"},
                        "text_top_points": {"type": "string", "enum": list(_DIRECTIONS)},
                        "starts_new_letter": {"type": "boolean"},
                        "note": {"type": "string"},
                    },
                    "required": ["output_page", "text_top_points", "starts_new_letter", "note"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["page_checks"],
        "additionalProperties": False,
    }
    _BATCH_FIELDS = ("batch_number", "received_month", "received_day", "sheets_per_letter", "letter_count")
    _BATCH_SCHEMA = {
        "type": "object",
        "properties": {name: {"type": "integer"} for name in _BATCH_FIELDS},
        "required": list(_BATCH_FIELDS),
        "additionalProperties": False,
    }
    # Models describe where the top of the writing points far more reliably
    # than they compute a clockwise angle, so the angle is derived here.
    _TOP_DIRECTION_TO_CORRECTION = {"up": 0, "right": 270, "down": 180, "left": 90}
    _ORIENTATION_GUIDE = (
        "Answer \"up\" when the writing reads normally from left to right. Answer \"down\" when the page is upside "
        "down. Answer \"left\" when the lines of writing run from the bottom of the image up toward the top. Answer "
        "\"right\" when the lines of writing run from the top of the image down toward the bottom. Judge from the "
        "letter itself: THE BUDGET logo, printed form labels such as Scribe Name and PLEASE PROOFREAD YOUR LETTER, "
        "handwriting baselines, page numbers, and the signature. A thin fax transmission line along one edge can be "
        "printed in a different direction; do not let it decide."
    )
    _FEEDBACK_DIRECTION_TEXT = {
        "up": "the top edge, so the page reads upright",
        "right": "the right edge, so the page is lying on its side",
        "down": "the bottom edge, so the page is upside down",
        "left": "the left edge, so the page is lying on its side",
    }

    def __init__(self, *, client: Any | None = None):
        self._client = client

    def review(
        self,
        previews: Sequence[Image.Image],
        *,
        provider: str | None = None,
        model: str | None = None,
        rotation_hints: Mapping[int, int] | None = None,
        judge: bool = False,
        judge_rotations: bool = True,
        judge_page_pairs: bool = True,
        read_batch_header: bool = False,
    ) -> VisionReviewPlan:
        """Review every page and return the validated normalization plan.

        ``rotation_hints`` maps 1-based pages to a local orientation estimate.
        Hints never replace the model's decision; a disagreement only sends
        that page through the verification pass.

        ``judge`` adds a final check of the finished document; see
        ``_judge_and_retry``. ``judge_rotations`` and ``judge_page_pairs`` tell
        the judge whether the caller applies the rotations and black pages, so
        it reads the document the caller will produce and only flags what the
        caller acts on.

        ``read_batch_header`` reads the handwritten batch details on page 1.
        The judge also checks letter sizes against the header's sheet count.
        """
        if not previews:
            raise VisionReviewError("The uploaded PDF has no pages to review")
        if len(previews) > self.MAX_PAGES:
            raise VisionReviewError(
                f"Vision review supports up to {self.MAX_PAGES} pages per PDF; received {len(previews)}"
            )

        selected_provider = (
            provider or os.getenv("PDF_NORMALIZER_VISION_PROVIDER") or self.DEFAULT_PROVIDER
        ).strip().lower()
        if selected_provider not in {"openai", "anthropic"}:
            raise VisionReviewError("Vision provider must be 'openai' or 'anthropic'")
        if selected_provider == "anthropic":
            configured_model = os.getenv("PDF_NORMALIZER_ANTHROPIC_MODEL")
            default_model = "claude-opus-5-5"
        else:
            configured_model = os.getenv("PDF_NORMALIZER_VISION_MODEL")
            default_model = self.DEFAULT_MODEL
        selected_model = (model or configured_model or default_model).strip()
        if not selected_model:
            raise VisionReviewError("A vision model must be configured")

        client = self._client or self._create_client(selected_provider)
        try:
            page_count = len(previews)
            proposed = self._review_rotations(
                client,
                previews,
                list(range(1, page_count + 1)),
                provider=selected_provider,
                model=selected_model,
            )
            rotations, rotation_sources = self._verify_rotations(
                client,
                previews,
                proposed,
                rotation_hints or {},
                provider=selected_provider,
                model=selected_model,
            )
            upright = self._upright_previews(previews, rotations)
            batch = (
                self._read_batch_header(client, upright[0], provider=selected_provider, model=selected_model)
                if read_batch_header
                else BatchHeader()
            )
            decisions = self._review_letter_boundaries(
                client,
                upright,
                list(range(2, page_count + 1)),
                provider=selected_provider,
                model=selected_model,
            )
            letter_starts = [1] + [page for page, starts_new in sorted(decisions.items()) if starts_new]

            judge_status, judge_retries, judge_issues = "skipped", 0, []
            if judge:
                try:
                    letter_starts, judge_status, judge_retries, judge_issues = self._judge_and_retry(
                        client,
                        previews,
                        rotations,
                        rotation_sources,
                        letter_starts,
                        provider=selected_provider,
                        model=selected_model,
                        check_rotations=judge_rotations,
                        check_page_pairs=judge_page_pairs,
                        batch=batch,
                    )
                except VisionReviewError:
                    # The plan was already reviewed; a failed final check is
                    # reported to the caller instead of discarding it.
                    judge_status = "error"

            payload = {
                "page_rotations": [
                    {"page": page, "degrees_clockwise": rotations[page]}
                    for page in sorted(rotations)
                ],
                "letter_start_pages": letter_starts,
            }
            plan = self._validate_plan(
                payload,
                page_count=page_count,
                provider=selected_provider,
                model=selected_model,
                rotation_sources=rotation_sources,
            )
            return replace(
                plan,
                judge_status=judge_status,
                judge_retries=judge_retries,
                judge_issues=judge_issues,
                batch=batch,
            )
        except VisionReviewError:
            raise
        except Exception as exc:
            raise VisionReviewError(f"Vision review failed: {exc}") from exc

    @staticmethod
    def _create_client(provider: str) -> Any:
        key_name = "OPENAI_API_KEY" if provider == "openai" else "ANTHROPIC_API_KEY"
        api_key = (os.getenv(key_name) or "").strip()
        if not api_key:
            raise VisionReviewError(
                f"{key_name} is required for {provider} vision review. "
                "Set review_mode=heuristic only when you intentionally want the non-LLM fallback."
            )
        from app.config import AI_MAX_RETRIES, AI_REQUEST_TIMEOUT_SECONDS

        try:
            if provider == "anthropic":
                import anthropic
                return anthropic.Anthropic(
                    api_key=api_key,
                    timeout=AI_REQUEST_TIMEOUT_SECONDS,
                    max_retries=AI_MAX_RETRIES,
                )
            import openai
        except ImportError as exc:
            raise VisionReviewError(f"The {provider} SDK is not installed") from exc

        return openai.OpenAI(
            api_key=api_key,
            timeout=AI_REQUEST_TIMEOUT_SECONDS,
            max_retries=AI_MAX_RETRIES,
        )

    def _review_rotations(
        self,
        client: Any,
        previews: Sequence[Image.Image],
        page_numbers: Sequence[int],
        *,
        provider: str,
        model: str,
        notes: Mapping[int, str] | None = None,
    ) -> dict[int, int]:
        """Return the clockwise correction for each page; ``previews`` align with ``page_numbers``."""
        rotations: dict[int, int] = {}
        for offset in range(0, len(page_numbers), self.ROTATION_BATCH_SIZE):
            batch_pages = list(page_numbers[offset : offset + self.ROTATION_BATCH_SIZE])
            batch_previews = list(previews[offset : offset + self.ROTATION_BATCH_SIZE])
            rotations.update(
                self._request_validated(
                    client,
                    provider=provider,
                    model=model,
                    schema_name="pdf_page_orientations",
                    schema=self._ROTATION_SCHEMA,
                    content=self._build_rotation_input(batch_previews, batch_pages, model=model, notes=notes),
                    validate=lambda payload, pages=batch_pages: self._validate_orientation_batch(
                        payload, expected_pages=pages
                    ),
                    label=f"Rotation batch {batch_pages[0]}-{batch_pages[-1]}",
                )
            )
        return rotations

    def _verify_rotations(
        self,
        client: Any,
        previews: Sequence[Image.Image],
        proposed: dict[int, int],
        rotation_hints: Mapping[int, int],
        *,
        provider: str,
        model: str,
    ) -> tuple[dict[int, int], dict[int, str]]:
        """Take a second look at sideways decisions and local-signal disagreements."""
        rotations = dict(proposed)
        sources = {page: "vision" for page in proposed}
        pages = [
            page
            for page, rotation in sorted(proposed.items())
            if rotation in {90, 270}
            or self._lands_landscape(previews[page - 1], rotation)
            or rotation_hints.get(page, rotation) != rotation
        ]
        if not pages:
            return rotations, sources

        for page, rotation in self._second_look(
            client, previews, proposed, pages, provider=provider, model=model
        ).items():
            rotations[page] = rotation
            sources[page] = "vision_verified" if rotation == proposed[page] else "verification_override"
        return rotations, sources

    def _second_look(
        self,
        client: Any,
        previews: Sequence[Image.Image],
        current: Mapping[int, int],
        pages: Sequence[int],
        *,
        provider: str,
        model: str,
        reported_tops: Mapping[int, str] | None = None,
    ) -> dict[int, int]:
        """Re-review ``pages`` with their current correction applied.

        Models recognize upright and upside-down pages far more reliably than
        they tell 90 from 270, and some describe sideways writing as level.
        Letter scans are portrait pages, so each page is shown standing
        portrait: its current correction, plus a quarter turn when that
        correction would leave it landscape. Any remaining error is then an
        upside-down page, which the second look catches. The quarter turn is
        only a viewpoint; the answers are composed, so a truly landscape page
        still comes out correct.

        ``reported_tops`` carries the judge's reading of a page (where the top
        of the writing pointed in the finished document); it is translated to
        the image the reviewer sees and sent along as feedback.
        """
        probes = {
            page: (current[page] + (90 if self._lands_landscape(previews[page - 1], current[page]) else 0)) % 360
            for page in pages
        }
        notes = {
            page: self._rotation_feedback(page, reported_tops[page], (probes[page] - current[page]) % 360)
            for page in pages
            if reported_tops and page in reported_tops
        }
        probed = [self._rotate_clockwise(previews[page - 1], probes[page]) for page in pages]
        residual = self._review_rotations(
            client, probed, pages, provider=provider, model=model, notes=notes or None
        )
        return {page: (probes[page] + residual[page]) % 360 for page in pages}

    def _review_letter_boundaries(
        self,
        client: Any,
        previews: Sequence[Image.Image],
        next_pages: Sequence[int],
        *,
        provider: str,
        model: str,
        notes: Mapping[int, str] | None = None,
    ) -> dict[int, bool]:
        """Return whether each of ``next_pages`` starts a new letter."""
        decisions: dict[int, bool] = {}
        for offset in range(0, len(next_pages), self.BOUNDARY_BATCH_SIZE):
            batch_next_pages = list(next_pages[offset : offset + self.BOUNDARY_BATCH_SIZE])
            decisions.update(
                self._request_validated(
                    client,
                    provider=provider,
                    model=model,
                    schema_name="pdf_letter_boundaries",
                    schema=self._BOUNDARY_SCHEMA,
                    content=self._build_boundary_input(previews, batch_next_pages, model=model, notes=notes),
                    validate=lambda payload, pages=batch_next_pages: self._validate_boundary_batch(
                        payload, expected_next_pages=pages
                    ),
                    label=f"Boundary batch {batch_next_pages[0]}-{batch_next_pages[-1]}",
                )
            )
        return decisions

    def _judge_and_retry(
        self,
        client: Any,
        previews: Sequence[Image.Image],
        rotations: dict[int, int],
        rotation_sources: dict[int, str],
        letter_starts: list[int],
        *,
        provider: str,
        model: str,
        check_rotations: bool,
        check_page_pairs: bool,
        batch: BatchHeader = BatchHeader(),
    ) -> tuple[list[int], str, int, list[str]]:
        """Have the model read the finished document and redo the pages it flags.

        The judge reads the output page by page: every page turned as planned
        and black pages in place. A page that is not upright goes back through
        the second look, and a disputed letter boundary goes back to the
        boundary review, each with the judge's finding as feedback. A letter
        whose length disagrees with the batch header's sheet count sends its
        boundaries back the same way. The reviewer's new answer is kept, so
        neither the judge nor the header edits the plan directly. This repeats
        until the document passes, a retry changes nothing, or
        ``JUDGE_RETRIES`` retries are spent.

        ``rotations`` and ``rotation_sources`` are updated in place. Returns
        the letter starts, the status, the retries used, and any remaining
        issues as ``"<output page>:<problem>"``, plus ``"batch:<problem>"``
        when the letter count differs from the header.
        """
        page_count = len(previews)
        sheets = batch.sheets_per_letter if check_page_pairs else 0
        retries = 0
        while True:
            layout = self._output_layout(len(previews), letter_starts, include_blanks=check_page_pairs)
            shown = rotations if check_rotations else {page: 0 for page in rotations}
            checks = self._judge_document(client, previews, shown, layout, provider=provider, model=model)
            sideways = {
                page: check.text_top_points
                for page, check in checks.items()
                if check_rotations and check.text_top_points != "up"
            }
            disputed = {
                page: check
                for page, check in checks.items()
                if check_page_pairs and page > 1 and check.starts_new_letter != (page in letter_starts)
            }
            misfits = self._letter_size_misfits(letter_starts, page_count, sheets)
            if not sideways and not disputed and not misfits:
                count_issue = self._letter_count_issue(batch, letter_starts) if check_page_pairs else None
                if count_issue:
                    return letter_starts, "issues_remaining", retries, [count_issue]
                return letter_starts, "passed", retries, []
            if retries == self.JUDGE_RETRIES:
                break
            retries += 1

            changed = False
            if sideways:
                for page, rotation in self._second_look(
                    client,
                    previews,
                    rotations,
                    sorted(sideways),
                    provider=provider,
                    model=model,
                    reported_tops=sideways,
                ).items():
                    if rotation != rotations[page]:
                        rotations[page] = rotation
                        rotation_sources[page] = "judge_override"
                        changed = True
            notes = {page: self._boundary_feedback(page, check) for page, check in disputed.items()}
            for start, (end, length) in misfits.items():
                size_note = self._letter_size_feedback(start, end, length, sheets)
                for page in range(max(2, start), min(end + 1, page_count) + 1):
                    notes[page] = f"{notes[page]} {size_note}" if page in notes else size_note
            if notes:
                decisions = self._review_letter_boundaries(
                    client,
                    self._upright_previews(previews, rotations),
                    sorted(notes),
                    provider=provider,
                    model=model,
                    notes=notes,
                )
                starts = set(letter_starts)
                starts.difference_update(page for page, starts_new in decisions.items() if not starts_new)
                starts.update(page for page, starts_new in decisions.items() if starts_new)
                if sorted(starts) != letter_starts:
                    letter_starts = sorted(starts)
                    changed = True
            if not changed:
                # The reviewer kept its answers, so the document the judge
                # just read is the final one and its findings still stand.
                break

        output_pages = {source: index for index, source in enumerate(layout, start=1) if source is not None}
        issues = [(output_pages[page], f"top_points_{top}") for page, top in sideways.items()]
        issues += [
            (output_pages[page], "starts_new_letter" if check.starts_new_letter else "continues_letter")
            for page, check in disputed.items()
        ]
        issues += [(output_pages[start], f"letter_has_{length}_pages") for start, (_end, length) in misfits.items()]
        remaining = [f"{page}:{problem}" for page, problem in sorted(issues)]
        count_issue = self._letter_count_issue(batch, letter_starts) if check_page_pairs else None
        if count_issue:
            remaining.append(count_issue)
        return letter_starts, "issues_remaining", retries, remaining

    def _read_batch_header(
        self,
        client: Any,
        first_page: Image.Image,
        *,
        provider: str,
        model: str,
    ) -> BatchHeader:
        """Read the batch details handwritten on the first page.

        The header only names the output and checks letter sizes, so a page
        without one, or a failed read, yields an empty header instead of
        failing the review.
        """
        instruction = (
            "This is the first page of a batch of letters scanned for THE BUDGET. Near the top edge someone wrote the "
            "batch details by hand, for example \"BATCH 5  2 Sheets  8\" or \"BATCH #1  25 letters  1 sheet\". "
            "batch_number: the number after BATCH. sheets_per_letter: the number before \"sheet\" or \"sheets\". "
            "letter_count: how many letters are in the batch, either a number followed by \"letters\" or a number "
            "written on its own beside the batch details, sometimes circled; never the fax page counter such as "
            "P 1/3, and never part of a date. received_month and received_day: the month and day on the RECEIVED "
            "stamp (for example RECEIVED JUL 25 gives 7 and 25); when there is no stamp, the date on the fax "
            "transmission line at the top edge. Ignore the letter itself. Use 0 for any value that is not written "
            "or cannot be read."
        )
        content: list[dict[str, object]] = [
            {"type": "input_text", "text": instruction},
            {"type": "input_image", "image_url": self._image_data_url(first_page), "detail": self._image_detail(model)},
        ]
        try:
            return self._request_validated(
                client,
                provider=provider,
                model=model,
                schema_name="pdf_batch_header",
                schema=self._BATCH_SCHEMA,
                content=content,
                validate=self._validate_batch_header,
                label="Batch header",
            )
        except VisionReviewError:
            return BatchHeader()

    @classmethod
    def _validate_batch_header(cls, payload: object) -> BatchHeader:
        if not isinstance(payload, dict) or any(
            not isinstance(payload.get(name), int) or payload[name] < 0 for name in cls._BATCH_FIELDS
        ):
            raise VisionReviewError("Batch header read returned an invalid result")
        month = payload["received_month"] if payload["received_month"] <= 12 else 0
        day = payload["received_day"] if payload["received_day"] <= 31 else 0
        return BatchHeader(
            number=payload["batch_number"],
            received_month=month if month and day else 0,
            received_day=day if month and day else 0,
            sheets_per_letter=payload["sheets_per_letter"] if payload["sheets_per_letter"] <= 8 else 0,
            letter_count=payload["letter_count"],
        )

    @classmethod
    def _letter_size_misfits(
        cls, letter_starts: Sequence[int], page_count: int, sheets_per_letter: int
    ) -> dict[int, tuple[int, int]]:
        """Map each letter that does not fill the header's sheet count to (last page, output length).

        A misread header or a mixed batch would make most letters misfit;
        then the header is not trusted and nothing is returned.
        """
        if not sheets_per_letter:
            return {}
        letter_ends = [page - 1 for page in letter_starts[1:]] + [page_count]
        misfits: dict[int, tuple[int, int]] = {}
        for start, end in zip(letter_starts, letter_ends):
            length = end - start + 1
            length += length % 2
            if length != 2 * sheets_per_letter:
                misfits[start] = (end, length)
        if len(misfits) * 2 > len(letter_starts):
            return {}
        return misfits

    @staticmethod
    def _letter_count_issue(batch: BatchHeader, letter_starts: Sequence[int]) -> str | None:
        if batch.letter_count and batch.letter_count != len(letter_starts):
            return f"batch:found_{len(letter_starts)}_letters_header_says_{batch.letter_count}"
        return None

    @staticmethod
    def _letter_size_feedback(start: int, end: int, length: int, sheets_per_letter: int) -> str:
        sheet_word = "sheet" if sheets_per_letter == 1 else "sheets"
        return (
            f"The batch header says every letter is {sheets_per_letter} {sheet_word} ({2 * sheets_per_letter} "
            f"pages once a blank back is added), but the letter from page {start} to page {end} comes to {length} "
            "pages, so a boundary near it is likely missing or wrong."
        )

    def _judge_document(
        self,
        client: Any,
        previews: Sequence[Image.Image],
        rotations: Mapping[int, int],
        layout: Sequence[int | None],
        *,
        provider: str,
        model: str,
    ) -> dict[int, _PageCheck]:
        """Return the judge's check of every scanned page, keyed by source page.

        ``layout`` lists the output pages in order: a source page number, or
        ``None`` for an inserted black page. Each batch opens with the
        previous scanned page (and any black page after it) as context, so
        letter boundaries are judged across batch edges.
        """
        entries = list(enumerate(layout, start=1))
        output_index = {source: index for index, source in entries if source is not None}
        upright = self._upright_previews(previews, rotations)
        checks: dict[int, _PageCheck] = {}
        for offset in range(0, len(entries), self.JUDGE_BATCH_SIZE):
            batch = entries[offset : offset + self.JUDGE_BATCH_SIZE]
            scanned = [(output_page, source) for output_page, source in batch if source is not None]
            if not scanned:
                continue
            first_source = scanned[0][1]
            context = entries[output_index[first_source - 1] - 1 : offset] if first_source > 1 else []
            expected = [output_page for output_page, _ in scanned]
            result = self._request_validated(
                client,
                provider=provider,
                model=model,
                schema_name="pdf_document_check",
                schema=self._JUDGE_SCHEMA,
                content=self._build_judge_input(upright, batch, context, model=model),
                validate=lambda payload, pages=expected: self._validate_judge_batch(payload, expected_pages=pages),
                label=f"Judge batch {expected[0]}-{expected[-1]}",
            )
            checks.update({source: result[output_page] for output_page, source in scanned})
        return checks

    @classmethod
    def _request_validated(
        cls,
        client: Any,
        *,
        provider: str,
        model: str,
        schema_name: str,
        schema: dict[str, object],
        content: list[dict[str, object]],
        validate: Callable[[object], Any],
        label: str,
    ) -> Any:
        """Request one structured answer and validate it, retrying failed attempts."""
        last_error: VisionReviewError | None = None
        for _attempt in range(cls.BATCH_ATTEMPTS):
            try:
                payload = cls._request_json(
                    client,
                    provider=provider,
                    model=model,
                    schema_name=schema_name,
                    schema=schema,
                    content=content,
                )
                return validate(payload)
            except VisionReviewError as exc:
                last_error = exc
        raise VisionReviewError(f"{label} failed after {cls.BATCH_ATTEMPTS} attempts: {last_error}")

    @classmethod
    def _request_json(
        cls,
        client: Any,
        *,
        provider: str,
        model: str,
        schema_name: str,
        schema: dict[str, object],
        content: list[dict[str, object]],
    ) -> object:
        if provider == "anthropic":
            return cls._request_anthropic_json(
                client, model=model, schema_name=schema_name, schema=schema, content=content
            )

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
    def _request_anthropic_json(
        cls,
        client: Any,
        *,
        model: str,
        schema_name: str,
        schema: dict[str, object],
        content: list[dict[str, object]],
    ) -> object:
        anthropic_content: list[dict[str, object]] = []
        for item in content:
            if item["type"] == "input_text":
                anthropic_content.append({"type": "text", "text": item["text"]})
            else:
                image_url = str(item["image_url"])
                encoded = image_url.split(",", 1)[1]
                anthropic_content.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": encoded,
                        },
                    }
                )
        try:
            # Thinking is always on for current Claude models; a small
            # max_tokens let it consume the budget and return no JSON at all.
            response = client.messages.create(
                model=model,
                max_tokens=16000,
                output_config={
                    "effort": "medium",
                    "format": {"type": "json_schema", "schema": schema},
                },
                messages=[{"role": "user", "content": anthropic_content}],
            )
            stop_reason = getattr(response, "stop_reason", None)
            if stop_reason in {"refusal", "max_tokens"}:
                raise VisionReviewError(f"{schema_name} review stopped early: {stop_reason}")
            text = "".join(
                block.text for block in response.content if getattr(block, "type", None) == "text"
            ).strip()
            if not text:
                raise VisionReviewError(f"{schema_name} review returned an empty response")
            return cls._parse_json_response(text)
        except VisionReviewError:
            raise
        except json.JSONDecodeError as exc:
            raise VisionReviewError(f"{schema_name} review returned invalid JSON") from exc
        except Exception as exc:
            raise VisionReviewError(f"{schema_name} review failed: {exc}") from exc

    @staticmethod
    def _parse_json_response(text: str) -> object:
        """Parse raw JSON or the common Markdown code-fence response from a model."""
        candidate = text.strip()
        fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", candidate, flags=re.DOTALL | re.IGNORECASE)
        if fenced:
            candidate = fenced.group(1).strip()
        return json.loads(candidate)

    @classmethod
    def _build_rotation_input(
        cls,
        previews: Sequence[Image.Image],
        page_numbers: Sequence[int],
        *,
        model: str,
        notes: Mapping[int, str] | None = None,
    ) -> list[dict[str, object]]:
        instruction = (
            "Report the current orientation of every scanned page independently: which edge of the image the TOP "
            f"of the writing faces. {cls._ORIENTATION_GUIDE} Do not copy a neighboring page's answer. Return every "
            "listed page once."
        )
        if notes:
            instruction += (
                " Some pages carry feedback from a reviewer who checked the finished document. Take it into "
                "account, but answer from what you see in the image."
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
            if notes and page_number in notes:
                content.append({"type": "input_text", "text": notes[page_number]})
        return content

    @classmethod
    def _build_boundary_input(
        cls,
        previews: Sequence[Image.Image],
        next_pages: Sequence[int],
        *,
        model: str,
        notes: Mapping[int, str] | None = None,
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
        if notes:
            instruction += (
                " Some boundaries carry feedback from a reviewer who read the finished document. Take it into "
                "account, but decide from what you see in the pages."
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
            if notes and next_page in notes:
                content.append({"type": "input_text", "text": notes[next_page]})
        return content

    @classmethod
    def _build_judge_input(
        cls,
        upright_previews: Sequence[Image.Image],
        batch: Sequence[tuple[int, int | None]],
        context: Sequence[tuple[int, int | None]],
        *,
        model: str,
    ) -> list[dict[str, object]]:
        instruction = (
            "You are the final checker for a scanned batch of handwritten letters to THE BUDGET. The images are the "
            "finished document in print order, after every page was turned upright and black pages were added. The "
            "document is printed double-sided, so a black page follows every letter with an odd number of pages and "
            "every letter starts on a new sheet. Read the document page by page and check each listed scanned output "
            "page. text_top_points: which edge of the image the TOP of the writing faces. "
            f"{cls._ORIENTATION_GUIDE} starts_new_letter: true only when the page clearly begins a different letter "
            "from the scanned page before it: a new sender, heading, date or greeting, or different handwriting after "
            "the previous letter's signature. False when it continues the same letter, such as the back of a sheet or "
            "page 2 of 3 with the same writer and topic. note: when a page is not upright, or a letter boundary or "
            "black page looks wrong, one short sentence on what you saw; otherwise an empty string. Black pages are "
            "listed as text, not images. Report every listed scanned output page once, and do not report context pages."
        )
        content: list[dict[str, object]] = [{"type": "input_text", "text": instruction}]
        detail = cls._image_detail(model)
        for is_context, entries in ((True, context), (False, batch)):
            for output_page, source in entries:
                if source is None:
                    label = "black page added as the blank back of the letter before it"
                    content.append(
                        {
                            "type": "input_text",
                            "text": f"Output page {output_page}{' (context)' if is_context else ''}: {label}.",
                        }
                    )
                    continue
                label = (
                    f"Output page {output_page} (context only, do not report it):"
                    if is_context
                    else f"Output page {output_page}:"
                )
                content.append({"type": "input_text", "text": label})
                content.append(
                    {
                        "type": "input_image",
                        "image_url": cls._image_data_url(upright_previews[source - 1]),
                        "detail": detail,
                    }
                )
        reported = ", ".join(str(output_page) for output_page, source in batch if source is not None)
        content.append({"type": "input_text", "text": f"Report exactly these output pages: {reported}."})
        return content

    @classmethod
    def _rotation_feedback(cls, page: int, reported_top: str, extra_turn: int) -> str:
        """Describe the judge's finding in the frame of the image the reviewer sees."""
        shown_top = cls._DIRECTIONS[(cls._DIRECTIONS.index(reported_top) + extra_turn // 90) % 4]
        return (
            f"Reviewer feedback for PDF page {page}: a reviewer who read the finished document saw the top of the "
            f"writing in this image facing {cls._FEEDBACK_DIRECTION_TEXT[shown_top]}. Check this page again before "
            "answering."
        )

    @staticmethod
    def _boundary_feedback(page: int, check: _PageCheck) -> str:
        finding = "starts a new letter" if check.starts_new_letter else f"continues the letter from page {page - 1}"
        detail = f' Their note: "{check.note}"' if check.note else ""
        return (
            f"Reviewer feedback for the boundary before PDF page {page}: a reviewer who read the finished document "
            f"believes page {page} {finding}.{detail} Check this boundary again before answering."
        )

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
    def _rotate_clockwise(image: Image.Image, rotation: int) -> Image.Image:
        if rotation == 0:
            return image
        return image.rotate(-rotation, expand=True)

    @classmethod
    def _upright_previews(
        cls, previews: Sequence[Image.Image], rotations: Mapping[int, int]
    ) -> list[Image.Image]:
        return [cls._rotate_clockwise(preview, rotations[page]) for page, preview in enumerate(previews, start=1)]

    @staticmethod
    def _lands_landscape(preview: Image.Image, rotation: int) -> bool:
        width, height = preview.size
        if rotation in {90, 270}:
            width, height = height, width
        return width > height * 1.05

    @staticmethod
    def _blank_after_pages(letter_start_pages: Sequence[int], page_count: int) -> list[int]:
        """Return the last page of every letter with an odd number of pages."""
        letter_ends = [page - 1 for page in letter_start_pages[1:]] + [page_count]
        return [
            end
            for start, end in zip(letter_start_pages, letter_ends)
            if (end - start + 1) % 2 == 1
        ]

    @classmethod
    def _output_layout(
        cls, page_count: int, letter_start_pages: Sequence[int], *, include_blanks: bool
    ) -> list[int | None]:
        """List the output pages: source page numbers, with ``None`` for each black page."""
        blank_after = set(cls._blank_after_pages(letter_start_pages, page_count)) if include_blanks else set()
        layout: list[int | None] = []
        for page in range(1, page_count + 1):
            layout.append(page)
            if page in blank_after:
                layout.append(None)
        return layout

    @classmethod
    def _validate_orientation_batch(cls, payload: object, *, expected_pages: Sequence[int]) -> dict[int, int]:
        """Convert a model's per-page orientation answers into clockwise corrections."""
        if not isinstance(payload, dict) or not isinstance(payload.get("page_orientations"), list):
            raise VisionReviewError("Rotation review returned an invalid plan")

        rotations: dict[int, int] = {}
        for item in payload["page_orientations"]:
            if not isinstance(item, dict):
                raise VisionReviewError("Rotation review returned an invalid entry")
            page = item.get("page")
            direction = item.get("text_top_points")
            if not isinstance(page, int) or page in rotations or direction not in cls._TOP_DIRECTION_TO_CORRECTION:
                raise VisionReviewError("Rotation review returned an invalid decision")
            rotations[page] = cls._TOP_DIRECTION_TO_CORRECTION[direction]

        if set(rotations) != set(expected_pages):
            raise VisionReviewError("Rotation review must decide every page in its batch exactly once")
        return rotations

    @classmethod
    def _validate_judge_batch(cls, payload: object, *, expected_pages: Sequence[int]) -> dict[int, _PageCheck]:
        if not isinstance(payload, dict) or not isinstance(payload.get("page_checks"), list):
            raise VisionReviewError("Document check returned an invalid result")

        checks: dict[int, _PageCheck] = {}
        for item in payload["page_checks"]:
            if not isinstance(item, dict):
                raise VisionReviewError("Document check returned an invalid entry")
            page = item.get("output_page")
            direction = item.get("text_top_points")
            starts_new = item.get("starts_new_letter")
            note = item.get("note")
            if (
                not isinstance(page, int)
                or page in checks
                or direction not in cls._DIRECTIONS
                or not isinstance(starts_new, bool)
                or not isinstance(note, str)
            ):
                raise VisionReviewError("Document check returned an invalid decision")
            # Models sometimes also describe a black or context page; only the
            # listed scanned pages count.
            if page in expected_pages:
                checks[page] = _PageCheck(direction, starts_new, note.strip())

        if set(checks) != set(expected_pages):
            raise VisionReviewError("Document check must report every scanned page in its batch exactly once")
        return checks

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
    def _validate_plan(
        payload: object,
        *,
        page_count: int,
        provider: str = "openai",
        model: str,
        rotation_sources: dict[int, str] | None = None,
    ) -> VisionReviewPlan:
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

        return VisionReviewPlan(
            rotations=rotations,
            letter_start_pages=letter_start_pages,
            blank_after_source_pages=PDFVisionReviewer._blank_after_pages(letter_start_pages, page_count),
            provider=provider,
            model=model,
            rotation_sources=dict(rotation_sources or {}),
        )
