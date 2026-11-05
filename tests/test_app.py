"""Tests for the intake server and console API. Offline: saved answers, temp storage."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server.app import create_app  # noqa: E402
from server.cases import CaseStore  # noqa: E402

BY_ID = {m["id"]: m for m in json.loads((ROOT / "tests" / "messages.json").read_text())}


@pytest.fixture
def client(tmp_path):
    app = create_app(store=CaseStore(tmp_path / "cases.json"), mode="cache")
    return app.test_client()


def form_for(msg_id):
    """Build the same JSON the web form sends, from a test message."""
    m = BY_ID[msg_id]
    s = m["submitter"]
    return {
        "first_name": s["first_name"], "last_name": s["last_name"], "email": s["email"],
        "zip": s["zip"], "phone_number": s["phone"], "street1": s.get("address", ""),
        "comments": m["comments"], "language": "en",
    }


def submit(client, msg_id):
    r = client.post("/api/inquiries", json=form_for(msg_id))
    assert r.status_code == 201
    return r.get_json()["case_id"]


# --- Intake -----------------------------------------------------------------

def test_submission_creates_a_case_and_returns_only_the_id(client):
    r = client.post("/api/inquiries", json=form_for("M02"))
    assert r.status_code == 201
    assert list(r.get_json()) == ["case_id"]      # no routing info to the public form
    case = client.get(f"/api/cases/{r.get_json()['case_id']}").get_json()
    assert case["route"]["teams"] == ["DON"]
    assert case["submitter"]["email"] == BY_ID["M02"]["submitter"]["email"]
    assert case["language"] == "en"


def test_case_ids_are_unique_and_count_up(client):
    assert submit(client, "M02") == "CASE-1042"
    assert submit(client, "M03") == "CASE-1043"


@pytest.mark.parametrize("field", ["first_name", "last_name", "email", "zip", "comments"])
def test_missing_required_field_is_rejected(client, field):
    body = form_for("M02")
    body[field] = " "
    assert client.post("/api/inquiries", json=body).status_code == 400


def test_comments_over_limit_rejected(client):
    body = form_for("M02")
    body["comments"] = "x" * 2501
    assert client.post("/api/inquiries", json=body).status_code == 400


# --- Privacy: contact details never reach the router/Claude -------------------

@pytest.mark.parametrize("msg_id", ["M02", "M29", "M30"])
def test_contact_details_not_in_what_claude_saw(client, msg_id):
    case_id = submit(client, msg_id)
    case = client.get(f"/api/cases/{case_id}").get_json()
    saw = case["route"]["what_claude_saw"]
    s = BY_ID[msg_id]["submitter"]
    for secret in [s["first_name"], s["last_name"], s["email"], s["phone"]]:
        assert secret not in saw
    assert set(saw.replace("</case_id>", "<case_id>").split("<")[1:]) >= {"case_id>" + case_id}


def test_queue_listing_hides_contact_details(client):
    submit(client, "M29")
    row = client.get("/api/cases").get_json()[0]
    assert "email" not in json.dumps(row) and "555-0142" not in json.dumps(row)


# --- Queue and decisions ------------------------------------------------------

def test_crisis_cases_come_first_in_the_queue(client):
    submit(client, "M02")
    crisis_id = submit(client, "M08")
    rows = client.get("/api/cases").get_json()
    assert rows[0]["case_id"] == crisis_id and rows[0]["needs_human"] is True
    assert "HELP" in rows[0]["teams"]


def test_approve_records_decision_and_audit(client):
    case_id = submit(client, "M02")
    r = client.post(f"/api/cases/{case_id}/decision", json={"action": "approve"})
    case = r.get_json()
    assert case["status"] == "approved" and case["decision"]["teams"] == ["DON"]
    assert case["audit"][0]["action"] == "approve"


def test_approve_with_changed_teams(client):
    case_id = submit(client, "M02")
    r = client.post(f"/api/cases/{case_id}/decision", json={"action": "approve", "teams": ["PG", "DON"]})
    d = r.get_json()["decision"]
    assert d["teams"] == ["PG", "DON"] and d["suggested_teams"] == ["DON"] and d["changed"] is True


def test_approve_without_changes_is_not_marked_changed(client):
    case_id = submit(client, "M02")
    d = client.post(f"/api/cases/{case_id}/decision", json={"action": "approve", "teams": ["DON"]}).get_json()["decision"]
    assert d["changed"] is False


def test_approve_rejects_unknown_team_or_empty_list(client):
    case_id = submit(client, "M02")
    for teams in (["NOPE"], []):
        r = client.post(f"/api/cases/{case_id}/decision", json={"action": "approve", "teams": teams})
        assert r.status_code == 400


def test_crisis_case_cannot_lose_the_helpline(client):
    case_id = submit(client, "M08")
    r = client.post(f"/api/cases/{case_id}/decision", json={"action": "approve", "teams": ["DON"]})
    assert r.get_json()["decision"]["teams"][0] == "HELP"


def test_triage_is_not_a_team_staff_can_assign(client):
    case_id = submit(client, "M02")
    r = client.post(f"/api/cases/{case_id}/decision", json={"action": "approve", "teams": ["TRIAGE"]})
    assert r.status_code == 400
    assert "TRIAGE" not in [t["team_id"] for t in client.get("/api/teams").get_json()]


def test_router_unsure_case_needs_staff_to_pick_teams(client):
    # M26 is vague: the router says TRIAGE, which in the console means "unsorted".
    case_id = submit(client, "M26")
    assert client.get(f"/api/cases/{case_id}").get_json()["route"]["teams"] == ["TRIAGE"]
    assert client.post(f"/api/cases/{case_id}/decision", json={"action": "approve"}).status_code == 400
    r = client.post(f"/api/cases/{case_id}/decision", json={"action": "approve", "teams": ["CHAP"]})
    d = r.get_json()["decision"]
    assert d["teams"] == ["CHAP"] and d["changed"] is True


def test_followup_keeps_case_open_and_assigns_no_team(client):
    case_id = submit(client, "M26")
    r = client.post(f"/api/cases/{case_id}/decision", json={"action": "followup", "note": "Ask what they need"})
    case = r.get_json()
    assert case["status"] == "needs_followup"
    assert case["decision"]["teams"] == [] and case["decision"]["note"] == "Ask what they need"
    assert case["decision"]["changed"] is False
    # It can still be sorted and approved later.
    r = client.post(f"/api/cases/{case_id}/decision", json={"action": "approve", "teams": ["DON"]})
    assert r.get_json()["status"] == "approved"


def test_crisis_followup_still_keeps_the_helpline(client):
    case_id = submit(client, "M08")
    r = client.post(f"/api/cases/{case_id}/decision", json={"action": "followup"})
    assert r.get_json()["decision"]["teams"] == ["HELP"]


def test_queue_order_crisis_then_open_then_followup_then_approved(client):
    a = submit(client, "M02")
    b = submit(client, "M26")
    c = submit(client, "M03")
    client.post(f"/api/cases/{b}/decision", json={"action": "followup"})
    client.post(f"/api/cases/{a}/decision", json={"action": "approve"})
    crisis = submit(client, "M08")
    order = [r["case_id"] for r in client.get("/api/cases").get_json()]
    assert order == [crisis, c, b, a]


def test_bad_action_and_unknown_case(client):
    case_id = submit(client, "M02")
    assert client.post(f"/api/cases/{case_id}/decision", json={"action": "reroute"}).status_code == 400
    assert client.get("/api/cases/CASE-9999").status_code == 404
    assert client.post("/api/cases/CASE-9999/decision", json={"action": "approve"}).status_code == 404
