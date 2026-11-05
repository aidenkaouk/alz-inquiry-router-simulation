"""Simulated handoff emails.

When staff approve a case, each team on it would get an email pointing at the
shared case. In this demo nothing is ever sent: we only BUILD the text so the
demo can show exactly what each team would receive.

The sender's contact details are added here by ordinary code. They are never
part of what Claude sees (see server/payload.py).
"""

import csv
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
CONTACTS_FILE = ROOT / "data" / "contacts.csv"
TEAMS_FILE = ROOT / "data" / "teams.csv"
STATUS_LABELS = {"pending": "Pending", "replied": "Replied", "no_reply_needed": "No reply needed"}
_LEVEL_ORDER = {"primary": 0, "lead-of-team": 0, "backup": 1}


def _read(path: Path) -> List[Dict[str, str]]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def pick_contact(team_id: str, zip_code: str, contacts: Optional[List[Dict[str, str]]] = None):
    """Choose the named person who would get the email.

    Chapter Operations has one regional manager per ZIP range (first digit of the
    ZIP). Every other team uses its primary contact (Triage: its lead).
    """
    contacts = contacts if contacts is not None else _read(CONTACTS_FILE)
    rows = [c for c in contacts if c["team_id"] == team_id]
    if team_id == "CHAP" and zip_code[:1].isdigit():
        digit = int(zip_code[0])
        for c in rows:
            m = re.search(r"ZIP (\d)-(\d)", c["coverage"])
            if m and int(m.group(1)) <= digit <= int(m.group(2)):
                return c
    rows.sort(key=lambda c: _LEVEL_ORDER.get(c["level"], 9))
    return rows[0] if rows else None


def build_emails(case: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One simulated email per team on an approved case."""
    names = {t["team_id"]: t["team_name"] for t in _read(TEAMS_FILE)}
    contacts = _read(CONTACTS_FILE)
    route, sub = case["route"], case["submitter"]
    team_status = case.get("team_status", {})
    phone = (sub.get("phone_area", "") + " " + sub.get("phone_number", "")).strip() or "(none given)"
    emails = []
    for team in (case.get("decision") or {}).get("teams", []):
        contact = pick_contact(team, sub.get("zip", ""), contacts)
        mine = [s["text"] for s in route.get("segments", []) if s["team"] == team]
        lines = [
            "SIMULATED EMAIL. Not sent to anyone.",
            "",
            f"Case {case['case_id']} was approved by Constituent Triage and assigned to your team.",
        ]
        if route.get("needs_human"):
            lines += ["", "CRISIS FLAG: a person must look at this case now."]
        lines += ["", "Your part of the message:"]
        if mine:
            lines += [f'  "{t}"' for t in mine]
        else:
            lines += ["  (No separate part was assigned to your team. Please read the whole message.)"]
        lines += ["", "Full message:", f'  "{case["comments"]}"']
        if route.get("handoff_note"):
            lines += ["", f"Handoff note: {route['handoff_note']}"]
        for flag in route.get("staff_flags", []):
            lines += [f"Staff flag: {flag}"]
        lines += ["", "Other teams on this case (all teams are equals; each owns its own part):"]
        others = [t for t in team_status if t != team]
        lines += [f"  - {t} ({names.get(t, t)}): {STATUS_LABELS[team_status[t]['status']]}" for t in others] or ["  (none)"]
        lines += [
            "",
            "Sender (added by our own code, never shown to Claude):",
            f"  {sub.get('first_name', '')} {sub.get('last_name', '')}".rstrip(),
            f"  {sub.get('email', '')}  |  {phone}  |  ZIP {sub.get('zip', '')}",
            "",
            f"Next step: open the Team Inbox, view as {team}, and set your status.",
        ]
        emails.append({
            "team_id": team,
            "team_name": names.get(team, team),
            "to_name": contact["name"] if contact else "(no contact on file)",
            "to_email": contact["email"] if contact else "",
            "to_role": contact["role"] if contact else "",
            "subject": f"[{case['case_id']}] New inquiry for {names.get(team, team)}",
            "body": "\n".join(lines),
            "simulated": True,
        })
    return emails
