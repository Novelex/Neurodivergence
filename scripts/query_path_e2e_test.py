"""Query path — prove one real question gets answered end to end.

No new corpus expansion — runs against the ~25 papers already ingested by
scripts/phase1_e2e_test.py. Requires supabase/query_functions.sql to have been run
first (match_chunks, rank_papers).

Usage: uv run python scripts/query_path_e2e_test.py "your question here"
"""

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from neurodiversity.query.pipeline import handle_turn

DEFAULT_QUESTION = (
    "What does research say about correcting for multiple comparisons in "
    "brain imaging studies of autism and Tourette syndrome?"
)


def main() -> None:
    question = " ".join(sys.argv[1:]) or DEFAULT_QUESTION
    print(f"Question: {question!r}\n")

    result = handle_turn(question)

    print(f"\n=== terminal_state: {result.terminal_state} ===")
    if result.reflection:
        print(f"Reflection: {result.reflection}")
    if result.prose:
        print(f"\nAnswer:\n{result.prose}")
    if result.citations:
        print(f"\nCitations ({len(result.citations)}):")
        for c in result.citations:
            print(f"  [{c.paper_id}] {c.quote[:120]!r}")


if __name__ == "__main__":
    main()
