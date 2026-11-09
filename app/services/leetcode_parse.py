"""Pure helpers for recognising LeetCode problem references (no network)."""
import html as _html
import re
from typing import Dict, List, Optional

_URL_RE = re.compile(r"leetcode\.(?:com|cn)/problems/([a-z0-9\-]+)", re.IGNORECASE)
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def slug_from_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    m = _URL_RE.search(url)
    return m.group(1).lower() if m else None


def classify_query(q: str):
    """Returns ("slug", slug) | ("number", "123") | ("search", text)."""
    q = (q or "").strip()
    slug = slug_from_url(q)
    if slug:
        return "slug", slug
    if q.isdigit():
        return "number", str(int(q))
    lowered = q.lower()
    if _SLUG_RE.match(lowered) and "-" in lowered:
        return "slug", lowered
    return "search", q


# ---------------------------------------------------------------------------
# Statement / example parsing
# ---------------------------------------------------------------------------
_BLOCK_BREAK_RE = re.compile(r"<\s*(br\s*/?|/p|/li|/div|/pre|/ul|/ol|/h\d)\s*>", re.IGNORECASE)
_LI_RE = re.compile(r"<\s*li[^>]*>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_EXAMPLE_RE = re.compile(r"Example\s*\d*\s*:", re.IGNORECASE)
_END_RE = re.compile(r"(Constraints\s*:|Follow[\s\-]*up\s*:?|Note\s*:)", re.IGNORECASE)
_LABEL_RE = re.compile(r"(Input|Output|Explanation)\s*:", re.IGNORECASE)


def html_to_text(content: str) -> str:
    """Convert LeetCode statement HTML into readable plain text."""
    if not content:
        return ""
    text = _LI_RE.sub("- ", content)
    text = _BLOCK_BREAK_RE.sub("\n", text)
    text = _TAG_RE.sub("", text)
    text = _html.unescape(text).replace("\xa0", " ").replace("\r", "")
    lines = [ln.rstrip() for ln in text.split("\n")]
    out: List[str] = []
    for ln in lines:
        if not ln.strip():
            if out and out[-1] != "":
                out.append("")
            continue
        out.append(ln.strip() if not ln.startswith("\t") else ln.strip())
    return "\n".join(out).strip()


def _clean(s: str) -> str:
    return re.sub(r"\n{2,}", "\n", s).strip()


def parse_examples(content: Optional[str], example_testcases: Optional[List[str]] = None) -> List[Dict[str, str]]:
    """Extract [{input, output, explanation}] from a statement.

    Handles the classic ``<pre><strong>Input:</strong> ...</pre>`` layout and the newer
    ``<div class="example-block">`` layout. Falls back to raw example test case inputs
    (with empty outputs) when the statement can't be parsed.
    """
    examples: List[Dict[str, str]] = []
    text = html_to_text(content or "")
    if text:
        starts = [m for m in _EXAMPLE_RE.finditer(text)]
        for i, m in enumerate(starts):
            end = starts[i + 1].start() if i + 1 < len(starts) else len(text)
            section = text[m.end():end]
            stop = _END_RE.search(section)
            if stop:
                section = section[: stop.start()]
            parts: Dict[str, str] = {}
            labels = list(_LABEL_RE.finditer(section))
            for j, lm in enumerate(labels):
                seg_end = labels[j + 1].start() if j + 1 < len(labels) else len(section)
                key = lm.group(1).lower()
                if key not in parts:
                    parts[key] = _clean(section[lm.end():seg_end])
            if parts.get("input") is not None and parts.get("output") is not None:
                examples.append({
                    "input": parts.get("input", ""),
                    "output": parts.get("output", ""),
                    "explanation": parts.get("explanation", ""),
                })
    if not examples and example_testcases:
        examples = [{"input": tc.strip(), "output": "", "explanation": ""} for tc in example_testcases if tc and tc.strip()]
    return examples
