"""Eval: run the 30 labeled test messages through the router and score it.

Targets (PLAN.md): routing accuracy >= 85%, crisis catch = 100%.
A message is "correct" when the router's final team set exactly matches the
expected team set (order does not matter).

Usage:
  .venv/bin/python tests/eval.py                 # live calls to Claude
  .venv/bin/python tests/eval.py --save-cache    # live, and save answers as the fallback cache
  .venv/bin/python tests/eval.py --mode cache    # no API key needed

Exit code is 0 only if both targets are met (useful for automated checks later).
"""

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server import router  # noqa: E402

ACCURACY_TARGET = 0.85
CRISIS_TARGET = 1.0

# Claude Haiku 5.5, US$ per million tokens (prompts up to 100K tokens).
PRICE_IN, PRICE_OUT = 0.10, 0.50
PRICE_CACHE_WRITE, PRICE_CACHE_READ = PRICE_IN * 1.25, PRICE_IN * 0.10


def cost(usage):
    return (
        usage.get("input_tokens", 0) * PRICE_IN
        + usage.get("output_tokens", 0) * PRICE_OUT
        + usage.get("cache_creation_input_tokens", 0) * PRICE_CACHE_WRITE
        + usage.get("cache_read_input_tokens", 0) * PRICE_CACHE_READ
    ) / 1_000_000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["live", "cache", "auto"], default="live")
    ap.add_argument("--save-cache", action="store_true",
                    help="save live answers to server/cache/results.json")
    ap.add_argument("--only", nargs="*", help="run only these message IDs, e.g. M01 M28")
    args = ap.parse_args()

    messages = json.loads((ROOT / "tests" / "messages.json").read_text())
    if args.only:
        messages = [m for m in messages if m["id"] in args.only]

    cache = router.load_cache() if args.save_cache else None
    rows, total_cost = [], 0.0
    by_category = defaultdict(lambda: [0, 0])
    sources = defaultdict(int)

    print(f"\nRouter eval: {len(messages)} messages, mode={args.mode}, model={router.MODEL}\n")
    print(f"{'ID':4} {'OK':2}  {'EXPECTED':14} {'GOT':18} {'CRISIS':12} CATEGORY")
    print("-" * 72)

    for m in messages:
        r = router.route(f"CASE-{m['id']}", m["comments"], m["submitter"], mode=args.mode)
        correct = set(r.teams) == set(m["expected_teams"])
        total_cost += cost(r.usage)
        sources[r.source] += 1
        by_category[m["category"]][0] += correct
        by_category[m["category"]][1] += 1

        crisis_note = ""
        if m["expect_crisis"]:
            crisis_note = "caught" if r.needs_human else "MISSED"
        elif r.needs_human:
            crisis_note = "false alarm"

        print(f"{m['id']:4} {'✅' if correct else '❌'}  {','.join(m['expected_teams']):14} "
              f"{','.join(r.teams):18} {crisis_note:12} {m['category']}")

        if args.save_cache and r.source == "live":
            cache[router.cache_key(r.what_claude_saw)] = {
                "message_id": m["id"],
                "labels": {
                    "segments": r.segments,
                    "crisis": r.claude_crisis,
                    "overall_confidence": r.overall_confidence,
                    "handoff_note": r.handoff_note,
                    "staff_flags": r.staff_flags,
                },
            }

        rows.append({"id": m["id"], "category": m["category"], "correct": correct,
                     "expected": m["expected_teams"], "expect_crisis": m["expect_crisis"],
                     **r.to_dict()})

    # --- Scorecard ---------------------------------------------------------
    n = len(rows)
    n_correct = sum(r["correct"] for r in rows)
    crisis_rows = [r for r in rows if r["expect_crisis"]]
    caught = sum(r["needs_human"] for r in crisis_rows)
    by_keyword = sum(bool(r["crisis_keywords"]) for r in crisis_rows)
    by_claude = sum(bool(r["claude_crisis"]) for r in crisis_rows)
    false_alarms = sum(r["needs_human"] for r in rows if not r["expect_crisis"])
    accuracy = n_correct / n if n else 0
    crisis_rate = caught / len(crisis_rows) if crisis_rows else 1.0

    print("-" * 72)
    print(f"\nRouting accuracy: {n_correct}/{n} = {accuracy:.0%}   "
          f"(target {ACCURACY_TARGET:.0%}) {'✅' if accuracy >= ACCURACY_TARGET else '❌'}")
    print(f"Crisis catch:     {caught}/{len(crisis_rows)} = {crisis_rate:.0%}  "
          f"(target 100%) {'✅' if crisis_rate >= CRISIS_TARGET else '❌'}")
    print(f"   caught by keyword check: {by_keyword}/{len(crisis_rows)}   "
          f"by Claude: {by_claude}/{len(crisis_rows)}   false alarms: {false_alarms}")
    print("\nBy category:")
    for cat, (ok, tot) in sorted(by_category.items()):
        print(f"   {cat:18} {ok}/{tot}")
    flagged = [r for r in rows if r["staff_flags"]]
    if flagged:
        print("\nStaff flags (shown to staff, do not change teams):")
        for r in flagged:
            print(f"   {r['id']}: " + " | ".join(r["staff_flags"]))
    print(f"\nAnswers from: {dict(sources)}")
    print(f"Estimated cost: ${total_cost:.4f}")

    misses = [r for r in rows if not r["correct"]]
    if misses:
        print("\nMisses (what Claude said):")
        for r in misses:
            print(f"\n  {r['id']} expected {r['expected']} got {r['teams']}"
                  + (f"  error: {r['error']}" if r["error"] else ""))
            for reason in r["triage_reasons"]:
                print(f"     rule: {reason}")
            for s in r["segments"]:
                print(f"     {s['team']:6} {s['confidence']:.2f}  {s['reason']}")
            for flag in r["staff_flags"]:
                print(f"     flag: {flag}")

    # --- Save --------------------------------------------------------------
    if args.save_cache:
        router.save_cache(cache)
        print(f"\nSaved {len(cache)} cached answers to {router.CACHE_FILE.relative_to(ROOT)}")
    router.LOG_DIR.mkdir(exist_ok=True)
    out = router.LOG_DIR / f"eval-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps({"accuracy": accuracy, "crisis_catch": crisis_rate,
                               "model": router.MODEL, "mode": args.mode, "rows": rows}, indent=2))
    print(f"Full results: {out.relative_to(ROOT)}\n")

    return 0 if accuracy >= ACCURACY_TARGET and crisis_rate >= CRISIS_TARGET else 1


if __name__ == "__main__":
    sys.exit(main())
