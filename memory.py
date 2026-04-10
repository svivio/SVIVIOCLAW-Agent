"""
SVIVIOCLAW — Persistent Task Memory
SQLite-backed memory: task history, learned facts, resumable sessions.
"""

import sqlite3
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

DB_PATH = Path(os.environ.get("SVIVIOCLAW_DB", Path(__file__).parent / "svivioclaw_memory.db"))


# ── Schema ────────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task        TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'running',
    result      TEXT,
    provider    TEXT,
    iterations  INTEGER DEFAULT 0,
    started_at  TEXT    NOT NULL,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS facts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    key        TEXT NOT NULL,
    value      TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    task_id    INTEGER,
    updated_at TEXT NOT NULL,
    UNIQUE(key)
);

CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id    INTEGER NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    ts         TEXT NOT NULL
);
"""

# ── Facts that the agent automatically learns and reuses ──────────────────────
# Key → human description
KNOWN_FACT_KEYS = {
    "claude_code_location":  "Where Claude Code app is located",
    "chrome_location":       "Where Google Chrome is located",
    "terminal_location":     "Where the terminal / cmd is",
    "preferred_language":    "User's preferred programming language",
    "workspace_folder":      "Main project/workspace folder path",
    "last_project_path":     "Path of the last coding project",
    "last_project_summary":  "Summary of the last coding project",
    "screen_layout":         "Observed screen layout / taskbar setup",
    "os_username":           "Windows username",
    "chrome_profile":        "Active Chrome profile name",
}


# ── MemoryManager ─────────────────────────────────────────────────────────────

class MemoryManager:
    """
    Manages SVIVIOCLAW's persistent memory.
    - Task history (all past runs, status, result)
    - Learned facts (app paths, preferences, workspace)
    - Resumable sessions (full message history for interrupted tasks)
    """

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._conn  = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    # ── Task lifecycle ────────────────────────────────────────────────────────

    def start_task(self, task: str, provider: str = "") -> int:
        """Create a new task record. Returns task_id."""
        cur = self._conn.execute(
            "INSERT INTO tasks (task, status, provider, started_at) VALUES (?,?,?,?)",
            (task, "running", provider, _now()),
        )
        self._conn.commit()
        return cur.lastrowid

    def finish_task(self, task_id: int, result: str, iterations: int, status: str = "done"):
        self._conn.execute(
            "UPDATE tasks SET status=?, result=?, iterations=?, finished_at=? WHERE id=?",
            (status, result, iterations, _now(), task_id),
        )
        self._conn.commit()

    def interrupt_task(self, task_id: int, iterations: int):
        self._conn.execute(
            "UPDATE tasks SET status='interrupted', iterations=?, finished_at=? WHERE id=?",
            (iterations, _now(), task_id),
        )
        self._conn.commit()

    # ── Message history (for resume) ──────────────────────────────────────────

    def save_messages(self, task_id: int, messages: list[dict]):
        """Persist the full message list for resumption."""
        self._conn.execute("DELETE FROM messages WHERE task_id=?", (task_id,))
        for msg in messages:
            self._conn.execute(
                "INSERT INTO messages (task_id, role, content, ts) VALUES (?,?,?,?)",
                (task_id, msg["role"], json.dumps(msg["content"]), _now()),
            )
        self._conn.commit()

    def load_messages(self, task_id: int) -> list[dict]:
        """Restore the message list for a task."""
        rows = self._conn.execute(
            "SELECT role, content FROM messages WHERE task_id=? ORDER BY id", (task_id,)
        ).fetchall()
        return [{"role": r["role"], "content": json.loads(r["content"])} for r in rows]

    # ── Facts ─────────────────────────────────────────────────────────────────

    def learn(self, key: str, value: str, task_id: Optional[int] = None, confidence: float = 1.0):
        """Store or update a learned fact."""
        self._conn.execute(
            """INSERT INTO facts (key, value, confidence, task_id, updated_at)
               VALUES (?,?,?,?,?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value,
               confidence=excluded.confidence, updated_at=excluded.updated_at""",
            (key, value, confidence, task_id, _now()),
        )
        self._conn.commit()

    def recall(self, key: str) -> Optional[str]:
        row = self._conn.execute("SELECT value FROM facts WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def all_facts(self) -> dict[str, str]:
        rows = self._conn.execute("SELECT key, value FROM facts ORDER BY key").fetchall()
        return {r["key"]: r["value"] for r in rows}

    # ── Task history ──────────────────────────────────────────────────────────

    def recent_tasks(self, limit: int = 20) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM tasks ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_task(self, task_id: int) -> Optional[dict]:
        row = self._conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return dict(row) if row else None

    def interrupted_tasks(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM tasks WHERE status='interrupted' ORDER BY id DESC LIMIT 10"
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Context block for system prompt ──────────────────────────────────────

    def context_block(self) -> str:
        """Return a memory summary to inject into the agent's system prompt."""
        facts = self.all_facts()
        recent = self.recent_tasks(5)

        lines = ["## SVIVIOCLAW Memory (from past sessions)"]

        if facts:
            lines.append("\n### Learned Facts")
            for k, v in facts.items():
                desc = KNOWN_FACT_KEYS.get(k, k)
                lines.append(f"- **{desc}**: {v}")

        if recent:
            lines.append("\n### Recent Tasks")
            for t in recent:
                status_icon = {"done": "✓", "failed": "✗", "interrupted": "⚡", "running": "…"}.get(
                    t["status"], "?"
                )
                ts = t["started_at"][:16] if t["started_at"] else ""
                result_snip = (t["result"] or "")[:80]
                lines.append(f"- [{status_icon}] [{ts}] {t['task'][:80]}")
                if result_snip:
                    lines.append(f"    → {result_snip}")

        lines.append(
            "\nUse these facts to work faster (e.g. don't search for app locations you already know)."
        )
        lines.append(
            "If you discover new facts (app paths, project folders, preferences), "
            "note them clearly in your response so they can be saved."
        )

        return "\n".join(lines)

    # ── Fact extractor ────────────────────────────────────────────────────────

    def extract_and_learn(self, text: str, task_id: Optional[int] = None):
        """
        Parse agent text for discoverable facts and save them.
        Looks for patterns like 'Claude Code is at C:\\...'.
        """
        import re
        patterns = [
            (r"Claude Code(?:\s+is)?\s+(?:at|located at|found at|path[:\s]+)\s*['\"]?([^\s'\"]+)", "claude_code_location"),
            (r"Chrome(?:\s+is)?\s+(?:at|located at|found at|path[:\s]+)\s*['\"]?([^\s'\"]+)", "chrome_location"),
            (r"workspace(?:\s+is)?\s+(?:at|in|located at)\s*['\"]?([^\s'\"]+)", "workspace_folder"),
            (r"project(?:\s+is)?\s+(?:at|in|located at)\s*['\"]?([^\s'\"]+)", "last_project_path"),
            (r"Windows user(?:name)?\s*[:\s]+([^\s,\.]+)", "os_username"),
        ]
        for pattern, key in patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                val = m.group(1).strip().rstrip("/\\.,")
                self.learn(key, val, task_id=task_id, confidence=0.8)


# ── Helper ────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


# ── Module-level singleton ─────────────────────────────────────────────────────

_default: Optional[MemoryManager] = None

def get_memory() -> MemoryManager:
    global _default
    if _default is None:
        _default = MemoryManager()
    return _default
