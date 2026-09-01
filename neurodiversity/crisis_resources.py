"""Static, hand-maintained crisis resources. Working spec §9.2: "Resources are data, not
generated text. Crisis line numbers are a static, maintained table keyed by locale, never
model output. A hallucinated or outdated crisis number is close to the worst failure this
system could produce."

Jurisdiction: UK, matching §10/§16 item 1's decision for the first build — the spec
explicitly names Samaritans (116 123) as the correct reference for this build. An
internationally-recognised fallback is included per §9.2's guidance for when locale can't
be resolved, since no jurisdiction-detection mechanism exists yet (§16 open decision #1).

Review and refresh this list periodically — the same discipline any static reference
table needs, not a one-time entry.
"""

RESOURCES: list[dict[str, str]] = [
    {
        "name": "Samaritans",
        "description": "Free, confidential support any time, day or night, for anyone struggling to cope — UK and Ireland.",
        "contact": "116 123 (free, 24/7)",
        "url": "https://www.samaritans.org",
    },
    {
        "name": "Shout",
        "description": "Free, confidential 24/7 text support for anyone in crisis, UK-wide.",
        "contact": "Text SHOUT to 85258",
        "url": "https://giveusashout.org",
    },
    {
        "name": "International Association for Suicide Prevention — crisis centre directory",
        "description": "Directory of crisis centres by country, for anyone outside the UK or wanting a local alternative.",
        "contact": "",
        "url": "https://www.iasp.info/resources/Crisis_Centres/",
    },
]
