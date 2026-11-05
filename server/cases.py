"""Case storage: one form submission = one case, kept in a JSON file.

The full record (name, email, phone, address, message) lives ONLY here, on our
side. The router is given just the case ID and the Comments text.

For the demo a single JSON file is enough. Not safe for many users at once.
"""

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FILE = ROOT / "var" / "cases.json"   # var/ is git-ignored
FIRST_NUMBER = 1042

# Form fields we keep. Anything else in a submission is dropped.
SUBMITTER_FIELDS = [
    "first_name", "last_name", "email", "email_type", "street1", "street2",
    "country", "zip", "city", "state", "phone_area", "phone_number", "phone_type",
]

_lock = threading.Lock()


class CaseStore:
    def __init__(self, path: Path = DEFAULT_FILE):
        self.path = Path(path)

    # -- file helpers --
    def _load(self) -> List[Dict[str, Any]]:
        if self.path.exists():
            return json.loads(self.path.read_text())
        return []

    def _save(self, cases: List[Dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(cases, indent=2) + "\n")

    # -- public API --
    def next_case_id(self) -> str:
        return f"CASE-{FIRST_NUMBER + len(self._load())}"

    def create(self, form: Dict[str, Any], route_result: Dict[str, Any],
               case_id: str) -> Dict[str, Any]:
        case = {
            "case_id": case_id,
            "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "language": form.get("language", "en"),
            "submitter": {k: form.get(k, "") for k in SUBMITTER_FIELDS},
            "comments": form.get("comments", ""),
            "route": route_result,
            "status": "needs_review",       # needs_review -> approved
            "decision": None,               # filled in when staff act
            "audit": [],
        }
        with _lock:
            cases = self._load()
            cases.append(case)
            self._save(cases)
        return case

    def list(self) -> List[Dict[str, Any]]:
        return self._load()

    def get(self, case_id: str) -> Optional[Dict[str, Any]]:
        return next((c for c in self._load() if c["case_id"] == case_id), None)

    def decide(self, case_id: str, action: str, teams: List[str],
               suggested: Optional[List[str]] = None,
               staff: str = "demo staff") -> Optional[Dict[str, Any]]:
        """Record a staff decision. Nothing is sent anywhere."""
        with _lock:
            cases = self._load()
            case = next((c for c in cases if c["case_id"] == case_id), None)
            if case is None:
                return None
            case["status"] = "approved"
            suggested = suggested if suggested is not None else teams
            changed = action == "approve" and sorted(teams) != sorted(suggested)
            case["decision"] = {"action": action, "teams": teams,
                                "suggested_teams": suggested, "changed": changed}
            case["audit"].append({
                "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "staff": staff,
                "action": action,
                "teams": teams,
                "suggested_teams": suggested,
                "changed": changed,
            })
            self._save(cases)
            return case
