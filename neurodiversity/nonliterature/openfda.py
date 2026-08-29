"""openFDA — supplementary international context only, not the primary source. Working spec §10.

api.fda.gov, Lucene query (510(k), PMA, recalls, MAUDE). No key required for reasonable
volume. Devices marketed in the UK often also carry US FDA clearance; this fills that in
as additional honest record, not as what jurisdiction correctness rests on (MHRA/PARD is).
Written to external_records with source='openfda', jurisdiction='US'.

TODO: implement fetch_clearance(device_name: str) -> list[FDARecord].
"""
