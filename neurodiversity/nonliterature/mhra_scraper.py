"""MHRA/PARD device register — direct scraper, no third-party API. Working spec §10.

Decided fully-free (no Tavily, no SERP API): one specific, stable, known government
source, not open-ended search — nothing to discover, only a fixed page to parse.
requests + BeautifulSoup against https://aic.mhra.gov.uk/era/pdr.nsf/. Accepted cost:
if PARD's page structure changes, this breaks until someone updates the parser —
acceptable given it runs on a schedule, not live traffic. Written to external_records
with source='mhra_pard', jurisdiction='UK'.

TODO: implement search_pard(device_or_manufacturer: str) -> list[DeviceRecord].
"""
