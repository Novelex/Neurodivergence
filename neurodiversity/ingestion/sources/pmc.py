"""PMC full-text fetch + license. Working spec §5.1.

PMC's "open access" label is not one license. The OA subset mixes CC-BY, CC-BY-NC, and
CC-BY-NC-ND papers, and a commercial build cannot legally ingest and serve CC-BY-NC or
CC-BY-NC-ND full text without a separate license. License is checked here, before
has_fulltext is trusted, not as a downstream cleanup step (§5.1).
"""

from dataclasses import dataclass
from xml.etree import ElementTree

import httpx

from neurodiversity.config import settings
from neurodiversity.db.models import PaperLicense

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

_LICENSE_URL_MAP = {
    "by-nc-nd": PaperLicense.cc_by_nc_nd,
    "by-nc": PaperLicense.cc_by_nc,
    "by": PaperLicense.cc_by,
}


@dataclass
class FullTextResult:
    text: str
    license: PaperLicense
    methods_text: str = ""


def _license_from_xml(root: ElementTree.Element) -> PaperLicense:
    """Search the permissions block's full text/attributes for a creativecommons.org URL.

    PMC's JATS structure carries the license URL in different places across articles —
    the <license> element's xlink:href attribute, an <ali:license_ref> element's text
    content, or spelled out in a <license-p> paragraph — and namespace prefixes vary
    enough between records that matching exact element paths is unreliable (this is
    exactly what produced 'unknown' for every paper in the first Phase 1 run). Searching
    the serialized permissions block for the URL substring sidesteps all of that: the
    actual creativecommons.org URL text shows up somewhere in the block regardless of
    which element or attribute is carrying it.
    """
    permissions = root.find(".//permissions")
    if permissions is None:
        return PaperLicense.unknown

    # Collect every attribute value and every text node under <permissions>, plus the
    # raw serialized XML as a final fallback, into one lowercase haystack.
    haystack_parts = ["".join(permissions.itertext())]
    for el in permissions.iter():
        haystack_parts.extend(el.attrib.values())
    haystack_parts.append(ElementTree.tostring(permissions, encoding="unicode"))
    haystack = " ".join(haystack_parts).lower()

    if "creativecommons.org" not in haystack:
        return PaperLicense.unknown

    # Check most-restrictive slugs first so "by-nc-nd" doesn't get matched as "by".
    for slug, license_enum in _LICENSE_URL_MAP.items():
        if f"/{slug}/" in haystack or f"/{slug}" in haystack:
            return license_enum
    return PaperLicense.unknown


def _section_text(sec: ElementTree.Element) -> str:
    paragraphs = ["".join(p.itertext()) for p in sec.iter() if p.tag == "p"]
    return "\n\n".join(paragraphs).strip()


def _extract_methods(body: ElementTree.Element) -> str:
    """Find the Methods section specifically, not just the start of the paper.

    The classifier and auditors need actual study-design details (recruitment, protocol,
    statistical analysis) to work from — the first N characters of a paper's full text is
    almost always the introduction/background, which reads like a literature review even
    for genuinely empirical papers. This is what was silently starving the design
    classifier of the information it needed (docs/gold-answer.md-style finding from the
    Phase 1 scale-up: a naive text[:3000] slice produced a 92% other_unclassified rate on
    papers that clearly had real methods sections). JATS marks sections with a sec-type
    attribute ("methods", "materials|methods", etc.) most of the time; fall back to
    matching the <title> text when sec-type is missing or non-standard, since not every
    journal's XML conversion is consistent about the attribute.
    """
    matches = []
    for sec in body.iter("sec"):
        sec_type = (sec.get("sec-type") or "").lower()
        title_el = sec.find("title")
        title_text = (title_el.text or "").lower() if title_el is not None else ""
        if "method" in sec_type or "material" in sec_type or "method" in title_text:
            matches.append(_section_text(sec))
    return "\n\n".join(m for m in matches if m).strip()


def fetch_fulltext(pmc_id: str) -> FullTextResult | None:
    """pmc_id like 'PMC1234567'. Returns None if not available (not OA, or fetch failed)."""
    params = {"db": "pmc", "id": pmc_id, "rettype": "full", "retmode": "xml"}
    if settings.ncbi_api_key:
        params["api_key"] = settings.ncbi_api_key

    resp = httpx.get(f"{EUTILS_BASE}/efetch.fcgi", params=params, timeout=60.0)
    if resp.status_code != 200 or not resp.text.strip():
        return None

    try:
        root = ElementTree.fromstring(resp.text)
    except ElementTree.ParseError:
        return None

    body = root.find(".//body")
    if body is None:
        return None

    paragraphs = [
        "".join(p.itertext()) for p in body.iter() if p.tag == "p"
    ]
    text = "\n\n".join(paragraphs).strip()
    if not text:
        return None

    methods_text = _extract_methods(body)

    return FullTextResult(text=text, license=_license_from_xml(root), methods_text=methods_text)
