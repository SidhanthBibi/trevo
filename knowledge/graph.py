"""Knowledge graph manager for trevo.

Manages a vault of .md notes on disk, builds a link graph between them,
supports search, backlinks, and auto-linking from dictation transcripts.
"""
from __future__ import annotations

import os
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from utils.logger import logger
from knowledge.note import Note, _WIKILINK_RE


def _default_vault_path() -> Path:
    """Return the default vault directory: ~/trevo-vault/"""
    return Path.home() / "trevo-vault"


class KnowledgeGraph:
    """Manages a vault of linked Markdown notes.

    The vault is a folder of .md files.  The graph is a bi-directional
    link index built from [[wikilinks]] found in note content.
    """

    def __init__(self, vault_path: Optional[Path] = None) -> None:
        self.vault_path = vault_path or _default_vault_path()
        self.vault_path.mkdir(parents=True, exist_ok=True)

        # In-memory index: slug -> Note
        self._notes: dict[str, Note] = {}
        # Backlinks: title -> set of titles that link TO it
        self._backlinks: dict[str, set[str]] = defaultdict(set)

        self._load_vault()
        logger.info(
            "KnowledgeGraph loaded {} notes from {}",
            len(self._notes),
            self.vault_path,
        )

    # ------------------------------------------------------------------
    # Vault I/O
    # ------------------------------------------------------------------

    def _load_vault(self) -> None:
        """Scan vault directory and load all .md files."""
        self._notes.clear()
        self._backlinks.clear()
        for md_file in self.vault_path.glob("*.md"):
            try:
                text = md_file.read_text(encoding="utf-8")
                note = Note.from_markdown(text, filepath=md_file)
                self._notes[note.slug] = note
            except Exception:
                logger.exception("Failed to load note: {}", md_file.name)

        # Build backlinks
        for note in self._notes.values():
            for link_title in note.outgoing_links:
                self._backlinks[self._slugify(link_title)].add(note.title)

    def save_note(self, note: Note) -> Path:
        """Write a note to disk and update the in-memory index."""
        note.updated_at = datetime.now()
        filepath = self.vault_path / note.filename
        filepath.write_text(note.to_markdown(), encoding="utf-8")

        # Update index
        self._notes[note.slug] = note

        # Rebuild backlinks for this note
        for link_title in note.outgoing_links:
            self._backlinks[self._slugify(link_title)].add(note.title)

        logger.debug("Saved note '{}' → {}", note.title, filepath)
        return filepath

    def delete_note(self, slug: str) -> bool:
        """Delete a note from disk and index."""
        note = self._notes.pop(slug, None)
        if note is None:
            return False
        filepath = self.vault_path / note.filename
        if filepath.exists():
            filepath.unlink()
        # Clean backlinks
        for link_title in note.outgoing_links:
            link_slug = self._slugify(link_title)
            self._backlinks[link_slug].discard(note.title)
        logger.debug("Deleted note '{}'", note.title)
        return True

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def get_note(self, slug: str) -> Optional[Note]:
        return self._notes.get(slug)

    def get_note_by_title(self, title: str) -> Optional[Note]:
        slug = self._slugify(title)
        return self._notes.get(slug)

    def all_notes(self) -> list[Note]:
        """Return all notes sorted by updated_at (newest first)."""
        return sorted(self._notes.values(), key=lambda n: n.updated_at, reverse=True)

    def search(self, query: str) -> list[Note]:
        """Full-text search across title, content, and tags."""
        q = query.lower()
        results = []
        for note in self._notes.values():
            if (
                q in note.title.lower()
                or q in note.content.lower()
                or any(q in t.lower() for t in note.tags)
            ):
                results.append(note)
        return sorted(results, key=lambda n: n.updated_at, reverse=True)

    def get_backlinks(self, title: str) -> list[Note]:
        """Return all notes that link TO the given title."""
        slug = self._slugify(title)
        linking_titles = self._backlinks.get(slug, set())
        return [
            self._notes[self._slugify(t)]
            for t in linking_titles
            if self._slugify(t) in self._notes
        ]

    def get_tags(self) -> dict[str, int]:
        """Return a tag -> count mapping across all notes."""
        tag_counts: dict[str, int] = defaultdict(int)
        for note in self._notes.values():
            for tag in note.tags:
                tag_counts[tag] += 1
        return dict(sorted(tag_counts.items(), key=lambda x: -x[1]))

    def get_notes_by_tag(self, tag: str) -> list[Note]:
        return [n for n in self._notes.values() if tag in n.tags]

    # ------------------------------------------------------------------
    # Auto-linking: create a note from a dictation transcript
    # ------------------------------------------------------------------

    def create_from_dictation(
        self,
        raw_text: str,
        polished_text: str,
        app_context: str = "",
        auto_link: bool = True,
    ) -> Note:
        """Create a new note from a dictation transcript.

        If *auto_link* is True, scans the polished text for mentions of
        existing note titles and wraps them in [[wikilinks]].
        """
        # Generate title from first ~60 chars of polished text
        title = self._generate_title(polished_text)

        content = polished_text
        if auto_link:
            content = self._auto_insert_wikilinks(content)

        # Auto-tag based on content
        tags = self._auto_tag(content, app_context)

        note = Note(
            title=title,
            content=content,
            tags=tags,
            source="dictation",
            app_context=app_context,
        )

        # If raw text differs significantly, include it as a details block
        if raw_text.strip() != polished_text.strip():
            note.content += f"\n\n<details><summary>Raw transcript</summary>\n\n{raw_text}\n\n</details>"

        self.save_note(note)
        return note

    def create_from_chat(
        self,
        title: str,
        content: str,
        tags: Optional[list[str]] = None,
    ) -> Note:
        """Create a note from an agent/chat interaction."""
        note = Note(
            title=title,
            content=self._auto_insert_wikilinks(content),
            tags=tags or ["chat"],
            source="chat",
        )
        self.save_note(note)
        return note

    # ------------------------------------------------------------------
    # Auto-linking helpers
    # ------------------------------------------------------------------

    def _auto_insert_wikilinks(self, text: str) -> str:
        """Scan text for mentions of existing note titles and wrap in [[...]]."""
        # Already-linked titles: don't double-link
        already_linked = set(_WIKILINK_RE.findall(text))

        for note in self._notes.values():
            if note.title in already_linked:
                continue
            if len(note.title) < 3:
                continue
            # Case-insensitive whole-word match
            pattern = r"\b" + re.escape(note.title) + r"\b"
            if re.search(pattern, text, re.IGNORECASE):
                # Replace first occurrence only
                text = re.sub(pattern, f"[[{note.title}]]", text, count=1, flags=re.IGNORECASE)

        return text

    def _generate_title(self, text: str) -> str:
        """Generate a short title from the first sentence or ~60 chars."""
        # Take first sentence
        first_sentence = re.split(r"[.!?\n]", text)[0].strip()
        if len(first_sentence) > 60:
            first_sentence = first_sentence[:57] + "..."
        return first_sentence or f"Note {datetime.now().strftime('%Y-%m-%d %H:%M')}"

    def _auto_tag(self, content: str, app_context: str) -> list[str]:
        """Auto-generate tags based on content and context."""
        tags: list[str] = []
        if app_context:
            tags.append(app_context)

        # Simple keyword-based tagging
        content_lower = content.lower()
        keyword_tags = {
            "meeting": ["meeting", "notes"],
            "todo": ["todo", "task"],
            "idea": ["idea"],
            "bug": ["bug", "issue"],
            "email": ["email", "communication"],
            "code": ["code", "programming"],
            "design": ["design"],
            "research": ["research"],
        }
        for keyword, tag_list in keyword_tags.items():
            if keyword in content_lower:
                tags.extend(tag_list)

        return list(dict.fromkeys(tags))  # dedupe, preserve order

    # ------------------------------------------------------------------
    # Graph statistics
    # ------------------------------------------------------------------

    def graph_stats(self) -> dict[str, int]:
        """Return statistics about the knowledge graph."""
        total_links = sum(len(n.outgoing_links) for n in self._notes.values())
        return {
            "total_notes": len(self._notes),
            "total_links": total_links,
            "total_tags": len(self.get_tags()),
            "orphan_notes": sum(
                1 for n in self._notes.values()
                if not n.outgoing_links and not self._backlinks.get(n.slug)
            ),
        }

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _slugify(title: str) -> str:
        safe = re.sub(r"[^\w\s-]", "", title.lower())
        return re.sub(r"[\s]+", "-", safe).strip("-")
