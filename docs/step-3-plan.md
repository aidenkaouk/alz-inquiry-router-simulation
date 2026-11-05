# Step 3 plan: router and eval script

Status: agreed, build in progress on branch `step-3-router`.

## Goal
Answer one question before building any screens: **does the router send messages to the right teams?**
Targets from PLAN.md: at least 85% routing accuracy, 100% crisis catch, privacy tests passing.

## Decisions
- **Language: Python** (with a virtual environment in `.venv`).
- **Model:** start with Claude Haiku 5.5 (small, cheap); move up only if the eval falls short.
- **TRIAGE result:** when a message goes to TRIAGE (more than 3 teams, or low confidence), the suggestion is TRIAGE only. Claude's guessed teams stay visible to staff as hints. This matches the test labels.
- **Crisis + TRIAGE:** a crisis always adds HELP, even when the message also goes to TRIAGE.

## How a message flows

```
Form data (name, email, phone, address, comments)
        │
        ├──► crisis.py   plain keyword check, runs on our side, no AI
        │
        ▼
   redact.py      removes emails, phones, addresses, ID numbers,
        │         and anything matching the person's own form fields
        ▼
   payload.py     builds the request: ONLY case ID + redacted text
        │         (the one place the allowed list is enforced)
        ▼
   router.py      sends it to Claude and checks the answer:
        │         segments, team, reason, confidence for each
        ▼
   rules (plain code, after Claude answers):
        • crisis keyword found → add HELP and flag a human
        • more than 3 teams or low confidence → TRIAGE
        ▼
   Result + a log entry of exactly what Claude saw
```

Claude only suggests. The safety rules run in our own code afterward, so they don't depend on the AI.

## Files

| File | What it does |
|---|---|
| `server/redact.py` | Swaps personal details for placeholders like `[EMAIL]`, `[PHONE]`, `[NAME]`, `[ADDRESS]`, `[ID]` |
| `server/crisis.py` | Keyword list for self-harm, abuse, wandering and emergencies. Runs locally, separate from Claude |
| `server/payload.py` | Builds the request to Claude. Only `case_id` and the redacted comments are allowed in |
| `server/router.py` | Loads teams and overlap rules from the CSVs, asks Claude, checks the reply, applies the rules |
| `server/cache/results.json` | Saved Claude answers for the 30 test messages. Used when there's no key or the API is down |
| `tests/test_privacy.py` | Automated tests (below) |
| `tests/eval.py` | Runs all 30 messages and prints a scorecard |
| `requirements.txt` | The add-on packages the project needs |

## Tests
- **Allowlist test:** fails if anything except `case_id` and the comments appears in a request to Claude. Uses a fake stand-in for Claude, so no key and no cost.
- **Redaction test:** for M29 and M30, the strings listed in `pii_in_text` must not appear in what we send.
- **Crisis test:** the keyword check must catch M08, M09 and M10 with no AI.
- **Prompt injection:** M28 must still route to DON. The message is sent inside clearly marked tags with an instruction to treat it as data, never as commands.

## Eval scorecard
`tests/eval.py` prints one line per message (expected vs. got, ✅/❌), then routing accuracy, crisis catch rate, and how many answers came live vs. from the cache. It can run live or from the cache.

## Known limits
- **Overfitting:** tuning the prompt until all 30 pass can mean "teaching to the test." Report scores honestly and flag fixes that only help one message.
- **Names in free text:** the submitter's own name is reliably redacted; other names (e.g. "my sister Jane") are not.

## New dependencies
- `anthropic`: Anthropic's official package for calling Claude from Python.
- `python-dotenv`: reads the API key from `.env` so it never appears in code.
- `pytest`: runs the automated tests and shows pass or fail.

## Build order within step 3
1. Virtual environment and `requirements.txt`.
2. Redaction, crisis check, payload builder, and the privacy tests (no API calls).
3. Router with live Claude calls and call logging.
4. Eval script; first scorecard.
5. Save cached results for the 30 messages.

## Eval results and open questions (2026-11-05)

After adding `staff_flags` and clarifying TRIAGE, 3 live runs scored 28/30, 30/30, 30/30
(88/90 = 98% routing) with 9/9 crisis catches and no false alarms. The cache in
`server/cache/results.json` is from the 28/30 run (kept as a typical run, not the best one).

Left for Aiden to decide:
1. **M28 (prompt injection):** Claude resists the attack and routes to DON, but sometimes also adds
   a TRIAGE segment, which sends the whole case to TRIAGE. Option: a code rule that ignores a
   TRIAGE segment when there is also a confident specialist team. This is a routing-policy change.
2. **M16 (company sponsorship + matching gifts):** Claude sometimes adds DON, citing overlap O04
   ("If both an employee gift and company program appear, route to both"). The message only
   describes a company program. Option: reword O04 in `data/overlaps.csv` so a company matching
   program alone stays CORP.
