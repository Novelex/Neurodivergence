"""One-off diagram generator — not part of the application, just this PNG request.
Run with: uv run --with matplotlib python scripts/generate_pipeline_diagram.py
"""

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from matplotlib.lines import Line2D

fig, ax = plt.subplots(figsize=(11, 15))
ax.set_xlim(0, 10)
ax.set_ylim(0, 32)
ax.axis("off")

BLUE = "#3b6fa0"
GREEN = "#3f8f5f"
ORANGE = "#c07a2c"
RED = "#b0433f"
GREY = "#666666"


def box(x, y, w, h, text, color=BLUE, fontsize=9.5, textcolor="white"):
    b = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.08,rounding_size=0.12",
        linewidth=1.2, edgecolor=color, facecolor=color, alpha=0.92,
    )
    ax.add_patch(b)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
             fontsize=fontsize, color=textcolor, wrap=True, weight="medium")
    return (x + w / 2, y, x + w / 2, y + h)


def arrow(x1, y1, x2, y2, color=GREY, style="-", label=None, lw=1.4):
    a = FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=14,
                         color=color, linewidth=lw, linestyle=style, shrinkA=2, shrinkB=2)
    ax.add_patch(a)
    if label:
        ax.text((x1 + x2) / 2 + 0.15, (y1 + y2) / 2, label, fontsize=8, color=color, style="italic")


# Title
ax.text(5, 31.3, "NeuroEvidence — query path", ha="center", fontsize=15, weight="bold")
ax.text(5, 30.7, "temp=0 unless noted · GPT-4o throughout", ha="center", fontsize=9, color=GREY, style="italic")

y = 29.3
_, y0, _, y1 = box(3, y, 4, 1.0, "raw_input arrives", color=GREY)

y -= 1.6
cx, cy0, cx2, cy1 = box(2.8, y, 4.4, 1.0, "5. Scope guard (temp 0)\nanswerable / diagnostic_ask / distress / out_of_domain")
arrow(5, y1, 5, y + 1.0)

# branches out
y_branch = y - 0.2
arrow(2.8, y + 0.5, 0.9, y - 0.9, color=RED)
ax.text(0.9, y - 1.15, "REFUSED", ha="center", fontsize=8.5, weight="bold", color=RED)
arrow(4.2, y + 0.0, 3.0, y - 0.9, color=RED)
ax.text(3.0, y - 1.15, "OUT OF SCOPE", ha="center", fontsize=8, weight="bold", color=RED)
arrow(6.6, y + 0.0, 7.1, y - 0.9, color=RED)
ax.text(7.1, y - 1.15, "DISTRESS\n(§9.2)", ha="center", fontsize=8, weight="bold", color=RED)

y -= 2.4
_, y0, _, y1 = box(2.8, y, 4.4, 1.0, "6. Translator (temp 0)\nprivacy boundary — raw_input stops here")
arrow(5, y + 3.2, 5, y1)

y -= 1.6
_, y0, _, y1 = box(2.5, y, 5.0, 1.0, "Retrieve\nvector search over existing corpus (cheap)")
arrow(5, y + 1.6, 5, y1)

y -= 1.8
_, y0, _, y1 = box(1.5, y, 7.0, 1.3, "Live search (only if coverage is thin, <3 candidates)\nPubMed → ingest_cheap (fetch+chunk+embed, NO GPT-4o call)", color=ORANGE)
arrow(5, y + 1.6, 5, y + 1.3)

y -= 1.6
_, y0, _, y1 = box(2.8, y, 4.4, 1.0, "Reranker (temp 0)\nrelevance ordering only — never quality")
arrow(5, y + 1.6, 5, y1)

y -= 1.6
_, y0, _, y1 = box(2.8, y, 4.4, 1.0, "Deterministic SQL rank\nno model call — site_count, fields_absent_ratio, n_total")
arrow(5, y + 1.6, 5, y1)

y -= 1.8
_, y0, _, y1 = box(1.5, y, 7.0, 1.3, "Audit survivors only (Phase B, deferred)\nclassify + one audit field — spent only on papers that made it this far", color=ORANGE)
arrow(5, y + 1.6, 5, y + 1.3)

y -= 1.6
_, y0, _, y1 = box(2.8, y, 4.4, 1.0, "8. Writer (temp 0)\nprose + citations, from supplied chunks only")
arrow(5, y + 1.6, 5, y1)

y -= 2.0
_, y0, _, y1 = box(1.3, y, 7.4, 1.4, "9. Citation checker\n9a mechanical (code): chunk_id + quote must match exactly\n9b semantic (temp 0): does the sentence fairly represent the quote?", color=GREEN)
arrow(5, y + 2.0, 5, y1)

# retry loop
arrow(1.3, y + 0.7, 0.3, y + 0.7, color=GREY)
ax.add_patch(FancyArrowPatch((0.3, y + 0.7), (0.3, y + 1.6 + 1.6 + 0.5), arrowstyle="-|>",
                              mutation_scale=12, color=GREY, linewidth=1.1,
                              connectionstyle="arc3,rad=0.0"))
ax.text(0.15, y + 2.5, "1 retry\ncapped", ha="center", fontsize=7.5, color=GREY, rotation=90)

y -= 2.0
box(0.7, y, 3.9, 1.0, "ANSWERED\nprose + citations\n+ evidence count", color=GREEN)
box(5.4, y, 3.9, 1.0, "NO_EVIDENCE\nif flags survive the retry", color=RED)
arrow(3.3, y + 2.0, 2.6, y + 1.0, color=GREEN)
arrow(6.5, y + 2.0, 7.3, y + 1.0, color=RED)

# legend
ax.text(0.3, 1.2, "Legend:", fontsize=9, weight="bold")
ax.add_patch(FancyBboxPatch((0.3, 0.6), 0.5, 0.35, boxstyle="round,pad=0.05", facecolor=BLUE, edgecolor=BLUE))
ax.text(1.0, 0.77, "agent (GPT-4o)", fontsize=8, va="center")
ax.add_patch(FancyBboxPatch((3.0, 0.6), 0.5, 0.35, boxstyle="round,pad=0.05", facecolor=ORANGE, edgecolor=ORANGE))
ax.text(3.7, 0.77, "cost-sensitive step (live search / deferred audit)", fontsize=8, va="center")
ax.add_patch(FancyBboxPatch((0.3, 0.05), 0.5, 0.35, boxstyle="round,pad=0.05", facecolor=GREEN, edgecolor=GREEN))
ax.text(1.0, 0.22, "verification (mechanical + model)", fontsize=8, va="center")

plt.tight_layout()
plt.savefig("docs/pipeline_diagram.png", dpi=180, bbox_inches="tight", facecolor="white")
print("Saved to docs/pipeline_diagram.png")
