"""Remove personal details from the Comments text before it is sent to Claude.

How it works, in plain terms:
1. First, anything that matches the submitter's own form fields (name, email,
   phone, address, ZIP) is replaced. This is the most reliable step, because we
   know exactly what to look for.
2. Then general patterns catch details the person typed that do not match their
   form: other emails, phone numbers, street addresses, ZIP codes and ID-like
   numbers (e.g. "donor ID 4471-8820").
3. "My name is ..." style introductions are caught as a last safety net.

Each removed item becomes a placeholder such as [EMAIL] so the meaning of the
sentence survives ("call me at [PHONE]").

Known limit: names of OTHER people in free text ("my sister Jane") are not
removed. See docs/step-3-plan.md.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, Mapping

# --- General patterns --------------------------------------------------------

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")

# 10-digit US numbers: 312-555-0101, (312) 555-0101, +1 312.555.0101
PHONE_LONG_RE = re.compile(r"(?<!\w)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]\d{4}(?!\w)")
# 7-digit local numbers: 555-0177
PHONE_SHORT_RE = re.compile(r"(?<![\w-])\d{3}[.-]\d{4}(?![\w-])")

STREET_WORDS = (
    "Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|"
    "Way|Place|Pl|Terrace|Circle|Cir|Parkway|Pkwy|Highway|Hwy"
)
ADDRESS_RE = re.compile(
    r"\b\d{1,6}\s+(?:[A-Z][\w'-]*\s+){1,3}(?:" + STREET_WORDS + r")\b\.?"
    r"(?:,?\s+(?:Apt|Apartment|Unit|Suite|Ste|#)\.?\s*\w+)?"
)

# ID-like numbers: groups of digits joined by dashes or spaces (4471-8820),
# or one long run of 6+ digits (account numbers).
ID_RE = re.compile(r"(?<![\w$])(?:\d{2,}(?:[-\s]\d{2,})+|\d{6,})(?![\w])")

# US ZIP codes (60614 or 60614-1234). The "$" check skips money like "$50000".
ZIP_RE = re.compile(r"(?<![\w$,.])\d{5}(?:-\d{4})?(?![\w,])")

# "My name is Jane Doe" / "I am Jane Doe" / "This is Jane Doe"
_NOT_NAMES = {"The", "A", "An", "Not", "Very", "So", "Just", "Also", "Your", "My", "Our"}
INTRO_RE = re.compile(
    r"\b(?:[Mm]y name is|I am|I'm|This is)\s+([A-Z][a-z'-]+)(?:\s+([A-Z][a-z'-]+))?"
)


@dataclass
class RedactionResult:
    text: str
    # How many items of each kind were removed, e.g. {"EMAIL": 1, "PHONE": 1}.
    # Shown to staff; never contains the removed values themselves.
    removed: Dict[str, int] = field(default_factory=dict)


def _sub(pattern, label, text, removed):
    new_text, n = pattern.subn(f"[{label}]", text)
    if n:
        removed[label] = removed.get(label, 0) + n
    return new_text


def _literal(value, flags=re.IGNORECASE):
    """Pattern that matches a form value as a whole word, ignoring spacing."""
    words = [re.escape(w) for w in value.split()]
    return re.compile(r"(?<!\w)" + r"\s+".join(words) + r"(?!\w)", flags)


def _digits_pattern(value):
    """Match a phone number by its digits, whatever separators were typed."""
    digits = re.sub(r"\D", "", value)
    if len(digits) < 7:
        return None
    return re.compile(r"(?<!\d)" + r"[\s().-]*".join(digits) + r"(?!\d)")


def redact(text: str, submitter: Mapping[str, str]) -> RedactionResult:
    removed: Dict[str, int] = {}
    s = submitter or {}

    def val(key):
        return (s.get(key) or "").strip()

    # 1. The submitter's own form fields (longest, most specific first).
    if val("email"):
        text = _sub(_literal(val("email")), "EMAIL", text, removed)
    if val("phone"):
        pat = _digits_pattern(val("phone"))
        if pat:
            text = _sub(pat, "PHONE", text, removed)
    if val("address"):
        address = val("address")
        text = _sub(_literal(address), "ADDRESS", text, removed)
        street = address.split(",")[0].strip()  # "412 Birch Street"
        if street and street != address:
            text = _sub(_literal(street), "ADDRESS", text, removed)
    if val("zip"):
        text = _sub(_literal(val("zip")), "ZIP", text, removed)

    first, last = val("first_name"), val("last_name")
    if first and last:
        text = _sub(_literal(f"{first} {last}"), "NAME", text, removed)
    # Single names: match only when capitalised, so a name like "Will" does
    # not wipe out the ordinary word "will".
    for name in (first, last):
        if len(name) >= 2:
            text = _sub(_literal(name, flags=0), "NAME", text, removed)

    # 2. General patterns for details that do not match the form.
    text = _sub(EMAIL_RE, "EMAIL", text, removed)
    text = _sub(ADDRESS_RE, "ADDRESS", text, removed)
    text = _sub(PHONE_LONG_RE, "PHONE", text, removed)
    text = _sub(PHONE_SHORT_RE, "PHONE", text, removed)
    text = _sub(ID_RE, "ID", text, removed)
    text = _sub(ZIP_RE, "ZIP", text, removed)

    # 3. Self-introductions with a name we did not know about.
    def _intro(m):
        names = [g for g in m.groups() if g]
        if names[0] in _NOT_NAMES:
            return m.group(0)
        removed["NAME"] = removed.get("NAME", 0) + 1
        return m.group(0)[: m.start(1) - m.start(0)] + "[NAME]"

    text = INTRO_RE.sub(_intro, text)

    return RedactionResult(text=text, removed=removed)
