"""Build the exact message that is sent to Claude.

This is the ONE place where the request content is assembled. Only two fields
are allowed in: the case ID and the already-redacted Comments text. Anything
else raises an error, and tests/test_privacy.py checks this.

The message text is wrapped in <message> tags and any "<" or ">" in it is
escaped, so a message cannot close the tag early and pretend to be
instructions (prompt injection).
"""

import html
import re
from typing import Dict

ALLOWED_FIELDS = ("case_id", "comments")

CASE_ID_RE = re.compile(r"^CASE-[A-Z0-9-]{1,20}$")


class PayloadError(ValueError):
    pass


def build_payload(**fields) -> Dict[str, str]:
    """Return the allowed fields, refusing anything extra.

    Call as build_payload(case_id="CASE-1042", comments=redacted_text).
    """
    extra = set(fields) - set(ALLOWED_FIELDS)
    if extra:
        raise PayloadError(f"Not allowed to send to Claude: {sorted(extra)}")
    missing = set(ALLOWED_FIELDS) - set(fields)
    if missing:
        raise PayloadError(f"Missing required fields: {sorted(missing)}")

    case_id = str(fields["case_id"])
    # The case ID has a strict shape so it cannot be used to smuggle other data.
    if not CASE_ID_RE.match(case_id):
        raise PayloadError("case_id must look like CASE-1042")

    return {"case_id": case_id, "comments": str(fields["comments"])}


def render_user_message(payload: Dict[str, str]) -> str:
    """Turn the payload into the text of the user message sent to Claude."""
    # Re-check, in case someone builds the dict by hand.
    build_payload(**payload)
    safe_comments = html.escape(payload["comments"], quote=False)
    return (
        f"<case_id>{payload['case_id']}</case_id>\n"
        f"<message>\n{safe_comments}\n</message>"
    )
