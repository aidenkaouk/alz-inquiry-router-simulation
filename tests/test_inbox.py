"""Tests for step 6: team inbox, per-team status, shared notes and simulated outbox.
Offline: saved answers and temporary storage."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server.app import create_app  # noqa: E402
from server.cases import CaseStore  # noqa: E402
from server.outbox import pick_contact  # noqa: E402

BY_ID = {m["id"]: m for m in json.loads((ROOT / "tests" / "messages.json").read_text())}


@pytest.fixture
def client(tmp_path):
    return create_app(store=CaseStore(tmp_path / "cases.json"), mode="cache").test_client()


def submit(client, msg_id):
    m = BY_ID[msg_id]
    s = m["submitter"]
    body = {"first_name": s["first_name"], "last_name": s["last_name"], "email": s["email"],
            "zip": s["zip"], "phone_number": s["phone"], "comments": m["comments"]}
    return client.post("/api/inquiries", json=body).get_json()["case_id"]


def approve(client, case_id, teams=None):
    body = {"action": "approve"}
    if teams is not None:
        body["teams"] = teams
    r = client.post(f"/api/cases/{case_id}/decision", json=body)
    assert r.status_code == 200
    return r.get_json()


def two_team_case(client):
    """M20 goes to DON + WALK."""
    case_id = submit(client, "M20")
    approve(client, case_id)
    return case_id


def set_status(client, case_id, team, status, as_team=None):
    return client.post(f"/api/cases/{case_id}/teams/{team}/status",
                       json={"status": status, "as_team": as_team or team})


# --- Per-team status ---------------------------------------------------------

def test_approval_gives_every_team_its_own_pending_status(client):
    case = client.get(f"/api/cases/{two_team_case(client)}").get_json()
    assert set(case["team_status"]) == {"DON", "WALK"}
    assert all(v["status"] == "pending" for v in case["team_status"].values())
    assert case["closed"] is False


def test_a_case_can_only_be_approved_once(client):
    case_id = two_team_case(client)
    r = client.post(f"/api/cases/{case_id}/decision", json={"action": "approve", "teams": ["PG"]})
    assert r.status_code == 409
    assert set(client.get(f"/api/cases/{case_id}").get_json()["team_status"]) == {"DON", "WALK"}


def test_team_changes_its_own_status_without_touching_the_other(client):
    case_id = two_team_case(client)
    case = set_status(client, case_id, "WALK", "replied").get_json()
    assert case["team_status"]["WALK"]["status"] == "replied"
    assert case["team_status"]["DON"]["status"] == "pending"


def test_a_team_cannot_change_another_teams_status(client):
    case_id = two_team_case(client)
    assert set_status(client, case_id, "DON", "replied", as_team="WALK").status_code == 403
    assert set_status(client, case_id, "DON", "replied", as_team="TRIAGE").status_code == 403   # Triage only watches
    assert client.get(f"/api/cases/{case_id}").get_json()["team_status"]["DON"]["status"] == "pending"


def test_status_must_be_a_known_value_and_team_must_be_on_the_case(client):
    case_id = two_team_case(client)
    assert set_status(client, case_id, "WALK", "done").status_code == 400
    assert set_status(client, case_id, "PG", "replied").status_code == 404
    assert set_status(client, "CASE-9999", "WALK", "replied").status_code == 404


def test_case_closes_only_when_every_team_is_resolved(client):
    case_id = two_team_case(client)
    assert set_status(client, case_id, "WALK", "replied").get_json()["closed"] is False
    assert set_status(client, case_id, "DON", "no_reply_needed").get_json()["closed"] is True
    assert set_status(client, case_id, "DON", "pending").get_json()["closed"] is False   # reopened


def test_unapproved_case_has_no_statuses_and_cannot_be_updated(client):
    case_id = submit(client, "M20")
    assert client.get(f"/api/cases/{case_id}").get_json()["team_status"] == {}
    assert set_status(client, case_id, "WALK", "replied").status_code == 404


# --- Team inbox lists ---------------------------------------------------------

def test_inbox_lists_only_approved_cases_that_include_the_team(client):
    mine = two_team_case(client)
    other = submit(client, "M02")           # DON only
    approve(client, other)
    unapproved = submit(client, "M20")      # never approved
    walk = [r["case_id"] for r in client.get("/api/teams/WALK/cases").get_json()]
    don = [r["case_id"] for r in client.get("/api/teams/DON/cases").get_json()]
    assert walk == [mine]
    assert set(don) == {mine, other}
    assert unapproved not in walk + don


def test_inbox_row_shows_my_status_and_every_teams_status(client):
    case_id = two_team_case(client)
    set_status(client, case_id, "WALK", "replied")
    row = client.get("/api/teams/DON/cases").get_json()[0]
    assert row["my_status"] == "pending"
    assert row["teams"] == {"DON": "pending", "WALK": "replied"}


def test_triage_watches_every_approved_case(client):
    a = two_team_case(client)
    b = submit(client, "M03")
    approve(client, b)
    rows = client.get("/api/teams/TRIAGE/cases").get_json()
    assert {r["case_id"] for r in rows} == {a, b}
    assert all(r["my_status"] is None for r in rows)      # Triage has no status of its own


def test_closed_cases_sort_to_the_bottom_and_open_crisis_to_the_top(client):
    done = submit(client, "M02")
    approve(client, done)
    set_status(client, done, "DON", "replied")
    plain = submit(client, "M03")
    approve(client, plain, ["DON"])
    crisis = submit(client, "M10")           # HELP + DON, crisis
    approve(client, crisis)
    order = [r["case_id"] for r in client.get("/api/teams/DON/cases").get_json()]
    assert order == [crisis, plain, done]


def test_unknown_team_inbox_is_404(client):
    assert client.get("/api/teams/NOPE/cases").status_code == 404


# --- Shared notes ---------------------------------------------------------------

def test_notes_are_shared_and_tagged_with_the_writing_team(client):
    case_id = two_team_case(client)
    client.post(f"/api/cases/{case_id}/notes", json={"as_team": "WALK", "text": "I will call her."})
    client.post(f"/api/cases/{case_id}/notes", json={"as_team": "DON", "text": "Receipt re-sent."})
    notes = client.get(f"/api/cases/{case_id}").get_json()["notes"]
    assert [(n["team"], n["text"]) for n in notes] == [("WALK", "I will call her."), ("DON", "Receipt re-sent.")]


def test_notes_rules(client):
    case_id = two_team_case(client)
    post = lambda **b: client.post(f"/api/cases/{case_id}/notes", json=b)
    assert post(as_team="TRIAGE", text="Watching.").status_code == 201
    assert post(as_team="PG", text="Not my case").status_code == 403         # not on the case
    assert post(as_team="WALK", text="   ").status_code == 400
    assert post(as_team="WALK", text="x" * 501).status_code == 400


# --- Simulated outbox -------------------------------------------------------------

def test_one_simulated_email_per_team_and_none_before_approval(client):
    case_id = submit(client, "M20")
    assert client.get(f"/api/cases/{case_id}/outbox").status_code == 409
    approve(client, case_id)
    emails = client.get(f"/api/cases/{case_id}/outbox").get_json()
    assert {e["team_id"] for e in emails} == {"DON", "WALK"}
    for e in emails:
        assert e["simulated"] is True and "SIMULATED EMAIL. Not sent" in e["body"]
        assert e["to_email"].endswith("@alz-demo.example")
        assert case_id in e["subject"]


def test_email_names_the_other_team_and_its_current_status(client):
    case_id = two_team_case(client)
    set_status(client, case_id, "WALK", "replied")
    don = next(e for e in client.get(f"/api/cases/{case_id}/outbox").get_json() if e["team_id"] == "DON")
    assert "WALK (Walk & Events): Replied" in don["body"]
    assert "DON (" not in don["body"].split("Other teams")[1]        # a team is not listed as its own "other"


def test_email_gives_each_team_its_own_part_of_the_message(client):
    case_id = two_team_case(client)
    emails = {e["team_id"]: e["body"] for e in client.get(f"/api/cases/{case_id}/outbox").get_json()}
    case = client.get(f"/api/cases/{case_id}").get_json()
    for seg in case["route"]["segments"]:
        mine = emails[seg["team"]].split("Full message")[0]
        assert seg["text"] in mine


def test_email_has_sender_details_but_claude_never_saw_them(client):
    case_id = two_team_case(client)
    s = BY_ID["M20"]["submitter"]
    case = client.get(f"/api/cases/{case_id}").get_json()
    body = client.get(f"/api/cases/{case_id}/outbox").get_json()[0]["body"]
    assert s["email"] in body and s["first_name"] in body
    assert s["email"] not in case["route"]["what_claude_saw"]


def test_crisis_flag_appears_in_the_email(client):
    case_id = submit(client, "M08")
    approve(client, case_id)
    emails = client.get(f"/api/cases/{case_id}/outbox").get_json()
    assert emails[0]["team_id"] == "HELP" and "CRISIS FLAG" in emails[0]["body"]


def test_team_without_its_own_segment_is_told_to_read_the_whole_message(client):
    case_id = submit(client, "M02")           # DON only
    approve(client, case_id, ["DON", "PG"])   # staff add PG, which has no segment
    pg = next(e for e in client.get(f"/api/cases/{case_id}/outbox").get_json() if e["team_id"] == "PG")
    assert "No separate part was assigned" in pg["body"]


# --- Choosing the named contact --------------------------------------------------

@pytest.mark.parametrize("zip_code,name", [
    ("60614", "Hannah Eriksen"), ("10001", "Lucille Banerjee"),
    ("33101", "Raymond Castellanos"), ("98101", "Tyrone Whitaker"),
])
def test_chapter_contact_is_chosen_by_zip(zip_code, name):
    assert pick_contact("CHAP", zip_code)["name"] == name


def test_non_chapter_teams_use_their_primary_contact_and_triage_its_lead():
    assert pick_contact("WALK", "60614")["level"] == "primary"
    assert pick_contact("TRIAGE", "60614")["level"] == "lead-of-team"
    assert pick_contact("CHAP", "")["level"] == "primary"        # no ZIP: national contact


# --- Cases saved by an earlier version (before per-team statuses existed) ----------

def test_old_approved_cases_without_team_status_still_work(tmp_path):
    old = {"case_id": "CASE-1042", "created": "2026-11-05T10:00:00", "language": "en",
           "submitter": {"first_name": "Old", "last_name": "Case", "email": "o@example.org", "zip": "60614"},
           "comments": "I want to volunteer at the Walk.",
           "route": {"teams": ["WALK"], "needs_human": False, "segments": [], "staff_flags": [], "handoff_note": "",
                     "what_claude_saw": ""},
           "status": "approved", "decision": {"action": "approve", "teams": ["WALK", "VOL"], "changed": False},
           "audit": [{"time": "2026-11-05T10:05:00"}]}          # no team_status, no notes
    path = tmp_path / "cases.json"
    path.write_text(json.dumps([old]))
    c = create_app(store=CaseStore(path), mode="cache").test_client()
    rows = c.get("/api/teams/WALK/cases")
    assert rows.status_code == 200
    assert rows.get_json()[0]["teams"] == {"WALK": "pending", "VOL": "pending"}
    assert c.get("/api/cases/CASE-1042/outbox").status_code == 200
    assert set_status(c, "CASE-1042", "WALK", "replied").status_code == 200
    assert c.get("/api/cases/CASE-1042").get_json()["notes"] == []
