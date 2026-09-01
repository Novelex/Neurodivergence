"""Community-corroboration axis. Working spec §9.1, §16 item 3.

Reports a second, separate axis alongside formal-evidence strength: whether a construct
that's thin in the peer-reviewed literature is nonetheless well-documented by first-person
accounts from the autistic/ADHD/etc. community itself. The point (§9.1): a system that
only ever says "not well established" for things the community has discussed for years
reads, to that audience, as dismissing community-generated knowledge in favour of a
literature that historically didn't ask them anything. The fix isn't to soften the formal
evidence grade — it's to report both axes honestly, separately.

Sourcing rule (§16 item 3, decided): hand-curated from legitimate public community
material — autistic-led organizations, published essays/books, community conference
talks. Deliberately excluded: scraped forum posts, subreddits, or personal social media,
even where technically public — harvesting someone's unguarded writing without their
expecting it to feed a product violates the same consent principle §7.2 applies to the
person asking the question.

This is a small, static, manually-curated table, not a search result or model output —
same discipline as practical_resources.py and §9.2's crisis-line table. Keep entries to
things that can be stated conservatively and are easy to verify; do not add a construct
here on the strength of a guess about how the community discusses it.

Seed set: autistic burnout and masking are the two constructs the working spec itself
names as the paradigm case (§9, §9.1) — "both constructs originated in the autistic
community and entered the formal literature late, thin, and largely through qualitative
work." Expand this table deliberately and conservatively, not by inference.
"""

ACCOUNTS: dict[str, dict] = {
    "autistic_burnout": {
        "keywords": ["burnout", "burnt out", "burned out", "shutdown", "shut down"],
        "summary": (
            "Autistic burnout — persistent exhaustion, skill loss, and reduced tolerance "
            "to stimulation after sustained masking or overload — is a concept that "
            "originated within the autistic community, not formal clinical literature, "
            "and has been discussed there for years ahead of (and beyond) what formal "
            "research has covered so far."
        ),
        "sources": [
            {"name": "Autistic Self Advocacy Network (ASAN)", "url": "https://autisticadvocacy.org"},
        ],
    },
    "masking": {
        "keywords": ["masking", "camouflaging", "camouflage"],
        "summary": (
            "Masking (or camouflaging) — suppressing or hiding autistic traits to fit in "
            "socially — is a term that entered the formal literature relatively recently "
            "and thinly, after extensive prior first-person discussion within the "
            "autistic community about what it costs."
        ),
        "sources": [
            {"name": "Autistic Self Advocacy Network (ASAN)", "url": "https://autisticadvocacy.org"},
        ],
    },
}


def for_query(research_query: str) -> dict | None:
    """Simple keyword match against the research_query text — plain code, no model call.
    Returns None if nothing matches; never guesses at a construct it doesn't have an
    entry for."""
    query_lower = research_query.lower()
    for entry in ACCOUNTS.values():
        if any(keyword in query_lower for keyword in entry["keywords"]):
            return {"summary": entry["summary"], "sources": entry["sources"]}
    return None
