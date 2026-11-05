"""Router tests. These use a FAKE Claude, so they need no API key and cost nothing.

The fake records exactly what the router tried to send, which lets us check the
privacy allowlist on the real request.

Run with:  .venv/bin/pytest
"""

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from server import router
from server.router import ALLOWED_REQUEST_KEYS, apply_rules, route

MESSAGES = json.loads((Path(__file__).parent / "messages.json").read_text())
BY_ID = {m["id"]: m for m in MESSAGES}


class FakeClaude:
    """Stands in for anthropic.Anthropic(). Records every request."""

    def __init__(self, labels=None, stop_reason="end_turn"):
        self.requests = []
        self.labels = labels or {
            "segments": [{"text": "x", "team": "DON", "reason": "gift", "confidence": 0.9}],
            "crisis": False,
            "overall_confidence": 0.9,
            "handoff_note": "Donor question.",
        }
        self.stop_reason = stop_reason
        self.messages = self

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return SimpleNamespace(
            stop_reason=self.stop_reason,
            content=[
                SimpleNamespace(type="thinking", thinking=""),
                SimpleNamespace(type="text", text=json.dumps(self.labels)),
            ],
            usage=SimpleNamespace(input_tokens=10, output_tokens=5,
                                  cache_creation_input_tokens=0, cache_read_input_tokens=0),
            _request_id="req_fake",
        )


@pytest.fixture(autouse=True)
def no_real_logs_or_cache(tmp_path, monkeypatch):
    """Keep tests from writing to the real logs/ or reading the real cache."""
    monkeypatch.setattr(router, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(router, "CACHE_FILE", tmp_path / "cache.json")


def appears(value, text):
    return re.search(r"(?<!\w)" + re.escape(value) + r"(?!\w)", text, re.IGNORECASE)


def test_appears_catches_a_real_leak():
    # Guard: the whole-word check must still catch the name on its own.
    assert appears("Pat", '{"content": "Hi, I am Pat."}')
    assert not appears("Pat", '{"content": "patient participating"}')


def seg(team, confidence=0.9):
    return {"text": "x", "team": team, "reason": "r", "confidence": confidence}


def labels(*segments, crisis=False, overall=0.9):
    return {"segments": list(segments), "crisis": crisis,
            "overall_confidence": overall, "handoff_note": "n"}


# --- Privacy allowlist on the REAL request --------------------------------

@pytest.mark.parametrize("msg", MESSAGES, ids=[m["id"] for m in MESSAGES])
def test_request_contains_only_allowed_fields(msg):
    fake = FakeClaude()
    route("CASE-2001", msg["comments"], msg["submitter"], mode="live", client=fake)
    assert len(fake.requests) == 1
    req = fake.requests[0]

    # Only these request settings, and never any tools.
    assert set(req) <= ALLOWED_REQUEST_KEYS
    assert "tools" not in req

    # Exactly one user message: the case ID and the redacted comments.
    assert len(req["messages"]) == 1
    content = req["messages"][0]["content"]
    assert content.startswith("<case_id>CASE-2001</case_id>\n<message>\n")

    # No form-field value appears ANYWHERE in the request (system prompt included).
    # Whole words only: the name "Pat" must not match inside "patient".
    sent = json.dumps(req)
    for key, value in msg["submitter"].items():
        if value:
            assert not appears(value, sent), f"{msg['id']}: {key} was sent to Claude"
    for item in msg.get("pii_in_text", []):
        assert not appears(item, sent), f"{msg['id']}: '{item}' was sent to Claude"


def test_what_claude_saw_matches_the_request_exactly():
    fake = FakeClaude()
    m = BY_ID["M29"]
    result = route("CASE-2001", m["comments"], m["submitter"], mode="live", client=fake)
    assert result.what_claude_saw == fake.requests[0]["messages"][0]["content"]


def test_every_call_is_logged(tmp_path):
    fake = FakeClaude()
    route("CASE-2001", "I need a receipt", {}, mode="live", client=fake)
    log = (tmp_path / "logs" / "claude_calls.jsonl").read_text().splitlines()
    entry = json.loads(log[0])
    assert entry["case_id"] == "CASE-2001"
    assert entry["what_claude_saw"] == fake.requests[0]["messages"][0]["content"]


def test_system_prompt_has_no_contact_details():
    # The system prompt is built from teams/overlaps only, not contacts.csv.
    assert "@alz-demo.example" not in router.SYSTEM_PROMPT


# --- Our rules (plain code, after Claude) ----------------------------------

def test_single_team_passes_through():
    assert apply_rules(labels(seg("WALK")), []) == (["WALK"], False, [])


def test_more_than_three_teams_goes_to_triage():
    teams, _, reasons = apply_rules(labels(seg("DON"), seg("WALK"), seg("JOBS"), seg("CORP")), [])
    assert teams == ["TRIAGE"] and reasons


def test_low_confidence_goes_to_triage():
    teams, _, _ = apply_rules(labels(seg("DON", 0.4)), [])
    assert teams == ["TRIAGE"]


def test_claude_saying_triage_goes_to_triage():
    teams, _, _ = apply_rules(labels(seg("TRIAGE", 0.3), overall=0.3), [])
    assert teams == ["TRIAGE"]


def test_crisis_keyword_adds_help_even_if_claude_misses_it():
    teams, needs_human, _ = apply_rules(labels(seg("DON")), ["self-harm"])
    assert teams == ["HELP", "DON"] and needs_human


def test_claude_crisis_flag_also_adds_help():
    teams, needs_human, _ = apply_rules(labels(seg("DON"), crisis=True), [])
    assert "HELP" in teams and needs_human


def test_crisis_plus_triage_keeps_help():
    teams, needs_human, _ = apply_rules(labels(seg("DON", 0.2)), ["wandering"])
    assert teams == ["HELP", "TRIAGE"] and needs_human


def test_claude_down_goes_to_triage_and_crisis_still_caught():
    teams, needs_human, _ = apply_rules(None, ["self-harm"])
    assert teams == ["HELP", "TRIAGE"] and needs_human


# --- Failures are safe ------------------------------------------------------

def test_refusal_or_cutoff_goes_to_triage():
    fake = FakeClaude(stop_reason="max_tokens")
    r = route("CASE-2001", "I need a receipt", {}, mode="live", client=fake)
    assert r.teams == ["TRIAGE"] and r.error


def test_crisis_message_reaches_help_even_when_claude_is_down():
    fake = FakeClaude(stop_reason="refusal")
    m = BY_ID["M09"]
    r = route("CASE-2001", m["comments"], m["submitter"], mode="live", client=fake)
    assert "HELP" in r.teams and r.needs_human


def test_auto_mode_falls_back_to_cache():
    m = BY_ID["M02"]
    fake = FakeClaude()
    first = route("CASE-2001", m["comments"], m["submitter"], mode="live", client=fake)
    router.save_cache({router.cache_key(first.what_claude_saw): {"labels": fake.labels}})

    broken = FakeClaude(stop_reason="refusal")
    r = route("CASE-2002", m["comments"], m["submitter"], mode="auto", client=broken)
    assert r.source == "cache" and r.teams == ["DON"]


def test_cache_mode_never_calls_claude():
    fake = FakeClaude()
    route("CASE-2001", "hello", {}, mode="cache", client=fake)
    assert fake.requests == []
