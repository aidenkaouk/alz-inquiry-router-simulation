"""Local demo server: serves the web pages, receives form submissions and
feeds the staff console.

Run:  .venv/bin/python -m server.app     then open http://127.0.0.1:5000

PRIVACY: the router only ever receives the case ID and the Comments text
(see server/payload.py). Name, email, phone and address stay in the case record.
There is no login: this is a local demo, never expose it to a network.
"""

import os
from pathlib import Path

from flask import Flask, abort, jsonify, request

from server import router
from server.cases import CaseStore

ROOT = Path(__file__).resolve().parent.parent
MAX_COMMENTS = 2500
REQUIRED = ["first_name", "last_name", "email", "zip", "comments"]
ACTIONS = ["approve"]
# The person at the console IS the Constituent Triage team (see PLAN.md), so cases
# are never assigned to TRIAGE by staff. Invented person from data/contacts.csv.
STAFF = "Beatrice Lowell (Constituent Triage, demo)"


def create_app(store=None, mode=None):
    """mode: "auto" (live Claude, falling back to saved answers), "live" or "cache"."""
    app = Flask(__name__, static_folder=str(ROOT / "web"), static_url_path="")
    store = store or CaseStore()
    mode = mode or os.environ.get("ROUTER_MODE", "auto")
    valid_teams = {t["team_id"] for t in router.load_teams()} - {"TRIAGE"}

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
        submitter = {k: str(form.get(k, "")) for k in
                     ["first_name", "last_name", "email", "street1", "street2",
                      "city", "zip", "phone_area", "phone_number"]}
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
        return jsonify(case)

    @app.post("/api/cases/<case_id>/decision")
    def decide(case_id):
        case = store.get(case_id)
        if case is None:
            abort(404)
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

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=False)
