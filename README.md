# ALZ Inquiry Router (simulation)

A demo for the Claude Corps / CodePath Basecamp program, built for the Alzheimer's Association host project by Aiden Kaouk and Katrina Silvers.

**This is a simulation.** It is not the official alz.org site and not connected to any Association system. All teams, contacts, emails and messages are invented sample data. Never put real personal information in this repo.

## The idea
The real Contact Us form has only a free-text Comments box, so staff sort every message by hand. This demo shows a router that reads each message, suggests which team(s) should handle it, and gives staff a one-click approval. Nothing is sent without a staff member approving it.

See [PLAN.md](PLAN.md) for the full design.

## Run the demo
Offline mode uses saved answers for the 30 test messages (no API key, no cost):

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt    # first time only
ROUTER_MODE=cache .venv/bin/python -m server.app
```

Then open (use `127.0.0.1`; on a Mac, `localhost:5000` is taken by AirPlay, so the demo uses port 5050):
- Public form: http://127.0.0.1:5050/contact.html (pick a sample message, Submit)
- Triage console: http://127.0.0.1:5050/console.html (review and Approve)
- Team inbox: http://127.0.0.1:5050/team.html (choose a team to "view as")

Run the tests with `.venv/bin/python -m pytest`. Cases are saved in `var/cases.json` (git-ignored; delete it to reset).
