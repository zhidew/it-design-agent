import sqlite3
import json
import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

# Get the base directory (it-design-agent)
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_DIR = BASE_DIR / "projects" / ".orchestrator"
DB_PATH = DB_DIR / "metadata.sqlite"

class MetadataDB:
    def __init__(self):
        DB_DIR.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self.synced = False

    def _get_connection(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS versions (
                    version_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    requirement TEXT,
                    run_status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (version_id, project_id),
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
            """)
            conn.commit()

    def upsert_project(self, project_id: str, name: str, description: Optional[str] = None):
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO projects (id, name, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    description=excluded.description,
                    updated_at=excluded.updated_at
            """, (project_id, name, description, now, now))
            conn.commit()

    def list_projects(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
            return [dict(row) for row in rows]

    def delete_project(self, project_id: str):
        with self._get_connection() as conn:
            conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            conn.commit()

    def upsert_version(self, project_id: str, version_id: str, requirement: str, run_status: str):
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO versions (version_id, project_id, requirement, run_status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(version_id, project_id) DO UPDATE SET
                    run_status=excluded.run_status,
                    updated_at=excluded.updated_at
            """, (version_id, project_id, requirement, run_status, now, now))
            conn.commit()

    def list_versions(self, project_id: str, page: int = 1, page_size: int = 10) -> Dict[str, Any]:
        offset = (page - 1) * page_size
        with self._get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM versions WHERE project_id = ?", (project_id,)).fetchone()[0]
            rows = conn.execute("""
                SELECT * FROM versions 
                WHERE project_id = ? 
                ORDER BY created_at DESC 
                LIMIT ? OFFSET ?
            """, (project_id, page_size, offset)).fetchall()
            
            return {
                "versions": [dict(row) for row in rows],
                "total": total,
                "page": page,
                "page_size": page_size
            }

    def delete_version(self, project_id: str, version_id: str):
        with self._get_connection() as conn:
            conn.execute("DELETE FROM versions WHERE project_id = ? AND version_id = ?", (project_id, version_id))
            conn.commit()

    def get_version(self, project_id: str, version_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM versions WHERE project_id = ? AND version_id = ?", (project_id, version_id)).fetchone()
            return dict(row) if row else None

metadata_db = MetadataDB()
