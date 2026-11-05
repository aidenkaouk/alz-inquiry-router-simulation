# Plan: ALZ Inquiry Router demo

Status: planning complete, build not started.

## Source documents
Problem statement, PRD and panel briefing (Claude Corps Basecamp). Key PRD points: the real Contact Us form has no topic field; staff sort messages by hand; the tool suggests, staff approve; crisis messages always go to the Helpline and a human; unclear messages go to TRIAGE; targets are at least 85% routing accuracy and 100% crisis catch. Mock baseline: about 120 inquiries a week, 35% reach the wrong team first, 1.8 handoffs, 3.2 business days to first response.

## What is real and what is invented
- Real/public basis: team names, what each owns, alz.org page mapping, Helpline 800.272.3900, public executive titles (used only to place teams in departments).
- Invented: all people, emails (`@alz-demo.example`), response targets, backups, messages.
- Each team row is marked `public-basis` or `inferred`.

## Teams (15 owners + TRIAGE)
HELP 24/7 Helpline; DON Donor Services; PG Planned Giving; WALK Walk & Events (incl. The Longest Day and event volunteers); VOL Volunteer Engagement; ADV Advocacy & Public Policy; RES Research & Clinical Trials; PRO Professionals & Medical Affairs; CHAP Chapter Operations; MEDIA Communications / Pressroom; WEB Web & Marketing; PRIV Privacy & Legal; CORP Corporate Partnerships; JOBS Careers / HR; DEI Diverse Communities Outreach; TRIAGE Constituent Triage (human fallback).

## Data (CSV)
- `teams.csv`: team_id, team_name, owns, does_not_own, related_alz_pages, target_response_time, escalation_team, basis
- `contacts.csv`: contact_id, team_id, name (fake), role, level (primary/backup/lead-of-team), email (fake), coverage, hours. About four regional CHAP contacts, selected by ZIP.
- `overlaps.csv`: message pattern, competing teams, tie-break rule, escalation (e.g. event volunteer WALK vs VOL; Walk donation WALK vs DON; memorial gift DON vs PG; CORP vs DON; DEI vs CHAP).

## Front end (matches the real Contact Us page)
Real form fields, in order: First Name*, Last Name*, Email Address*, Email Address Type* (default Personal), pre-checked "Yes, I would like to receive email" box, Street Address 1, Street Address 2, Country* (United States), ZIP Code*, City, State, Phone Number (area + number), Phone Number Type (Mobile), Comments* (2,500 characters), Cancel and Submit.
Layout: utility bar (Illinois Chapter, About, News, Events, Professionals, E-News, English); logo; "Call Our 24/7 Helpline 800.272.3900"; search; gold DONATE NOW and GIVE MONTHLY; deep-purple nav (About Alzheimer's & Dementia, Help & Support, Research, Get Involved); narrow centered form; purple footer band with Make a Donation / 24/7 Helpline / Local Resources. Look-alike wordmark, demo banner.

## Cases and multi-team routing
- One submission = one case (e.g. CASE-1042) holding the full form data and original message.
- Claude splits the Comments into segments; each gets a team, one-line reason and confidence.
- Teams on a case are equals. Each sees the full case, the highlighted segments, the other teams and their statuses, and a shared notes thread. Each owns its own segment.
- Status per team: Pending / Replied / No reply needed. Case closes when all teams are resolved. TRIAGE watches and flags overdue pending teams.
- Console user = the Constituent Triage team (decided in step 5). Staff never assign a case to TRIAGE; they pick real teams and Approve. The router's "TRIAGE" answer shows in the console as "UNSORTED" (router could not decide). "Can't sort this: needs follow-up" keeps a case open with an optional note and assigns no team. TRIAGE as a team still watches for overdue teams in step 6.
- Rules: crisis adds HELP and flags a human; more than 3 teams or low confidence goes to TRIAGE; staff approve and can add/remove teams; nothing is sent automatically.

## Privacy design
- Claude receives only redacted Comments plus the case ID. Server re-attaches name/contact details by case ID with ordinary code when building the handoff.
- Layers: field allowlist (with failing test), local redaction, "What Claude saw" panel, audit log, no tools for Claude, key kept on the server in `.env`.
- Limits to state aloud: name redaction in free text is imperfect; redaction can drop useful context; Association privacy/IT must review data terms before any real data.

## Router
Local server calls Claude live (small cheap model first, move up only if the test set requires), returns validated JSON (segments, teams, crisis flag, confidence, handoff note). Cached results for the 30 test messages as a fallback. Pre-made message dropdown plus free typing.

## Screens
1. Public site and Contact Us form.
2. Triage console: queue, suggestion, reasons, confidence, crisis banner, Approve / Reroute / Send to Triage, What Claude saw.
3. Team inbox (separate screen, "view as" a team): that team's cases, shared case page, simulated outbox.

## Test set and eval
30 invented labeled messages: about 8 touch two or more teams; 2-3 crisis; the "walked last year, want to volunteer" case; a prompt-injection attempt; a few vague messages that should go to TRIAGE; some with fake names/phones/emails inside the Comments to test redaction. Correct = team set matches; crisis catch must be 100%; redaction test must pass.

## Build order
1. Repo setup and the three CSVs.
2. 30-message test set.
3. Router and eval script (check accuracy before any UI). API key needed from here.
4. Public form.
5. Triage console.
6. Team inbox and shared case page.
7. Demo script and "what's not real" slide.

## Ideas to practice Claude skills on
Hook blocking `.env`/key text from commits; eval run on every router change; GitHub check that fails if the privacy allowlist test fails; a privacy-review skill or subagent for changes touching what is sent to Claude.

## Open items
- Whether to show an "overdue" timer in triage.
- Anthropic API key (needed at build step 3; billing and a low spend limit first).
- Later: Spanish support.
