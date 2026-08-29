"""NICE — primary UK guidance source. Working spec §10, §16 item 1.

Structured access where available. Runs at ingestion, scheduled refresh, never at
query time. Written to external_records with source='nice', jurisdiction='UK'.

TODO: implement fetch_guidance(topic: str) -> list[GuidanceRecord].
"""
