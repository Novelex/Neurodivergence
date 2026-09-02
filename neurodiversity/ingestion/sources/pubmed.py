"""PubMed E-utilities — esearch + efetch. Working spec §5.1, §5.1.1.

The five-clause, per-condition-capped query is decided in §5.1.1 (~500 papers/condition,
~2,500 total) — run each bracketed clause as its own esearch, not one combined query, to
avoid autism/ADHD crowding out dyspraxia/Tourette's (§16 item 2). Uses NCBI_API_KEY
(docs/setup.md) for the 10 req/sec rate limit instead of 3.
"""

from xml.etree import ElementTree

from neurodiversity.config import settings
from neurodiversity.db.models import Paper
from neurodiversity.ingestion.sources._shared_http import get_eutils_client

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# working spec §5.1.1 — five bracketed clauses, plus the shared filters
CONDITION_CLAUSES = {
    "autism": '("Autism Spectrum Disorder"[MeSH] OR "Autistic Disorder"[MeSH] OR "Asperger Syndrome"[MeSH] OR autism[tiab] OR autistic[tiab] OR asperger*[tiab])',
    "adhd": '("Attention Deficit Disorder with Hyperactivity"[MeSH] OR ADHD[tiab] OR "attention deficit"[tiab])',
    "dyslexia": '("Dyslexia"[MeSH] OR dyslexia[tiab] OR dyslexic[tiab])',
    "dyspraxia": '("Motor Skills Disorders"[MeSH] OR dyspraxia[tiab] OR "developmental coordination disorder"[tiab] OR "clumsy child"[tiab])',
    "tourettes": '("Tourette Syndrome"[MeSH] OR tourette*[tiab] OR "tic disorder"[tiab])',
}

# Extended after the Phase 1 scale-up: 52% of a real 25-paper sample landed in
# other_unclassified, and inspection showed corrections/errata and narrative-review/
# perspective pieces slipping through — the classifier was correctly refusing to force
# them into one of the five empirical designs, but they shouldn't have reached it at all.
# "published erratum"[pt] closes the corrections gap. The review clause is deliberately
# not a blanket "NOT review[pt]": PubMed often double-tags a systematic review or
# meta-analysis with the broader "review"[pt] too, and those are exactly what the ranking
# SQL favors (has_meta desc, §7.3) — excluding review[pt] outright would have cut the
# highest-value evidence tier. (NOT review[pt] OR "systematic review"[pt] OR
# meta-analysis[pt]) reads as "keep it unless it's a review, except when that review is
# specifically a systematic review or meta-analysis."
SHARED_FILTERS = (
    'AND hasabstract[text] AND english[lang] '
    'NOT ("case reports"[pt] OR comment[pt] OR letter[pt] OR editorial[pt] OR "published erratum"[pt]) '
    'AND (NOT review[pt] OR "systematic review"[pt] OR meta-analysis[pt])'
)


def _params() -> dict:
    p = {"retmode": "xml"}
    if settings.ncbi_api_key:
        p["api_key"] = settings.ncbi_api_key
    return p


def esearch(condition: str, retmax: int = 500) -> list[str]:
    """Run one condition's clause + shared filters. Returns PMIDs."""
    clause = CONDITION_CLAUSES[condition]
    term = f"{clause} {SHARED_FILTERS}"
    return _esearch_term(term, retmax)


def esearch_free_text(query: str, retmax: int = 8) -> list[str]:
    """Live, per-question search — not one of the five fixed condition clauses.

    Used for the query-time live-search path (query/live_search.py), decided because a
    pre-built corpus isn't affordable at the current budget: search PubMed directly with
    the translator's research_query text, still through the same quality filters
    (SHARED_FILTERS) so a live-fetched paper isn't held to a lower bar than the
    pre-ingested ones. Small retmax by design — this runs synchronously inside a live
    turn, so it costs real latency and real audit-call budget per new paper found.
    """
    term = f"({query}) {SHARED_FILTERS}"
    return _esearch_term(term, retmax)


def _esearch_term(term: str, retmax: int) -> list[str]:
    resp = get_eutils_client().get(
        f"{EUTILS_BASE}/esearch.fcgi",
        params={**_params(), "db": "pubmed", "term": term, "retmax": retmax},
        timeout=30.0,
    )
    resp.raise_for_status()
    root = ElementTree.fromstring(resp.text)
    return [el.text for el in root.findall(".//Id") if el.text]


def _text(article: ElementTree.Element, path: str) -> str | None:
    el = article.find(path)
    return el.text if el is not None else None


def efetch(pmids: list[str]) -> list[Paper]:
    """Fetch bibliographic metadata for a batch of PMIDs."""
    if not pmids:
        return []
    resp = get_eutils_client().get(
        f"{EUTILS_BASE}/efetch.fcgi",
        params={**_params(), "db": "pubmed", "id": ",".join(pmids), "rettype": "abstract"},
        timeout=60.0,
    )
    resp.raise_for_status()
    root = ElementTree.fromstring(resp.text)

    papers = []
    for article in root.findall(".//PubmedArticle"):
        pmid = _text(article, ".//PMID")
        title = _text(article, ".//ArticleTitle") or ""
        abstract_parts = [
            (el.text or "") for el in article.findall(".//Abstract/AbstractText")
        ]
        abstract = " ".join(abstract_parts) if abstract_parts else None
        journal = _text(article, ".//Journal/Title")
        year_text = _text(article, ".//Journal/JournalIssue/PubDate/Year")
        doi = None
        for id_el in article.findall(".//ArticleIdList/ArticleId"):
            if id_el.get("IdType") == "doi":
                doi = id_el.text
        pmc_id = None
        for id_el in article.findall(".//ArticleIdList/ArticleId"):
            if id_el.get("IdType") == "pmc":
                pmc_id = id_el.text

        papers.append(
            Paper(
                pubmed_id=pmid,
                pmc_id=pmc_id,
                doi=doi,
                title=title,
                abstract=abstract,
                journal=journal,
                publication_year=int(year_text) if year_text and year_text.isdigit() else None,
            )
        )
    return papers
