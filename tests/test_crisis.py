"""Crisis keyword check: must catch every crisis message, with no AI involved.

Run with:  .venv/bin/pytest
"""

import json
from pathlib import Path

import pytest

from server.crisis import is_crisis

MESSAGES = json.loads((Path(__file__).parent / "messages.json").read_text())


@pytest.mark.parametrize("msg", MESSAGES, ids=[m["id"] for m in MESSAGES])
def test_matches_test_set_label(msg):
    assert is_crisis(msg["comments"]) == msg["expect_crisis"]


# Phrasings that are NOT in the test set, so the list is not just tuned to
# three sentences.
@pytest.mark.parametrize(
    "text",
    [
        "I have thought about suicide.",
        "Sometimes I want to die.",
        "I can't go on anymore like this.",
        "Mom wandered off from the care home this morning.",
        "Grandpa is missing since last night.",
        "I couldn't find my husband at the store and he doesn't have his phone.",
        "My brother hits her when he is angry.",
        "I think the aide is neglecting my father.",
        "Dad fell and can't get up.",
        "She is not breathing right, is this an emergency?",
        "I am afraid for my safety at home.",
    ],
)
def test_catches_other_crisis_phrasings(text):
    assert is_crisis(text), text


@pytest.mark.parametrize(
    "text",
    [
        "My donation receipt is missing a date.",
        "I walked out of the meeting early, sorry.",
        "Can I end my monthly gift?",
        "I cannot find the volunteer page.",
        "Help me find a support group please.",
        "I want to hit my fundraising goal this year!",
    ],
)
def test_ordinary_messages_do_not_trigger(text):
    assert not is_crisis(text), text
