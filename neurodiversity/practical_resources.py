"""Static, hand-maintained practical-support resources — same principle as §9.2's crisis
resources: this is data, never model output. A hallucinated organization name, phone
number, or URL here is close to the same failure class as a hallucinated crisis line.

Jurisdiction: UK, matching the working spec's §10/§16 item 1 decision for the first
build. Expanding beyond the UK needs the same explicit jurisdiction handling §10 already
flags as an unsolved problem for guidance data generally — don't silently add other
countries' organizations into this table without that decision being made first.

This is a fixed, small, manually-curated list, not a search result — review and refresh
it periodically the way any static reference table needs upkeep, the same discipline
§9.2 asks for crisis-line numbers.
"""

RESOURCES: dict[str, list[dict[str, str]]] = {
    "workplace": [
        {
            "name": "ACAS (Advisory, Conciliation and Arbitration Service)",
            "description": "Free, impartial advice on workplace rights, disputes, and reasonable adjustments — including harassment and discrimination at work.",
            "url": "https://www.acas.org.uk",
        },
        {
            "name": "Equality Advisory Support Service (EASS)",
            "description": "Advice on discrimination law in England, Scotland, and Wales, including disability discrimination under the Equality Act 2010.",
            "url": "https://www.equalityadvisoryservice.com",
        },
        {
            "name": "National Autistic Society — Employment",
            "description": "Autism-specific guidance on workplace rights, disclosure, and reasonable adjustments.",
            "url": "https://www.autism.org.uk/advice-and-guidance/topics/employment",
        },
    ],
    "education": [
        {
            "name": "IPSEA (Independent Provider of Special Education Advice)",
            "description": "Free legal advice for parents and carers on special educational needs (SEN) and EHC plans in England.",
            "url": "https://www.ipsea.org.uk",
        },
        {
            "name": "National Autistic Society — Education",
            "description": "Guidance on autism in schools, SEN support, and education rights.",
            "url": "https://www.autism.org.uk/advice-and-guidance/topics/education",
        },
    ],
    "benefits": [
        {
            "name": "Citizens Advice",
            "description": "Free, independent guidance on benefits, disability support, and related legal questions.",
            "url": "https://www.citizensadvice.org.uk",
        },
        {
            "name": "Disability Rights UK",
            "description": "Information and advocacy on disability benefits and rights.",
            "url": "https://www.disabilityrightsuk.org",
        },
    ],
    "general": [
        {
            "name": "National Autistic Society",
            "description": "General information, advice, and support for autistic people and their families.",
            "url": "https://www.autism.org.uk",
        },
        {
            "name": "ADHD Foundation",
            "description": "General information and support for people with ADHD.",
            "url": "https://www.adhdfoundation.org.uk",
        },
        {
            "name": "Citizens Advice",
            "description": "Free, independent guidance across legal, financial, and practical issues.",
            "url": "https://www.citizensadvice.org.uk",
        },
    ],
}


def for_topic(topic: str | None) -> list[dict[str, str]]:
    """Always includes 'general' alongside the specific topic (deduplicated by name), so
    a narrow topic match never hides the broader support organizations."""
    specific = RESOURCES.get(topic, []) if topic else []
    general = RESOURCES["general"]
    seen = set()
    combined = []
    for r in specific + general:
        if r["name"] not in seen:
            seen.add(r["name"])
            combined.append(r)
    return combined
