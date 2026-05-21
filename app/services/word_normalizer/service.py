import io
import json
import os
import re
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Tuple

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt


_NORM_CACHE: Dict[str, Any] = {"by_client": {}}
_NORM_TTL_SECONDS = 300


def _fetch_normalization_rules(client: str) -> List[Tuple[str, str]]:
    supabase_url = (os.getenv("SUPABASE_URL") or "").strip().rstrip("/")
    supabase_key = (os.getenv("SUPABASE_KEY") or "").strip()
    if not supabase_url or not supabase_key:
        return []

    now = time.time()
    by_client = _NORM_CACHE.get("by_client") or {}
    entry = by_client.get(client) or {}
    if now - float(entry.get("ts") or 0.0) < _NORM_TTL_SECONDS:
        return list(entry.get("items") or [])

    query = urllib.parse.urlencode({"select": "ShortForm,Expansion,Client"})
    url = f"{supabase_url}/rest/v1/Normalization_Words_List?{query}"
    req = urllib.request.Request(
        url,
        headers={
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Accept": "application/json",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            rows = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []

    if not isinstance(rows, list):
        return []

    items: List[Tuple[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_client = (row.get("Client") or "").strip()
        if client.lower() not in row_client.lower():
            continue
        short_form = (row.get("ShortForm") or "").strip()
        expansion = (row.get("Expansion") or "").strip()
        if short_form and expansion:
            items.append((short_form, expansion))

    if not isinstance(_NORM_CACHE.get("by_client"), dict):
        _NORM_CACHE["by_client"] = {}
    _NORM_CACHE["by_client"][client] = {"ts": now, "items": items}
    return items


def _build_pattern(short_form: str) -> re.Pattern:
    escaped = re.escape(short_form)
    if re.fullmatch(r"[A-Za-z0-9']+", short_form):
        return re.compile(rf"\b{escaped}\b", re.IGNORECASE)
    return re.compile(escaped, re.IGNORECASE)


def _context_is_uppercase(text: str) -> bool:
    """Return True if the majority of alphabetic characters in text are uppercase."""
    alpha = [c for c in text if c.isalpha()]
    if not alpha:
        return False
    return sum(1 for c in alpha if c.isupper()) / len(alpha) > 0.5


def _apply_rules(text: str, rules: List[Tuple[str, str]]) -> Tuple[str, List[Dict[str, Any]]]:
    """Apply normalization rules to text. Returns (normalized_text, changes_list)."""
    normalized = text
    changes: List[Dict[str, Any]] = []
    uppercase_context = _context_is_uppercase(text)
    for short_form, expansion in rules:
        pattern = _build_pattern(short_form)
        count = len(pattern.findall(normalized))
        if count == 0:
            continue
        applied = expansion.upper() if uppercase_context else expansion.lower()
        normalized = pattern.sub(applied, normalized)
        changes.append({"short_form": short_form, "expansion": expansion, "occurrences": count})
    return normalized, changes


def normalize_text(date: str, body: str, client: str) -> Dict[str, Any]:
    """
    Apply normalization rules to both date and body.

    Returns:
      - normalized_date: str
      - normalized_body: str
      - changes: list of {short_form, expansion, occurrences}
      - total_changes: int
    """
    rules = _fetch_normalization_rules(client)

    normalized_date, date_changes = _apply_rules(date, rules)
    normalized_body, body_changes = _apply_rules(body, rules)

    # Merge changes, combining counts for the same short_form
    merged: Dict[str, Dict[str, Any]] = {}
    for change in date_changes + body_changes:
        key = change["short_form"]
        if key in merged:
            merged[key]["occurrences"] += change["occurrences"]
        else:
            merged[key] = dict(change)
    changes = list(merged.values())

    total_changes = sum(c["occurrences"] for c in changes)
    return {
        "normalized_date": normalized_date,
        "normalized_body": normalized_body,
        "changes": changes,
        "total_changes": total_changes,
    }


def build_report_docx(changes: List[Dict[str, Any]], total_changes: int) -> bytes:
    """Generate a Word document listing all word substitutions and the total count."""
    doc = Document()

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("Normalization Report")
    run.bold = True
    run.font.size = Pt(14)
    run.font.name = "Times New Roman"

    doc.add_paragraph()

    header = doc.add_paragraph()
    h_run = header.add_run("Words Changed:")
    h_run.bold = True
    h_run.font.size = Pt(12)
    h_run.font.name = "Times New Roman"

    if changes:
        for change in changes:
            p = doc.add_paragraph(style="List Bullet")
            r = p.add_run(
                f'"{change["short_form"]}"  →  "{change["expansion"]}"'
                f'  ({change["occurrences"]} occurrence(s))'
            )
            r.font.size = Pt(12)
            r.font.name = "Times New Roman"
    else:
        p = doc.add_paragraph()
        r = p.add_run("No changes made.")
        r.font.size = Pt(12)
        r.font.name = "Times New Roman"

    doc.add_paragraph()

    total_p = doc.add_paragraph()
    t_run = total_p.add_run(f"Total words changed: {total_changes}")
    t_run.bold = True
    t_run.font.size = Pt(12)
    t_run.font.name = "Times New Roman"

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
