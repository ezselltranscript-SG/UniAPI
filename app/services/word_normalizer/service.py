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


# --- Context exception helpers ---
# Each function receives (text, match) and returns True to SKIP that match.

_EVE_SALUTATIONS = re.compile(
    r"\b(dear|hi|hello|mr\.?|mrs\.?|ms\.?|dr\.?|miss|saint|st\.?)\s*$",
    re.IGNORECASE,
)

_EVE_RELATIONSHIPS = re.compile(
    r"\b(?:my|our|his|her|their|your\s+)?"
    r"(?:daughter|son|mother|father|sister|brother|aunt|uncle|"
    r"friend|wife|husband|neighbor|neighbour|colleague|coworker|partner|"
    r"niece|nephew|granddaughter|grandson|grandmother|grandfather|"
    r"grandma|grandpa|mom|dad|sis|cousin|fianc[eé]e?|"
    r"client|patient|neighbor|associate|classmate|roommate|teammate)\s*$",
    re.IGNORECASE,
)

# Matches "my friend", "our neighbor", "his daughter", etc. before "Eve"
_EVE_POSSESSIVE_RELATIONSHIP = re.compile(
    r"\b(?:my|our|his|her|their|your)\s+\w+\s*$",
    re.IGNORECASE,
)


def _skip_eve(text: str, m: re.Match) -> bool:
    """Skip 'Eve' when it is part of 'Christmas Eve' or appears to be a proper name."""
    start, end = m.start(), m.end()
    before = text[max(0, start - 40):start]
    after = text[end:end + 25]

    # Christmas Eve (any casing)
    if re.search(r"christmas\s*$", before, re.IGNORECASE):
        return True

    # Proper name: Eve followed by a capitalized surname (e.g. "Eve Stoltzfus")
    if re.match(r"\s+[A-Z][a-z]", after):
        return True

    # Preceded by a salutation or title (Dear Eve, Hi Eve, Dr. Eve …)
    if _EVE_SALUTATIONS.search(before):
        return True

    # Preceded by a relationship noun (daughter Eve, my friend Eve, his sister Eve …)
    if _EVE_RELATIONSHIPS.search(before):
        return True

    # Catch-all possessive + any word right before Eve ("my little Eve", "our sweet Eve" …)
    if _EVE_POSSESSIVE_RELATIONSHIP.search(before):
        return True

    return False


# Map short_form (lowercase key) → skip-check function
_CONTEXT_EXCEPTIONS: Dict[str, Any] = {
    "eve": _skip_eve,
}


def _apply_rules(text: str, rules: List[Tuple[str, str]]) -> Tuple[str, List[Dict[str, Any]]]:
    """Apply normalization rules to text. Returns (normalized_text, changes_list)."""
    normalized = text
    changes: List[Dict[str, Any]] = []
    uppercase_context = _context_is_uppercase(text)

    for short_form, expansion in rules:
        pattern = _build_pattern(short_form)
        applied = expansion.upper() if uppercase_context else expansion.lower()
        skip_check = _CONTEXT_EXCEPTIONS.get(short_form.lower())

        if skip_check:
            # Walk matches manually so we can consult context before substituting.
            parts: List[str] = []
            last = 0
            count = 0
            for m in pattern.finditer(normalized):
                if skip_check(normalized, m):
                    # Keep original text for this match
                    parts.append(normalized[last:m.end()])
                else:
                    parts.append(normalized[last:m.start()])
                    parts.append(applied)
                    count += 1
                last = m.end()
            parts.append(normalized[last:])
            normalized = "".join(parts)
        else:
            count = len(pattern.findall(normalized))
            if count == 0:
                continue
            normalized = pattern.sub(applied, normalized)

        if count > 0:
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
