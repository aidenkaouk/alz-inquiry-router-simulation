"""Local demo server: serves the web pages, receives form submissions and
feeds the staff console.

Run:  .venv/bin/python -m server.app     then open http://127.0.0.1:5050

PRIVACY: the router only ever receives the case ID and the Comments text
(see server/payload.py). Name, email, phone and address stay in the case record.
There is no login: this is a local demo, never expose it to a network.
"""

import os
from pathlib import Path

from flask import Flask, abort, jsonify, request

from server import router
from server.cases import STATUSES, CaseStore, is_closed
from server.outbox import build_emails

ROOT = Path(__file__).resolve().parent.parent
MAX_COMMENTS = 2500
REQUIRED = ["first_name", "last_name", "email", "zip", "comments"]
ACTIONS = ["approve"]
# The person at the console IS the Constituent Triage team (see PLAN.md), so cases
# are never assigned to TRIAGE by staff. Invented person from data/contacts.csv.
STAFF = "Beatrice Lowell (Constituent Triage, demo)"
MAX_NOTE = 500


def redaction_fields(form):
    """Turn the form's boxes into the names the redactor understands.

    redact() looks for `address` and `phone`; the form has separate street, city and
    phone boxes. Without this step the sender's own address and phone would NOT be
    matched against the message text. Used only for redaction; never sent to Claude."""
    get = lambda k: str(form.get(k, "") or "").strip()
    return {
        "first_name": get("first_name"), "last_name": get("last_name"),
        "email": get("email"), "zip": get("zip"),
        "address": ", ".join(p for p in (get("street1"), get("street2"), get("city")) if p),
        "phone": (get("phone_area") + get("phone_number")),
    }


def create_app(store=None, mode=None):
    """mode: "auto" (live Claude, falling back to saved answers), "live" or "cache"."""
    app = Flask(__name__, static_folder=str(ROOT / "web"), static_url_path="")
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0   # browsers always fetch the latest page files
    store = store or CaseStore()
    mode = mode or os.environ.get("ROUTER_MODE", "auto")
    all_teams = {t["team_id"] for t in router.load_teams()}
    valid_teams = all_teams - {"TRIAGE"}          # teams staff can assign a case to

    @app.get("/")
    def home():
        return app.send_static_file("index.html")

    @app.get("/api/teams")
    def teams():
        # TRIAGE is left out: staff at the console are the triage team.
        return jsonify([{"team_id": t["team_id"], "team_name": t["team_name"]}
                        for t in router.load_teams() if t["team_id"] != "TRIAGE"])

    @app.post("/api/inquiries")
    def new_inquiry():
        form = request.get_json(silent=True) or {}
        missing = [f for f in REQUIRED if not str(form.get(f, "")).strip()]
        if missing:
            return jsonify({"error": "Missing required fields", "fields": missing}), 400
        comments = str(form["comments"])
        if len(comments) > MAX_COMMENTS:
            return jsonify({"error": f"Comments are over {MAX_COMMENTS} characters"}), 400

        case_id = store.next_case_id()
        # Only the case ID and the Comments go to the router. The submitter
        # fields are passed so redaction can remove them from the text; they
        # are never sent to Claude.
        submitter = redaction_fields(form)
        result = router.route(case_id, comments, submitter, mode=mode)
        store.create(form, result.to_dict(), case_id)
        return jsonify({"case_id": case_id}), 201   # no routing info to the public

    @app.get("/api/cases")
    def list_cases():
        # Queue view: crisis cases first, then oldest first. Contact details omitted.
        rows = [{
            "case_id": c["case_id"], "created": c["created"], "status": c["status"],
            "needs_human": c["route"]["needs_human"], "teams": c["route"]["teams"],
            "preview": c["comments"][:90],
            "name": f'{c["submitter"]["first_name"]} {c["submitter"]["last_name"]}'.strip(),
        } for c in store.list()]
        order = {"needs_review": 0, "approved": 1}
        rows.sort(key=lambda r: (not r["needs_human"], order[r["status"]], r["created"]))
        return jsonify(rows)

    @app.get("/api/cases/<case_id>")
    def one_case(case_id):
        case = store.get(case_id)
        if case is None:
            abort(404)
        return jsonify(dict(case, closed=is_closed(case)))

    @app.post("/api/cases/<case_id>/decision")
    def decide(case_id):
        case = store.get(case_id)
        if case is None:
            abort(404)
        if case["status"] == "approved":
            return jsonify({"error": "This case was already approved"}), 409
        body = request.get_json(silent=True) or {}
        action = body.get("action")
        if action not in ACTIONS:
            return jsonify({"error": f"action must be one of {ACTIONS}"}), 400

        needs_human = case["route"]["needs_human"]
        # "TRIAGE" in the router's answer just means "router could not decide".
        suggested = [t for t in case["route"]["teams"] if t != "TRIAGE"]

        teams_ = list(dict.fromkeys(body["teams"] if "teams" in body else suggested))
        if not teams_ or any(t not in valid_teams for t in teams_):
            return jsonify({"error": "Pick one or more valid teams"}), 400
        # Safety rule in code: a crisis case always includes the Helpline.
        if needs_human and "HELP" not in teams_:
            teams_ = ["HELP"] + teams_
        return jsonify(store.decide(case_id, "approve", teams_, suggested, staff=STAFF))


    # ---- Team inbox: each team works on its own part of a shared case ----

    @app.get("/api/teams/<team_id>/cases")
    def team_cases(team_id):
        if team_id not in all_teams:
            abort(404)
        rows = []
        for c in store.list():
            if c["status"] != "approved":
                continue
            ts = c["team_status"]
            if team_id != "TRIAGE" and team_id not in ts:
                continue                      # Triage watches every case; teams see only theirs
            rows.append({
                "case_id": c["case_id"], "created": c["created"],
                "name": f'{c["submitter"]["first_name"]} {c["submitter"]["last_name"]}'.strip(),
                "preview": c["comments"][:90], "needs_human": c["route"]["needs_human"],
                "closed": is_closed(c),
                "my_status": ts.get(team_id, {}).get("status"),
                "teams": {t: v["status"] for t, v in ts.items()},
            })
        rows.sort(key=lambda r: (r["closed"], not r["needs_human"], r["my_status"] != "pending", r["created"]))
        return jsonify(rows)

    @app.post("/api/cases/<case_id>/teams/<team_id>/status")
    def set_status(case_id, team_id):
        case = store.get(case_id)
        if case is None or case["status"] != "approved" or team_id not in case["team_status"]:
            abort(404)
        body = request.get_json(silent=True) or {}
        # A team can only change ITS OWN status. (No logins in the demo: the inbox
        # says who it is viewing as, and the server checks it matches.)
        if body.get("as_team") != team_id:
            return jsonify({"error": "A team can only change its own status"}), 403
        if body.get("status") not in STATUSES:
            return jsonify({"error": f"status must be one of {STATUSES}"}), 400
        updated = store.set_team_status(case_id, team_id, body["status"])
        return jsonify(dict(updated, closed=is_closed(updated)))

    @app.post("/api/cases/<case_id>/notes")
    def add_note(case_id):
        case = store.get(case_id)
        if case is None or case["status"] != "approved":
            abort(404)
        body = request.get_json(silent=True) or {}
        team = body.get("as_team")
        text = str(body.get("text") or "").strip()
        if team != "TRIAGE" and team not in case["team_status"]:
            return jsonify({"error": "Only teams on this case (or Triage) can add notes"}), 403
        if not text or len(text) > MAX_NOTE:
            return jsonify({"error": f"A note must be 1 to {MAX_NOTE} characters"}), 400
        updated = store.add_note(case_id, team, text)
        return jsonify(dict(updated, closed=is_closed(updated))), 201

    @app.get("/api/cases/<case_id>/outbox")
    def outbox(case_id):
        case = store.get(case_id)
        if case is None:
            abort(404)
        if case["status"] != "approved":
            return jsonify({"error": "Emails are only built after staff approve a case"}), 409
        return jsonify(build_emails(case))

    return app


if __name__ == "__main__":
    # use_reloader restarts the server when code changes, so it never runs stale code.
    # debug stays off (the debug mode allows running code from the browser).
    create_app().run(host="127.0.0.1", port=5050, debug=False, use_reloader=True)
