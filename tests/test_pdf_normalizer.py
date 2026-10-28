import fitz
from PIL import Image

from app.services.pdf_normalizer.router import (
    _build_content_disposition,
    _letter_file_names,
    _normalized_file_name,
)
from app.services.pdf_normalizer.service import PDFNormalizerService
from app.services.pdf_normalizer.vision import BatchHeader, PDFVisionReviewer, VisionReviewPlan


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
        self.rotation_hints: dict[int, int] | None = None
        self.judge_options: dict[str, bool] = {}

    def review(
        self,
        previews,
        *,
        provider: str | None = None,
        model: str | None = None,
        rotation_hints: dict[int, int] | None = None,
        **judge_options: bool,
    ) -> VisionReviewPlan:
        self.calls.append((len(previews), model))
        self.rotation_hints = rotation_hints
        self.judge_options = judge_options
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
    assert "which edge of the image the TOP of the writing faces" in rotation_instruction
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
        if schema_name == "pdf_page_orientations":
            pages = [
                int(label.removeprefix("PDF page ").removesuffix(":"))
                for label in labels
                if label.startswith("PDF page ")
            ]
            payload = {
                "page_orientations": [
                    {"page": page, "text_top_points": "down" if page == 9 else "up"}
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


class _FakeAnthropicMessage:
    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class _FakeAnthropicMessages:
    def __init__(self):
        self.calls: list[dict] = []

    def create(self, **request):
        self.calls.append(request)
        labels = [block["text"] for block in request["messages"][0]["content"] if block["type"] == "text"]
        if any(label.startswith("PDF page ") for label in labels):
            pages = [int(label.removeprefix("PDF page ").removesuffix(":")) for label in labels if label.startswith("PDF page ")]
            payload = {"page_orientations": [{"page": page, "text_top_points": "up"} for page in pages]}
        else:
            next_pages = [
                int(label.split(";", 1)[0].removeprefix("Boundary before PDF page "))
                for label in labels if label.startswith("Boundary before PDF page ")
            ]
            payload = {"boundaries": [{"next_page": page, "starts_new_letter": False} for page in next_pages]}
        import json
        return type("Response", (), {"content": [_FakeAnthropicMessage(json.dumps(payload))]})()


class _FakeAnthropicClient:
    def __init__(self):
        self.messages = _FakeAnthropicMessages()


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


def test_vision_review_supports_anthropic_messages_api():
    client = _FakeAnthropicClient()
    reviewer = PDFVisionReviewer(client=client)
    plan = reviewer.review(
        [Image.new("RGB", (20, 20), "white") for _ in range(2)],
        provider="anthropic",
        model="claude-opus-5-5",
    )

    assert plan.provider == "anthropic"
    assert plan.model == "claude-opus-5-5"
    assert len(client.messages.calls) == 2
    assert all(call["model"] == "claude-opus-5-5" for call in client.messages.calls)
    # Structured output is enforced, and thinking has room to finish before the JSON.
    assert all(call["output_config"]["format"]["type"] == "json_schema" for call in client.messages.calls)
    assert all(call["max_tokens"] >= 16000 for call in client.messages.calls)


def test_anthropic_empty_response_is_retried():
    client = _FakeAnthropicClient()
    real_create = client.messages.create
    replies = iter(["", None])

    def flaky_create(**request):
        if next(replies) == "":
            client.messages.calls.append(request)
            return type("Response", (), {"content": [], "stop_reason": "max_tokens"})()
        return real_create(**request)

    client.messages.create = flaky_create
    plan = PDFVisionReviewer(client=client).review(
        [Image.new("RGB", (20, 20), "white")],
        provider="anthropic",
        model="claude-opus-5-5",
    )

    assert plan.rotations == {1: 0}
    assert len(client.messages.calls) == 2


def test_vision_review_accepts_anthropic_json_in_a_markdown_code_fence():
    assert PDFVisionReviewer._parse_json_response("```json\n{\"ok\": true}\n```") == {"ok": True}


def test_strong_local_layout_signal_is_a_hint_and_never_overrides_vision():
    # A confident layout signal was wrong on real scans (gray paper, writing in
    # the lower half); it may only ask the reviewer for a second look.
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

    assert reviewer.rotation_hints == {1: 180}
    assert result["applied_rotations"] == [0]
    assert result["rotation_sources"] == ["vision"]


def test_vision_rotation_sources_are_reported_per_page():
    reviewer = _FakeVisionReviewer(
        VisionReviewPlan(
            rotations={1: 90, 2: 0},
            letter_start_pages=[1],
            blank_after_source_pages=[],
            model="test-vision-model",
            rotation_sources={1: "verification_override", 2: "vision"},
        )
    )
    result = PDFNormalizerService.normalize_pdf(
        _make_letter_pdf(page_count=2),
        review_mode="vision",
        vision_reviewer=reviewer,
    )

    assert result["applied_rotations"] == [90, 0]
    assert result["rotation_sources"] == ["verification_override", "vision"]


class _ScriptedOrientationClient:
    """OpenAI-shaped fake that answers each page's requests in order.

    ``boundaries`` scripts each next page's starts_new_letter answers (default
    false). ``judge_rounds`` scripts one document check per entry, mapping an
    output page to (text_top_points, starts_new_letter, note); unlisted pages
    are reported upright and continuing.
    """

    def __init__(
        self,
        answers: dict[int, list[str]],
        *,
        boundaries: dict[int, list[bool]] | None = None,
        judge_rounds: list[dict[int, tuple[str, bool, str]]] | None = None,
        header: dict[str, int] | None = None,
    ):
        self.answers = {page: list(replies) for page, replies in answers.items()}
        self.boundaries = {page: list(replies) for page, replies in (boundaries or {}).items()}
        self.judge_rounds = list(judge_rounds or [])
        self.header = header or {}
        self.header_requests: list[dict] = []
        self.rotation_requests: list[dict] = []
        self.boundary_requests: list[dict] = []
        self.judge_requests: list[dict] = []
        self.responses = self

    def create(self, **request):
        import json

        items = request["input"][0]["content"]
        labels = [item["text"] for item in items if item["type"] == "input_text"]
        schema_name = request["text"]["format"]["name"]
        if schema_name == "pdf_page_orientations":
            self.rotation_requests.append(request)
            pages = [
                int(label.removeprefix("PDF page ").removesuffix(":"))
                for label in labels
                if label.startswith("PDF page ")
            ]
            payload = {
                "page_orientations": [
                    {"page": page, "text_top_points": self.answers[page].pop(0)} for page in pages
                ]
            }
        elif schema_name == "pdf_batch_header":
            self.header_requests.append(request)
            fields = ("batch_number", "received_month", "received_day", "sheets_per_letter", "letter_count")
            payload = {name: self.header.get(name, 0) for name in fields}
        elif schema_name == "pdf_letter_boundaries":
            self.boundary_requests.append(request)
            next_pages = [
                int(label.split(";", 1)[0].removeprefix("Boundary before PDF page "))
                for label in labels
                if label.startswith("Boundary before PDF page ")
            ]
            payload = {
                "boundaries": [
                    {
                        "next_page": page,
                        "starts_new_letter": self.boundaries[page].pop(0) if self.boundaries.get(page) else False,
                    }
                    for page in next_pages
                ]
            }
        else:
            self.judge_requests.append(request)
            checked = self.judge_rounds.pop(0) if self.judge_rounds else {}
            pages = [
                int(label.removeprefix("Output page ").removesuffix(":"))
                for label in labels
                if label.startswith("Output page ") and label.endswith(":") and "context" not in label
            ]
            payload = {
                "page_checks": [
                    {
                        "output_page": page,
                        "text_top_points": checked.get(page, ("up", False, ""))[0],
                        "starts_new_letter": checked.get(page, ("up", False, ""))[1],
                        "note": checked.get(page, ("up", False, ""))[2],
                    }
                    for page in pages
                ]
            }
        return _FakeResponse(json.dumps(payload))


def _request_texts(request: dict) -> list[str]:
    return [item["text"] for item in request["input"][0]["content"] if item["type"] == "input_text"]


def _request_image_sizes(request: dict) -> list[tuple[int, int]]:
    import base64
    import io

    return [
        Image.open(io.BytesIO(base64.b64decode(item["image_url"].split(",", 1)[1]))).size
        for item in request["input"][0]["content"]
        if item["type"] == "input_image"
    ]


def test_orientation_answers_map_to_clockwise_corrections():
    assert PDFVisionReviewer._TOP_DIRECTION_TO_CORRECTION == {"up": 0, "right": 270, "down": 180, "left": 90}


def test_second_look_corrects_a_wrong_sideways_direction():
    # The first answer turns the page the wrong way; with that correction
    # applied the page looks upside down, so the total correction is 270 + 180.
    client = _ScriptedOrientationClient({1: ["right", "down"]})
    plan = PDFVisionReviewer(client=client).review(
        [Image.new("RGB", (40, 20), "white")], model="gpt-5.6-terra"
    )

    assert plan.rotations == {1: 90}
    assert plan.rotation_sources == {1: "verification_override"}
    assert len(client.rotation_requests) == 2
    assert _request_image_sizes(client.rotation_requests[0]) == [(40, 20)]
    assert _request_image_sizes(client.rotation_requests[1]) == [(20, 40)]


def test_second_look_confirms_a_correct_sideways_rotation():
    client = _ScriptedOrientationClient({1: ["left", "up"]})
    plan = PDFVisionReviewer(client=client).review(
        [Image.new("RGB", (40, 20), "white")], model="gpt-5.6-terra"
    )

    assert plan.rotations == {1: 90}
    assert plan.rotation_sources == {1: "vision_verified"}


def test_landscape_page_called_upright_is_shown_portrait_for_the_second_look():
    # A sideways scan described as level would stay landscape; a quarter turn
    # makes the second look an upright-versus-upside-down question.
    client = _ScriptedOrientationClient({1: ["up", "down"]})
    plan = PDFVisionReviewer(client=client).review(
        [Image.new("RGB", (40, 20), "white")], model="gpt-5.6-terra"
    )

    assert _request_image_sizes(client.rotation_requests[1]) == [(20, 40)]
    assert plan.rotations == {1: 270}
    assert plan.rotation_sources == {1: "verification_override"}


def test_truly_landscape_page_keeps_its_upright_answer():
    client = _ScriptedOrientationClient({1: ["up", "right"]})
    plan = PDFVisionReviewer(client=client).review(
        [Image.new("RGB", (40, 20), "white")], model="gpt-5.6-terra"
    )

    assert plan.rotations == {1: 0}
    assert plan.rotation_sources == {1: "vision_verified"}


def test_portrait_page_called_sideways_is_checked_standing_portrait():
    client = _ScriptedOrientationClient({1: ["right", "up"]})
    plan = PDFVisionReviewer(client=client).review(
        [Image.new("RGB", (20, 40), "white")], model="gpt-5.6-terra"
    )

    assert _request_image_sizes(client.rotation_requests[1]) == [(20, 40)]
    assert plan.rotations == {1: 0}
    assert plan.rotation_sources == {1: "verification_override"}


def test_upright_and_upside_down_pages_skip_the_second_look():
    client = _ScriptedOrientationClient({1: ["up"], 2: ["down"]})
    plan = PDFVisionReviewer(client=client).review(
        [Image.new("RGB", (20, 40), "white") for _ in range(2)], model="gpt-5.6-terra"
    )

    assert plan.rotations == {1: 0, 2: 180}
    assert plan.rotation_sources == {1: "vision", 2: "vision"}
    assert len(client.rotation_requests) == 1


def test_local_hint_disagreement_gets_a_second_look_without_overriding():
    client = _ScriptedOrientationClient({1: ["up", "up"]})
    plan = PDFVisionReviewer(client=client).review(
        [Image.new("RGB", (20, 40), "white")],
        model="gpt-5.6-terra",
        rotation_hints={1: 90},
    )

    assert plan.rotations == {1: 0}
    assert plan.rotation_sources == {1: "vision_verified"}
    assert len(client.rotation_requests) == 2


def test_judge_passes_a_correct_document_without_retries():
    client = _ScriptedOrientationClient({1: ["up"], 2: ["up"]})
    plan = PDFVisionReviewer(client=client).review(
        [Image.new("RGB", (20, 40), "white") for _ in range(2)], model="gpt-5.6-terra", judge=True
    )

    assert plan.judge_status == "passed"
    assert plan.judge_retries == 0
    assert plan.judge_issues == []
    assert len(client.judge_requests) == 1


def test_judge_feedback_fixes_a_page_the_second_look_missed():
    # A sideways page (top of the writing points right) is first called level,
    # then wrongly confirmed upside down. The judge reads the finished page,
    # reports it upside down, and the reviewer fixes it with that feedback.
    client = _ScriptedOrientationClient(
        {1: ["up", "up", "down"]},
        judge_rounds=[{1: ("down", False, "")}, {}],
    )
    plan = PDFVisionReviewer(client=client).review(
        [Image.new("RGB", (40, 20), "white")], model="gpt-5.6-terra", judge=True
    )

    assert plan.rotations == {1: 270}
    assert plan.rotation_sources == {1: "judge_override"}
    assert plan.judge_status == "passed"
    assert plan.judge_retries == 1
    retry = client.rotation_requests[-1]
    assert _request_image_sizes(retry) == [(20, 40)]
    assert any("facing the bottom edge, so the page is upside down" in text for text in _request_texts(retry))
    assert _request_image_sizes(client.judge_requests[-1]) == [(20, 40)]


def test_judge_feedback_is_translated_to_the_portrait_view():
    # The judge saw a landscape output page with the top of the writing to
    # the right; the reviewer sees it after a further quarter turn.
    feedback = PDFVisionReviewer._rotation_feedback(10, "right", 90)

    assert feedback.startswith("Reviewer feedback for PDF page 10:")
    assert "facing the bottom edge, so the page is upside down" in feedback


def test_judge_boundary_dispute_is_sent_back_with_its_note():
    client = _ScriptedOrientationClient(
        {1: ["up"], 2: ["up"]},
        boundaries={2: [False, True]},
        judge_rounds=[
            {2: ("up", True, "New sender and greeting from Kidron.")},
            {3: ("up", True, "")},
        ],
    )
    plan = PDFVisionReviewer(client=client).review(
        [Image.new("RGB", (20, 40), "white") for _ in range(2)], model="gpt-5.6-terra", judge=True
    )

    assert plan.letter_start_pages == [1, 2]
    assert plan.blank_after_source_pages == [1, 2]
    assert plan.judge_status == "passed"
    assert plan.judge_retries == 1
    retry_texts = _request_texts(client.boundary_requests[-1])
    assert any("believes page 2 starts a new letter" in text and "Kidron" in text for text in retry_texts)
    second_check = _request_texts(client.judge_requests[-1])
    assert "Output page 2: black page added as the blank back of the letter before it." in second_check


def test_judge_reports_issues_when_the_reviewer_keeps_its_answer():
    client = _ScriptedOrientationClient({1: ["up", "up"]}, judge_rounds=[{1: ("right", False, "")}])
    plan = PDFVisionReviewer(client=client).review(
        [Image.new("RGB", (20, 40), "white")], model="gpt-5.6-terra", judge=True
    )

    assert plan.rotations == {1: 0}
    assert plan.judge_status == "issues_remaining"
    assert plan.judge_retries == 1
    assert plan.judge_issues == ["1:top_points_right"]
    assert len(client.judge_requests) == 1


def test_judge_stops_after_its_retry_limit():
    client = _ScriptedOrientationClient(
        {1: ["up", "right", "left"]},
        judge_rounds=[{1: ("right", False, "")}, {1: ("down", False, "")}, {1: ("left", False, "")}],
    )
    plan = PDFVisionReviewer(client=client).review(
        [Image.new("RGB", (20, 40), "white")], model="gpt-5.6-terra", judge=True
    )

    assert plan.judge_status == "issues_remaining"
    assert plan.judge_retries == PDFVisionReviewer.JUDGE_RETRIES == 2
    assert plan.judge_issues == ["1:top_points_left"]
    assert len(client.judge_requests) == 3


def test_judge_batches_carry_the_previous_page_as_context():
    client = _ScriptedOrientationClient({page: ["up"] for page in range(1, 10)})
    plan = PDFVisionReviewer(client=client).review(
        [Image.new("RGB", (20, 40), "white") for _ in range(9)], model="gpt-5.6-terra", judge=True
    )

    assert plan.judge_status == "passed"
    assert len(client.judge_requests) == 2
    texts = _request_texts(client.judge_requests[1])
    assert texts[1:] == [
        "Output page 8 (context only, do not report it):",
        "Output page 9:",
        "Output page 10: black page added as the blank back of the letter before it.",
        "Report exactly these output pages: 9.",
    ]


def test_judge_ignores_extra_entries_for_black_and_context_pages():
    payload = {
        "page_checks": [
            {"output_page": page, "text_top_points": "up", "starts_new_letter": False, "note": ""}
            for page in (8, 9, 10)
        ]
    }

    checks = PDFVisionReviewer._validate_judge_batch(payload, expected_pages=[9])

    assert list(checks) == [9]


def test_judge_failure_keeps_the_reviewed_plan():
    client = _ScriptedOrientationClient({1: ["down"]})
    scripted_create = client.create

    def create(**request):
        if request["text"]["format"]["name"] == "pdf_document_check":
            client.judge_requests.append(request)
            return _FakeResponse("not json")
        return scripted_create(**request)

    client.create = create
    plan = PDFVisionReviewer(client=client).review(
        [Image.new("RGB", (20, 40), "white")], model="gpt-5.6-terra", judge=True
    )

    assert plan.rotations == {1: 180}
    assert plan.judge_status == "error"
    assert len(client.judge_requests) == PDFVisionReviewer.BATCH_ATTEMPTS


def test_normalizer_runs_the_judge_on_what_it_applies_and_reports_it():
    reviewer = _FakeVisionReviewer(
        VisionReviewPlan(
            rotations={1: 0, 2: 0},
            letter_start_pages=[1],
            blank_after_source_pages=[],
            model="test-vision-model",
            judge_status="issues_remaining",
            judge_retries=2,
            judge_issues=["2:top_points_right"],
        )
    )
    result = PDFNormalizerService.normalize_pdf(
        _make_letter_pdf(page_count=2),
        review_mode="vision",
        ensure_page_pairs=False,
        vision_reviewer=reviewer,
    )

    assert reviewer.judge_options == {
        "judge": True,
        "judge_rotations": True,
        "judge_page_pairs": False,
        "read_batch_header": True,
    }
    assert result["judge_status"] == "issues_remaining"
    assert result["judge_retries"] == 2
    assert result["judge_issues"] == ["2:top_points_right"]

    PDFNormalizerService.normalize_pdf(
        _make_letter_pdf(page_count=2), review_mode="vision", judge=False, vision_reviewer=reviewer
    )
    assert reviewer.judge_options["judge"] is False


_BATCH_5 = {"batch_number": 5, "received_month": 7, "received_day": 25, "sheets_per_letter": 2, "letter_count": 2}


def test_batch_header_is_read_from_the_upright_first_page():
    client = _ScriptedOrientationClient({1: ["down"], 2: ["down"]}, header=_BATCH_5)
    plan = PDFVisionReviewer(client=client).review(
        [Image.new("RGB", (20, 40), "white") for _ in range(2)], model="gpt-5.6-terra", read_batch_header=True
    )

    assert plan.batch == BatchHeader(number=5, received_month=7, received_day=25, sheets_per_letter=2, letter_count=2)
    assert len(client.header_requests) == 1
    assert "BATCH" in _request_texts(client.header_requests[0])[0]


def test_unreadable_batch_header_values_are_dropped():
    header = PDFVisionReviewer._validate_batch_header(
        {"batch_number": 3, "received_month": 13, "received_day": 24, "sheets_per_letter": 40, "letter_count": 8}
    )

    assert header == BatchHeader(number=3, received_month=0, received_day=0, sheets_per_letter=0, letter_count=8)


def test_a_failed_batch_header_read_does_not_fail_the_review():
    client = _ScriptedOrientationClient({1: ["up"]})
    scripted_create = client.create

    def create(**request):
        if request["text"]["format"]["name"] == "pdf_batch_header":
            return _FakeResponse("not json")
        return scripted_create(**request)

    client.create = create
    plan = PDFVisionReviewer(client=client).review(
        [Image.new("RGB", (20, 40), "white")], model="gpt-5.6-terra", read_batch_header=True
    )

    assert plan.batch == BatchHeader()


def test_letter_that_breaks_the_header_sheet_count_is_sent_back():
    # Header: 2 sheets (4 pages) per letter. The first pass misses the start
    # at page 8, so pages 4-11 come to 8 pages; the size hint sends those
    # boundaries back and the reviewer finds the start. The judge reads 12
    # output pages in two batches per round.
    client = _ScriptedOrientationClient(
        {page: ["up"] for page in range(1, 12)},
        boundaries={4: [True, True], 8: [False, True]},
        judge_rounds=[{5: ("up", True, "")}, {}, {5: ("up", True, "")}, {9: ("up", True, "")}],
        header={**_BATCH_5, "letter_count": 3},
    )
    plan = PDFVisionReviewer(client=client).review(
        [Image.new("RGB", (20, 40), "white") for _ in range(11)],
        model="gpt-5.6-terra",
        judge=True,
        read_batch_header=True,
    )

    assert plan.letter_start_pages == [1, 4, 8]
    assert plan.judge_status == "passed"
    assert plan.judge_retries == 1
    retry_texts = _request_texts(client.boundary_requests[-1])
    assert any("from page 4 to page 11 comes to 8 pages" in text for text in retry_texts)


def test_letter_count_disagreement_with_the_header_is_reported():
    client = _ScriptedOrientationClient(
        {1: ["up"], 2: ["up"]}, header={**_BATCH_5, "sheets_per_letter": 1, "letter_count": 3}
    )
    plan = PDFVisionReviewer(client=client).review(
        [Image.new("RGB", (20, 40), "white") for _ in range(2)],
        model="gpt-5.6-terra",
        judge=True,
        read_batch_header=True,
    )

    assert plan.judge_status == "issues_remaining"
    assert plan.judge_issues == ["batch:found_1_letters_header_says_3"]


def test_header_that_most_letters_disagree_with_is_not_trusted():
    assert PDFVisionReviewer._letter_size_misfits([1, 3, 5], 6, 2) == {}
    assert PDFVisionReviewer._letter_size_misfits([1, 4, 7, 9], 12, 2) == {7: (8, 2)}


def test_letter_files_are_named_month_day_batch_position_total():
    batch = BatchHeader(number=3, received_month=10, received_day=24, sheets_per_letter=2, letter_count=8)

    assert _letter_file_names(batch, 8)[1] == "10-24-Batch3-2-8.pdf"
    assert _letter_file_names(BatchHeader(number=5, received_month=7, received_day=25), 2) == [
        "07-25-Batch5-1-2.pdf",
        "07-25-Batch5-2-2.pdf",
    ]
    assert _letter_file_names(BatchHeader(), 1) == ["XX-XX-BatchX-1-1.pdf"]
    assert _normalized_file_name("scan.pdf", batch, 8) == "10-24-Batch3-2sheets-8letters.pdf"
    assert _normalized_file_name("scan.pdf", BatchHeader(), 8) == "scan_normalized.pdf"


def test_normalizer_splits_letters_with_their_black_pages():
    reviewer = _FakeVisionReviewer(
        VisionReviewPlan(
            rotations={1: 0, 2: 0, 3: 0},
            letter_start_pages=[1, 2],
            blank_after_source_pages=[1],
            model="test-vision-model",
        )
    )
    result = PDFNormalizerService.normalize_pdf(
        _make_letter_pdf(page_count=3), review_mode="vision", vision_reviewer=reviewer, split_letters=True
    )

    assert result["letter_page_ranges"] == [(1, 2), (3, 4)]
    page_counts = []
    for letter_pdf in result["letter_pdfs"]:
        letter = fitz.open(stream=letter_pdf, filetype="pdf")
        page_counts.append(letter.page_count)
        letter.close()
    assert page_counts == [2, 2]


def test_zip_output_names_each_letter_from_the_batch_header():
    import io
    import zipfile

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.services.pdf_normalizer import service as service_module
    from app.services.pdf_normalizer.router import router

    plan = VisionReviewPlan(
        rotations={1: 0, 2: 0, 3: 0},
        letter_start_pages=[1, 2],
        blank_after_source_pages=[1],
        model="test-vision-model",
        batch=BatchHeader(number=3, received_month=10, received_day=24, sheets_per_letter=1, letter_count=2),
    )
    original = service_module.PDFVisionReviewer
    service_module.PDFVisionReviewer = lambda: _FakeVisionReviewer(plan)
    try:
        app = FastAPI()
        app.include_router(router, prefix="/pdf-normalizer")
        response = TestClient(app).post(
            "/pdf-normalizer/normalize/?output=zip",
            files={"file": ("scan.pdf", _make_letter_pdf(page_count=3), "application/pdf")},
        )
    finally:
        service_module.PDFVisionReviewer = original

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert 'filename="10-24-Batch3.zip"' in response.headers["content-disposition"]
    assert response.headers["x-batch-number"] == "3"
    assert response.headers["x-batch-received"] == "10-24"
    assert response.headers["x-letters-found"] == "2"
    with zipfile.ZipFile(io.BytesIO(response.content)) as bundle:
        assert bundle.namelist() == ["10-24-Batch3-1-2.pdf", "10-24-Batch3-2-2.pdf"]
