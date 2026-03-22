"""Daily notes and automatic index generation for trevo vault.

Generates:
- A daily note (YYYY-MM-DD.md) that aggregates all dictations for that day
- An index.md with links to all notes, grouped by tag
"""
from __future__ import annotations

from datetime import datetime, date
from pathlib import Path
from typing import Optional

from utils.logger import logger
from knowledge.note import Note
from knowledge.graph import KnowledgeGraph


def ensure_daily_note(graph: KnowledgeGraph, target_date: Optional[date] = None) -> Note:
    """Get or create today's daily note."""
    d = target_date or date.today()
    title = d.strftime("%Y-%m-%d")
    slug = title

    existing = graph.get_note(slug)
    if existing:
        return existing

    note = Note(
        title=title,
        content=f"# {d.strftime('%A, %B %d, %Y')}\n\n## Dictations\n\n_No dictations yet._\n",
        tags=["daily"],
        source="system",
    )
    graph.save_note(note)
    logger.debug("Created daily note: {}", title)
    return note


def append_to_daily_note(graph: KnowledgeGraph, note_title: str) -> None:
    """Add a wikilink to today's daily note pointing to the given note."""
    daily = ensure_daily_note(graph)

    link = f"- [[{note_title}]]"
    if link in daily.content:
        return  # already linked

    # Replace the placeholder or append
    if "_No dictations yet._" in daily.content:
        daily.content = daily.content.replace(
            "_No dictations yet._",
            link,
        )
    else:
        daily.content += f"\n{link}"

    graph.save_note(daily)


def generate_index(graph: KnowledgeGraph) -> Path:
    """Generate/update an index.md in the vault root.

    Groups notes by tag and lists them with links.
    """
    notes = graph.all_notes()
    tags = graph.get_tags()
    stats = graph.graph_stats()

    lines = [
        "# trevo Knowledge Vault",
        "",
        f"**{stats['total_notes']}** notes | **{stats['total_links']}** links | **{stats['total_tags']}** tags",
        "",
        "---",
        "",
        "## Recent Notes",
        "",
    ]

    # Last 20 notes
    for note in notes[:20]:
        date_str = note.updated_at.strftime("%Y-%m-%d")
        tags_str = " ".join(f"#{t}" for t in note.tags[:3])
        lines.append(f"- [{date_str}] [[{note.title}]] {tags_str}")

    lines.extend(["", "---", "", "## By Tag", ""])

    for tag, count in tags.items():
        if tag == "daily":
            continue
        lines.append(f"### #{tag} ({count})")
        for note in graph.get_notes_by_tag(tag):
            if "daily" not in note.tags:
                lines.append(f"- [[{note.title}]]")
        lines.append("")

    # Orphan notes (no links in or out)
    orphans = [
        n for n in notes
        if not n.outgoing_links and not graph.get_backlinks(n.title)
        and "daily" not in n.tags
    ]
    if orphans:
        lines.extend(["---", "", "## Orphan Notes (unlinked)", ""])
        for note in orphans:
            lines.append(f"- [[{note.title}]]")

    index_path = graph.vault_path / "index.md"
    index_path.write_text("\n".join(lines), encoding="utf-8")
    logger.debug("Updated vault index at {}", index_path)
    return index_path
