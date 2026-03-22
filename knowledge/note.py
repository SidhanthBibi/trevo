"""Note model for trevo's Obsidian-style knowledge graph.

Each note is a real .md file on disk with YAML frontmatter.
Notes link to each other via [[wikilinks]].
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_TAG_RE = re.compile(r"(?:^|\s)#([a-zA-Z0-9_/-]+)")


@dataclass
class Note:
    """A single knowledge note, backed by a .md file."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str = ""
    content: str = ""
    tags: list[str] = field(default_factory=list)
    source: str = ""  # "dictation", "agent", "manual", "chat"
    app_context: str = ""  # app that was active when note was created
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # Derived — populated by parse or by the graph manager
    outgoing_links: list[str] = field(default_factory=list)  # titles of linked notes

    @property
    def slug(self) -> str:
        """Filesystem-safe slug from the title."""
        safe = re.sub(r"[^\w\s-]", "", self.title.lower())
        safe = re.sub(r"[\s]+", "-", safe).strip("-")
        return safe or self.id

    @property
    def filename(self) -> str:
        return f"{self.slug}.md"

    # ------------------------------------------------------------------
    # Serialisation: Note ↔ Markdown with YAML frontmatter
    # ------------------------------------------------------------------

    def to_markdown(self) -> str:
        """Render the note as a Markdown string with YAML frontmatter."""
        tags_str = ", ".join(f'"{t}"' for t in self.tags)
        lines = [
            "---",
            f"id: {self.id}",
            f"title: \"{self.title}\"",
            f"tags: [{tags_str}]",
            f"source: {self.source}",
            f"app_context: {self.app_context}",
            f"created_at: {self.created_at.isoformat()}",
            f"updated_at: {self.updated_at.isoformat()}",
            "---",
            "",
            self.content,
        ]
        return "\n".join(lines)

    @classmethod
    def from_markdown(cls, text: str, filepath: Optional[Path] = None) -> Note:
        """Parse a Markdown file with YAML frontmatter into a Note."""
        meta: dict[str, str] = {}
        content = text

        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                frontmatter = parts[1].strip()
                content = parts[2].strip()
                for line in frontmatter.splitlines():
                    if ":" in line:
                        key, _, val = line.partition(":")
                        meta[key.strip()] = val.strip().strip('"')

        # Parse tags from frontmatter
        tags_raw = meta.get("tags", "")
        tags = [t.strip().strip('"') for t in tags_raw.strip("[]").split(",") if t.strip()]

        # Also extract inline #tags from content
        inline_tags = _TAG_RE.findall(content)
        all_tags = list(dict.fromkeys(tags + inline_tags))  # dedupe, preserve order

        # Parse links
        links = _WIKILINK_RE.findall(content)

        # Parse dates
        created = _parse_dt(meta.get("created_at", ""))
        updated = _parse_dt(meta.get("updated_at", ""))

        return cls(
            id=meta.get("id", uuid.uuid4().hex[:12]),
            title=meta.get("title", filepath.stem if filepath else "Untitled"),
            content=content,
            tags=all_tags,
            source=meta.get("source", "manual"),
            app_context=meta.get("app_context", ""),
            created_at=created or datetime.now(),
            updated_at=updated or datetime.now(),
            outgoing_links=links,
        )


def _parse_dt(s: str) -> Optional[datetime]:
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None
