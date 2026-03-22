"""trevo MCP Server — exposes trevo functionality to Claude Code.

Run with: python -m mcp_server.server
Or configure in .claude/settings.json:
{
  "mcpServers": {
    "trevo": {
      "command": "python",
      "args": ["-m", "mcp_server.server"]
    }
  }
}
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add parent to path so we can import trevo modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from fastmcp import FastMCP
except ImportError:
    print("fastmcp not installed. Run: pip install fastmcp", file=sys.stderr)
    sys.exit(1)

mcp = FastMCP("trevo", description="trevo voice-to-text assistant")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_status() -> dict:
    """Get the current status of trevo (running state, engine, language)."""
    try:
        from models.settings import Settings
        settings = Settings.load()
        return {
            "stt_engine": settings.stt.engine,
            "language": settings.stt.language,
            "polishing_provider": settings.polishing.provider,
            "polishing_enabled": settings.polishing.enabled,
            "theme": settings.general.theme,
            "hotkey": settings.general.hotkey,
        }
    except Exception as exc:
        return {"error": f"Failed to load settings: {exc}"}


@mcp.tool()
def search_vault(query: str, max_results: int = 10) -> list[dict]:
    """Search the trevo knowledge vault for notes matching a query."""
    try:
        from knowledge.graph import KnowledgeGraph
        kg = KnowledgeGraph()
        results = kg.search(query)[:max_results]
        return [
            {
                "title": n.title,
                "path": str(Path(kg.vault_path) / n.filename),
                "tags": n.tags,
                "preview": n.content[:200],
            }
            for n in results
        ]
    except Exception as exc:
        return [{"error": f"Failed to search vault: {exc}"}]


@mcp.tool()
def get_vault_note(title: str) -> dict:
    """Get the full content of a knowledge vault note by title."""
    try:
        from knowledge.graph import KnowledgeGraph
        kg = KnowledgeGraph()
        # Try by title first, then by slug
        note = kg.get_note_by_title(title)
        if note is None:
            note = kg.get_note(title)
        if note:
            backlinks = kg.get_backlinks(note.title)
            return {
                "title": note.title,
                "content": note.content,
                "tags": note.tags,
                "links": note.outgoing_links,
                "backlinks": [n.title for n in backlinks],
            }
        return {"error": f"Note '{title}' not found"}
    except Exception as exc:
        return {"error": f"Failed to get note: {exc}"}


@mcp.tool()
def list_workflows() -> list[dict]:
    """List all available workflows."""
    try:
        from core.workflow_engine import WorkflowEngine
        workflows = WorkflowEngine.get_builtin_workflows()
        return [
            {
                "id": w.id,
                "name": w.name,
                "description": w.description,
                "node_count": len(w.nodes),
            }
            for w in workflows
        ]
    except Exception as exc:
        return [{"error": f"Failed to list workflows: {exc}"}]


@mcp.tool()
def get_transcript_history(limit: int = 20) -> list[dict]:
    """Get recent transcript history."""
    try:
        from storage.database import DatabaseManager
        db = DatabaseManager()
        transcripts = db.get_all_transcripts(limit=limit)
        return [
            {
                "id": str(t.id),
                "raw_text": t.raw_text[:200],
                "polished_text": t.polished_text[:200] if t.polished_text else "",
                "created_at": str(t.created_at),
            }
            for t in transcripts
        ]
    except Exception as exc:
        return [{"error": f"Failed to get transcripts: {exc}"}]


@mcp.tool()
def get_settings() -> dict:
    """Get the full trevo settings as a dictionary."""
    try:
        from models.settings import Settings
        settings = Settings.load()
        return settings._to_dict()
    except Exception as exc:
        return {"error": f"Failed to load settings: {exc}"}


@mcp.tool()
def update_setting(section: str, key: str, value: str) -> dict:
    """Update a single setting value. Section is like 'general', 'stt', 'polishing', etc."""
    try:
        from models.settings import Settings
        settings = Settings.load()
        data = settings._to_dict()
        if section not in data or not isinstance(data[section], dict):
            return {"error": f"Section '{section}' not found. Available: {[k for k in data if isinstance(data.get(k), dict)]}"}
        if key not in data[section]:
            return {"error": f"Key '{key}' not found in section '{section}'. Available: {list(data[section].keys())}"}

        # Type coerce based on current value
        current = data[section][key]
        if isinstance(current, bool):
            data[section][key] = value.lower() in ("true", "1", "yes")
        elif isinstance(current, int):
            data[section][key] = int(value)
        elif isinstance(current, float):
            data[section][key] = float(value)
        else:
            data[section][key] = value

        settings = Settings._from_dict(data)
        settings.save()
        return {"success": True, "section": section, "key": key, "value": data[section][key]}
    except Exception as exc:
        return {"error": f"Failed to update setting: {exc}"}


if __name__ == "__main__":
    mcp.run()
