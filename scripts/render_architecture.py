"""Render the current IncidentIQ architecture as a presentation-ready PNG."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "architecture.png"

COLORS = {
    "blue": "#DBEAFE",
    "indigo": "#E0E7FF",
    "amber": "#FEF3C7",
    "green": "#DCFCE7",
    "violet": "#EDE9FE",
    "rose": "#FCE7F3",
    "slate": "#F1F5F9",
}


def add_card(ax, x, y, w, h, title, detail, color, title_size=11.2):
    card = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.018,rounding_size=0.025",
        facecolor=color,
        edgecolor="#475569",
        linewidth=1.35,
        zorder=2,
    )
    ax.add_patch(card)
    ax.text(x + w / 2, y + h * 0.66, title, ha="center", va="center",
            fontsize=title_size, fontweight="bold", color="#172554", zorder=3)
    ax.text(x + w / 2, y + h * 0.34, detail, ha="center", va="center",
            fontsize=7.8, color="#334155", linespacing=1.25, zorder=3)


def arrow(ax, start, end, label=None, curve=0.0, color="#475569"):
    patch = FancyArrowPatch(
        start, end, arrowstyle="-|>", mutation_scale=12,
        linewidth=1.45, color=color,
        connectionstyle=f"arc3,rad={curve}", zorder=3,
    )
    ax.add_patch(patch)
    if label:
        mx, my = (start[0] + end[0]) / 2, (start[1] + end[1]) / 2
        ax.text(mx, my + 0.035, label, ha="center", va="bottom", fontsize=7.2,
                color="#475569", bbox={"facecolor": "#F8FAFC", "edgecolor": "none", "pad": 1.2}, zorder=4)


def main():
    fig, ax = plt.subplots(figsize=(16, 10), facecolor="#F8FAFC")
    ax.set_facecolor("#F8FAFC")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    ax.text(0.5, 0.965, "IncidentIQ | System Architecture", ha="center", va="center",
            fontsize=23, fontweight="bold", color="#0F172A")
    ax.text(0.5, 0.928, "Role-based incident support, hybrid retrieval, and local-first resolution assistance",
            ha="center", va="center", fontsize=10.5, color="#475569")

    # User experience and application services.
    y, h = 0.78, 0.105
    cards = [
        (0.035, 0.20, "Support roles", "L1  ·  L2  ·  L3  ·  Admin", COLORS["blue"]),
        (0.285, 0.22, "React + Vite frontend", "Role-based pages, search,\nqueues, profiles", COLORS["blue"]),
        (0.56, 0.205, "FastAPI REST backend", "Authentication, access checks,\nworkflow APIs", COLORS["indigo"]),
        (0.815, 0.15, "SQLite", "Users, tickets, events,\nfeedback, settings", COLORS["rose"]),
    ]
    for x, w, title, detail, color in cards:
        add_card(ax, x, y, w, h, title, detail, color)
    arrow(ax, (0.235, y + h / 2), (0.278, y + h / 2))
    arrow(ax, (0.505, y + h / 2), (0.553, y + h / 2))
    arrow(ax, (0.77, y + h / 2), (0.808, y + h / 2))

    # Incident preparation and retrieval index.
    y, h = 0.605, 0.105
    cards = [
        (0.035, 0.20, "Incident data", "Raw / processed CSV\n+ admin-added incidents", COLORS["amber"]),
        (0.285, 0.22, "Preprocessing", "Normalize, clean, deduplicate,\ncompose searchable text", COLORS["amber"]),
        (0.56, 0.205, "Local searchable index", "Word/char TF-IDF +\ncorpus-local SVD vectors", COLORS["amber"]),
        (0.815, 0.15, "Hybrid ranking", "Keywords, metadata filters,\nweighted reranking", COLORS["amber"]),
    ]
    for x, w, title, detail, color in cards:
        add_card(ax, x, y, w, h, title, detail, color, title_size=10.5)
    arrow(ax, (0.235, y + h / 2), (0.278, y + h / 2))
    arrow(ax, (0.505, y + h / 2), (0.553, y + h / 2))
    arrow(ax, (0.77, y + h / 2), (0.808, y + h / 2))
    arrow(ax, (0.66, 0.78), (0.66, 0.718))

    # Resolution pipeline.
    y, h = 0.425, 0.105
    cards = [
        (0.035, 0.20, "Incoming query", "Symptoms, impact, optional\nmetadata filters", COLORS["green"]),
        (0.285, 0.22, "Guardrails + triage", "Redact / block unsafe input;\nclassify, prioritize, route", COLORS["green"]),
        (0.56, 0.205, "RCA + resolution", "Historical evidence, likely causes,\ntroubleshooting guidance", COLORS["green"]),
        (0.815, 0.15, "Safety review", "Destructive-command scan\nand grounding signal", COLORS["green"]),
    ]
    for x, w, title, detail, color in cards:
        add_card(ax, x, y, w, h, title, detail, color, title_size=10.5)
    arrow(ax, (0.235, y + h / 2), (0.278, y + h / 2))
    arrow(ax, (0.505, y + h / 2), (0.553, y + h / 2))
    arrow(ax, (0.77, y + h / 2), (0.808, y + h / 2))
    arrow(ax, (0.89, 0.605), (0.89, 0.538))

    # Provider selection is a single resolution step with a local fallback.
    add_card(ax, 0.20, 0.255, 0.60, 0.105, "Resolution model and fallback",
             "Optional: OpenRouter / Gemini / OpenAI\nDisabled, missing, or unavailable: local deterministic guidance", COLORS["violet"])
    arrow(ax, (0.66, 0.425), (0.66, 0.365))

    tier_y, tier_h = 0.105, 0.09
    tier_cards = [
        (0.105, 0.19, "L1 support", "Work and resolve"),
        (0.405, 0.19, "L2 handoff", "Assigned escalation + notes"),
        (0.705, 0.19, "L3 support", "Final tier; AI guidance available"),
    ]
    for x, w, title, detail in tier_cards:
        add_card(ax, x, tier_y, w, tier_h, title, detail, COLORS["violet"], title_size=10.5)
    arrow(ax, (0.30, tier_y + tier_h / 2), (0.398, tier_y + tier_h / 2), "escalate")
    arrow(ax, (0.60, tier_y + tier_h / 2), (0.698, tier_y + tier_h / 2), "escalate")

    # Operational quality and feedback loop.
    ax.text(0.04, 0.055,
            "Operations: ticket history and handoffs  ·  user/admin feedback  ·  notifications  ·  audit logs  ·  retrieval evaluation",
            ha="left", va="center", fontsize=8.6, color="#334155")
    ax.text(0.5, 0.022,
            "Local retrieval and fallback work without an external API key; provider calls are optional.",
            ha="center", va="center", fontsize=8.3, color="#64748B")

    fig.savefig(OUTPUT, dpi=180, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"Created {OUTPUT}")


if __name__ == "__main__":
    main()
