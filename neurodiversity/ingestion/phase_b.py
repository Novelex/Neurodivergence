"""Phase B — expensive, lazy, priority-queued worker pool. Working spec §5.8, §12.

Plain Python (asyncio/multiprocessing), no Celery, no Redis — quality_checks.status =
'unchecked' plus the priority flag already is the queue (schema.sql). Claim via
SELECT ... FOR UPDATE SKIP LOCKED on the standard pooled connection, claim + status
update in one transaction (§6.1, corrected — no direct/session-mode connection needed).

Two lanes: background (steady rate) and priority (retrieval just surfaced this paper's
row while unchecked — promotion is a retrieval fact, never a model's judgement call).

TODO: implement run_worker(pool_size: int) -> None — claim loop dispatching to
neurodiversity/agents/design_classifier.py and the appropriate auditor in
neurodiversity/agents/auditors/.
"""
