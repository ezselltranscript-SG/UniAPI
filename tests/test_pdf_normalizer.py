import fitz
from PIL import Image

from app.services.pdf_normalizer.router import _build_content_disposition
from app.services.pdf_normalizer.service import PDFNormalizerService
from app.services.pdf_normalizer.vision import PDFVisionReviewer, VisionReviewPlan


def _make_letter_pdf(page_count: int = 1) -> bytes:
    document = fitz.open()
    for page_number in range(page_count):
        page = document.new_page(width=612, height=792)
        page.insert_text((72, 90), "THE BUDGET", fontsize=18)
        for line in range(12):
            page.insert_text(
                (72, 140 + line * 28),
                f"This is readable line {line + 1} on page {page_number + 1}.",
                fontsize=12,
            )
    try:
        return document.tobytes()
    finally:
        document.close()


def test_content_disposition_supports_unicode_upload_filenames():
    header = _build_content_disposition(
        "07032026_THE BUDGET 71A •PO Box 249 •Sugarcreek.pdf"
    )

    header.encode("latin-1")
    assert 'filename="07032026_THE BUDGET 71A PO Box 249 Sugarcreek_normalized.pdf"' in header
    assert "filename*=UTF-8''" in header
    assert "%E2%80%A2" in header
    assert "•" not in header


def test_content_disposition_removes_paths_and_header_control_characters():
    header = _build_content_disposition("../../unsafe\r\nname.pdf")

    assert ".." not in header
    assert "\r" not in header
    assert "\n" not in header


def _add_scanned_letter_page(
    document: fitz.Document,
    *,
    letterhead: str | None,
    handwriting: str,
):
    page = document.new_page(width=612, height=792)
    body_start = 260
    if letterhead:
        page.insert_text((72, 80), f"{letterhead} LETTERHEAD", fontsize=20)
        page.insert_text((72, 112), "PO Box 249 - Sugarcreek, OH", fontsize=11)
    else:
        body_start = 100

    for line in range(6):
        page.insert_text(
            (92, body_start + line * 34),
            f"{handwriting} {line + 1}",
            fontsize=16,
            color=(0, 0, 1),
        )


def _make_batch(*pages: tuple[str | None, str]) -> bytes:
    document = fitz.open()
    try:
        for letterhead, handwriting in pages:
            _add_scanned_letter_page(
                document,
                letterhead=letterhead,
                handwriting=handwriting,
            )
        return document.tobytes()
    finally:
        document.close()


def test_normalizer_appends_blank_reverse_side_for_odd_page_count():
    result = PDFNormalizerService.normalize_pdf(
        _make_letter_pdf(),
        auto_rotate=False,
        review_mode="heuristic",
    )
    output = fitz.open(stream=result["pdf_bytes"], filetype="pdf")
    try:
        assert result["input_page_count"] == 1
        assert result["output_page_count"] == 2
        assert result["blank_pages_added"] == 1
        assert output.page_count == 2
        assert output[0].get_text().strip()
        assert output[1].get_text().strip() == ""
        assert output[0].rect == output[1].rect
        placeholder = output[1].get_pixmap(alpha=False)
        assert max(placeholder.samples) == 0
    finally:
        output.close()


def test_normalizer_preserves_even_page_count_without_adding_a_blank_page():
    result = PDFNormalizerService.normalize_pdf(
        _make_letter_pdf(page_count=2),
        auto_rotate=False,
        review_mode="heuristic",
    )
    output = fitz.open(stream=result["pdf_bytes"], filetype="pdf")
    try:
        assert result["output_page_count"] == 2
        assert result["blank_pages_added"] == 0
        assert output.page_count == 2
    finally:
        output.close()


def test_normalizer_detects_and_corrects_rotated_letters():
    source = fitz.open(stream=_make_letter_pdf(), filetype="pdf")
    try:
        for source_rotation, expected_correction in ((90, 270), (180, 180), (270, 90)):
            rotated = fitz.open()
            rotated.insert_pdf(source, rotate=source_rotation)
            try:
                result = PDFNormalizerService.normalize_pdf(
                    rotated.tobytes(),
                    review_mode="heuristic",
                )
            finally:
                rotated.close()

            output = fitz.open(stream=result["pdf_bytes"], filetype="pdf")
            try:
                assert result["applied_rotations"] == [expected_correction]
                assert output[0].rect.height > output[0].rect.width
                assert output[0].rotation == 0
                assert output.page_count == 2
            finally:
                output.close()
    finally:
        source.close()


def test_normalizer_keeps_a_sparse_upright_continuation_page_upright():
    result = PDFNormalizerService.normalize_pdf(
        _make_batch(
            ("ALPHA", "Ada"),
            (None, "Ada"),
        ),
        review_mode="heuristic",
    )
    output = fitz.open(stream=result["pdf_bytes"], filetype="pdf")
    try:
        assert result["applied_rotations"] == [0, 0]
        assert output[1].rect.height > output[1].rect.width
        assert "Ada" in output[1].get_text()
    finally:
        output.close()


def test_normalizer_inserts_missing_side_before_a_new_distinct_letterhead():
    result = PDFNormalizerService.normalize_pdf(
        _make_batch(
            ("ALPHA", "Ada"),
            ("BRAVO", "Zoe"),
            (None, "Zoe"),
        ),
        auto_rotate=False,
        review_mode="heuristic",
    )
    output = fitz.open(stream=result["pdf_bytes"], filetype="pdf")
    try:
        assert result["blank_after_source_pages"] == [1]
        assert result["blank_pages_added"] == 1
        assert output.page_count == 4
        assert "ALPHA" in output[0].get_text()
        assert output[1].get_text().strip() == ""
        assert "BRAVO" in output[2].get_text()
    finally:
        output.close()


def test_normalizer_inserts_missing_side_after_a_three_page_letter():
    result = PDFNormalizerService.normalize_pdf(
        _make_batch(
            ("ALPHA", "Ada"),
            (None, "Ada"),
            (None, "Ada"),
            ("BRAVO", "Zoe"),
            (None, "Zoe"),
        ),
        auto_rotate=False,
        review_mode="heuristic",
    )
    output = fitz.open(stream=result["pdf_bytes"], filetype="pdf")
    try:
        assert result["blank_after_source_pages"] == [3]
        assert output.page_count == 6
        assert "Ada" in output[2].get_text()
        assert output[3].get_text().strip() == ""
        assert "BRAVO" in output[4].get_text()
    finally:
        output.close()


def test_normalizer_uses_handwriting_change_when_letterheads_match():
    result = PDFNormalizerService.normalize_pdf(
        _make_batch(
            ("COMMON", "AAAAAAAAAAAA"),
            ("COMMON", "ZZZZZZZZZZZZ"),
            (None, "ZZZZZZZZZZZZ"),
        ),
        auto_rotate=False,
        review_mode="heuristic",
    )
    output = fitz.open(stream=result["pdf_bytes"], filetype="pdf")
    try:
        assert result["blank_after_source_pages"] == [1]
        assert output.page_count == 4
        assert output[1].get_text().strip() == ""
        assert "ZZZZ" in output[2].get_text()
    finally:
        output.close()


class _FakeVisionReviewer:
    def __init__(self, plan: VisionReviewPlan):
        self.plan = plan
        self.calls: list[tuple[int, str | None]] = []

    def review(self, previews, *, model: str | None = None) -> VisionReviewPlan:
        self.calls.append((len(previews), model))
        return self.plan


def test_normalizer_uses_the_vision_review_plan_instead_of_heuristics():
    reviewer = _FakeVisionReviewer(
        VisionReviewPlan(
            rotations={1: 0, 2: 0, 3: 0},
            letter_start_pages=[1, 2],
            blank_after_source_pages=[1],
            model="test-vision-model",
        )
    )
    result = PDFNormalizerService.normalize_pdf(
        _make_letter_pdf(page_count=3),
        review_mode="vision",
        vision_model="test-vision-model",
        vision_reviewer=reviewer,
    )
    output = fitz.open(stream=result["pdf_bytes"], filetype="pdf")
    try:
        assert reviewer.calls == [(3, "test-vision-model")]
        assert result["review_mode"] == "vision"
        assert result["review_model"] == "test-vision-model"
        assert result["blank_after_source_pages"] == [1]
        assert output.page_count == 4
        assert max(output[1].get_pixmap(alpha=False).samples) == 0
    finally:
        output.close()


def test_vision_plan_does_not_add_a_blank_after_a_complete_four_page_letter():
    reviewer = _FakeVisionReviewer(
        VisionReviewPlan(
            rotations={1: 0, 2: 0, 3: 0, 4: 0},
            letter_start_pages=[1],
            blank_after_source_pages=[],
            model="test-vision-model",
        )
    )
    result = PDFNormalizerService.normalize_pdf(
        _make_letter_pdf(page_count=4),
        review_mode="vision",
        vision_reviewer=reviewer,
    )

    assert result["blank_after_source_pages"] == []
    assert result["blank_pages_added"] == 0
    assert result["output_page_count"] == 4


def test_vision_uses_separate_prompts_for_rotation_and_letter_boundaries():
    previews = [Image.new("RGB", (20, 20), "white") for _ in range(2)]
    rotation_instruction = PDFVisionReviewer._build_rotation_input(
        previews,
        [1, 2],
        model="gpt-5.6-terra",
    )[0]["text"]
    boundary_instruction = PDFVisionReviewer._build_boundary_input(
        previews,
        [2],
        model="gpt-5.6-terra",
    )[0]["text"]

    assert "orientation of every scanned page independently" in rotation_instruction
    assert "An upside-down page requires 180" in rotation_instruction
    assert "starts a different letter" in boundary_instruction
    assert "Page 1/2 and page 2/2" in boundary_instruction
    assert "If uncertain, return false" in boundary_instruction


def test_vision_plan_derives_blanks_only_from_odd_length_letter_groups():
    payload = {
        "page_rotations": [
            {"page": page, "degrees_clockwise": 0}
            for page in range(1, 8)
        ],
        "letter_start_pages": [1, 3, 6],
    }

    plan = PDFVisionReviewer._validate_plan(payload, page_count=7, model="test-vision-model")

    assert plan.letter_start_pages == [1, 3, 6]
    assert plan.blank_after_source_pages == [5]


class _FakeResponse:
    def __init__(self, payload: str):
        self.output_text = payload


class _FakeResponses:
    def __init__(self):
        self.calls: list[dict] = []

    def create(self, **request):
        self.calls.append(request)
        schema_name = request["text"]["format"]["name"]
        labels = [
            item["text"]
            for item in request["input"][0]["content"]
            if item["type"] == "input_text"
        ]
        if schema_name == "pdf_page_rotations":
            pages = [int(label.removeprefix("PDF page ").removesuffix(":")) for label in labels[1:]]
            payload = {
                "page_rotations": [
                    {"page": page, "degrees_clockwise": 180 if page == 9 else 0}
                    for page in pages
                ]
            }
        else:
            next_pages = [
                int(label.split(";", 1)[0].removeprefix("Boundary before PDF page "))
                for label in labels[1:]
                if label.startswith("Boundary before PDF page ")
            ]
            payload = {
                "boundaries": [
                    {"next_page": page, "starts_new_letter": page in {4, 7}}
                    for page in next_pages
                ]
            }

        import json

        return _FakeResponse(json.dumps(payload))


class _FakeOpenAIClient:
    def __init__(self):
        self.responses = _FakeResponses()


def test_vision_review_batches_tasks_and_derives_only_required_blanks():
    client = _FakeOpenAIClient()
    reviewer = PDFVisionReviewer(client=client)
    previews = [Image.new("RGB", (20, 20), "white") for _ in range(10)]

    plan = reviewer.review(previews, model="gpt-5.6-terra")

    assert plan.rotations[9] == 180
    assert plan.letter_start_pages == [1, 4, 7]
    assert plan.blank_after_source_pages == [3, 6]
    assert len(client.responses.calls) == 4
    assert all(call["reasoning"] == {"effort": "medium"} for call in client.responses.calls)
    image_items = [
        item
        for call in client.responses.calls
        for item in call["input"][0]["content"]
        if item["type"] == "input_image"
    ]
    assert image_items
    assert all(item["detail"] == "original" for item in image_items)


def test_vision_rotation_is_corrected_by_a_strong_local_layout_signal():
    source = fitz.open(stream=_make_letter_pdf(), filetype="pdf")
    rotated = fitz.open()
    try:
        rotated.insert_pdf(source, rotate=180)
        reviewer = _FakeVisionReviewer(
            VisionReviewPlan(
                rotations={1: 0},
                letter_start_pages=[1],
                blank_after_source_pages=[1],
                model="test-vision-model",
            )
        )
        result = PDFNormalizerService.normalize_pdf(
            rotated.tobytes(),
            review_mode="vision",
            ensure_page_pairs=False,
            vision_reviewer=reviewer,
        )
    finally:
        rotated.close()
        source.close()

    output = fitz.open(stream=result["pdf_bytes"], filetype="pdf")
    try:
        assert result["applied_rotations"] == [180]
        assert result["rotation_sources"] == ["layout_override"]
        assert output[0].rotation == 0
    finally:
        output.close()


def test_vision_unnecessary_rotation_is_rejected_by_a_strong_local_signal():
    reviewer = _FakeVisionReviewer(
        VisionReviewPlan(
            rotations={1: 180},
            letter_start_pages=[1],
            blank_after_source_pages=[1],
            model="test-vision-model",
        )
    )
    result = PDFNormalizerService.normalize_pdf(
        _make_letter_pdf(),
        review_mode="vision",
        ensure_page_pairs=False,
        vision_reviewer=reviewer,
    )

    assert result["applied_rotations"] == [0]
    assert result["rotation_sources"] == ["layout_override"]
