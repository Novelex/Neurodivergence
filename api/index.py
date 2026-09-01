"""Vercel serverless entrypoint. Vercel's Python runtime auto-detects an ASGI `app`
variable in any file under /api and serves it as a function — this file exists only to
re-export the real app (neurodiversity/api/main.py) at the path Vercel expects.

Real risks worth knowing about this deployment target, not glossed over:
- The /sessions/{id}/turns/stream SSE endpoint (query/pipeline.py's progress streaming)
  is unlikely to work reliably here — Vercel's Python serverless runtime doesn't have the
  mature chunked-streaming support its Node/Edge runtimes do. The frontend
  (static/index.html) falls back to the plain, non-streaming /turns endpoint if the
  stream fails, so the app still works — it just loses the live progress-line UI on this
  deployment specifically.
- Turns can take 25-90+ seconds (real GPT-4o calls, sometimes a live PubMed search).
  Check this project's configured function `maxDuration` in vercel.json against your
  actual Vercel plan's limits before relying on this in production — a turn that
  triggers live_search is the most likely one to run long.
- Every request is a stateless, cold-start-prone invocation — there is no persistent
  server process the way `uv run uvicorn ...` gives you locally. Nothing in this app
  currently depends on in-process state surviving between requests (Supabase is accessed
  purely over its REST API), so this should be safe, but it's a real difference worth
  knowing about if that ever changes.
"""

from neurodiversity.api.main import app

__all__ = ["app"]
