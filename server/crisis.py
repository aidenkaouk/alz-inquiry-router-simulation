"""Plain keyword check for crisis or safety language. No AI involved.

This runs on our own server, separately from Claude, so the rule "crisis always
adds the Helpline and flags a human" does not depend on the AI getting it right.

It is deliberately cautious: a false alarm costs a Helpline staff member a
minute; a missed crisis could cost far more. When adding phrases, also run the
tests to make sure ordinary messages (e.g. "my receipt is missing") do not trip it.
"""

import re
from typing import List

# Words for a person, so "hit my mom" counts but "hit my goal" does not.
PERSON = (
    r"(?:him|her|them|he|she|they|"
    r"(?:my\s+|our\s+)?(?:mother|father|mom|dad|husband|wife|partner|spouse|"
    r"grandmother|grandfather|grandma|grandpa|son|daughter|brother|sister|"
    r"aunt|uncle|parents?|patient|loved\s+one|friend|neighbou?r))"
)

# Each entry: (category, pattern). Patterns are case-insensitive.
CRISIS_PATTERNS = [
    # Self-harm / suicide
    ("self-harm", r"\bsuicid\w*"),
    ("self-harm", r"\bkill(?:ing)?\s+myself\b"),
    ("self-harm", r"\bend(?:ing)?\s+(?:my\s+(?:own\s+)?life|it\s+all)\b"),
    ("self-harm", r"\b(?:want|wanting)\s+to\s+die\b"),
    ("self-harm", r"\bno\s+(?:reason|point)\s+(?:to|in)\s+(?:live|living|going\s+on)\b"),
    ("self-harm", r"\b(?:hurt|harm)(?:ing)?\s+myself\b"),
    ("self-harm", r"\b(?:can ?not|can't|cannot)\s+(?:do\s+this|go\s+on|take\s+(?:it|this))\s+any\s?more\b"),
    # Harm to others / abuse
    ("harm-to-others", r"\b(?:hurt|harm|hit|kill|strangle|smother)\s+" + PERSON + r"\b"),
    ("abuse", r"\babus(?:e|ed|ing|ive)\b"),
    ("abuse", r"\bneglect(?:ed|ing)?\b"),
    ("abuse", r"\b(?:hits|hitting|beats|beating|threaten(?:s|ing|ed)?)\s+(?:me|him|her)\b"),
    ("abuse", r"\bafraid\s+(?:of|for)\s+(?:him|her|my\s+safety|my\s+life)\b"),
    # Wandering / missing person
    ("wandering", r"\bwander(?:ed|ing|s)?\s+(?:off|away)\b"),
    ("wandering", r"\b(?:walked|ran|left|got)\s+out\s+of\s+the\s+(?:house|home|building)\b"),
    ("wandering", r"\b(?:can ?not|can't|cannot|couldn't)\s+find\s+" + PERSON + r"\b"),
    ("wandering", r"\b" + PERSON + r"\s+(?:is|went|has\s+gone|has\s+been)\s+missing\b"),
    # Medical / general emergency
    ("emergency", r"\bemergency\b"),
    ("emergency", r"\b911\b"),
    ("emergency", r"\bnot\s+breathing\b"),
    ("emergency", r"\b(?:fell|has\s+fallen)\s+and\s+(?:can ?not|can't|cannot|won't)\b"),
    ("emergency", r"\bunsafe\b|\bin\s+danger\b"),
]

_COMPILED = [(cat, re.compile(p, re.IGNORECASE)) for cat, p in CRISIS_PATTERNS]


def crisis_categories(text: str) -> List[str]:
    """Return the crisis categories found in the text (empty list if none)."""
    found = []
    for cat, pattern in _COMPILED:
        if pattern.search(text) and cat not in found:
            found.append(cat)
    return found


def is_crisis(text: str) -> bool:
    return bool(crisis_categories(text))
