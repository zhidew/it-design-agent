import base64
import datetime
import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_DIR = BASE_DIR / "projects" / ".orchestrator"
DB_PATH = DB_DIR / "metadata.sqlite"
KEY_PATH = DB_DIR / "metadata.key"
ENV_PATH = BASE_DIR / ".env"

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:  # pragma: no cover
    Fernet = None
    InvalidToken = Exception


class SensitiveValueCodec:
    """Encrypt sensitive values when cryptography is available."""

    def __init__(self, key_path: Path):
        self._key_path = key_path
        self._fernet = self._build_fernet()

    def _build_fernet(self):
        if Fernet is None:
            return None

        env_key = os.getenv("IT_DESIGN_AGENT_METADATA_KEY")
        if env_key:
            return Fernet(env_key.encode("utf-8"))

        self._key_path.parent.mkdir(parents=True, exist_ok=True)
        if self._key_path.exists():
            key = self._key_path.read_bytes().strip()
        else:
            key = Fernet.generate_key()
            self._key_path.write_bytes(key)
        return Fernet(key)

    def encrypt(self, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if self._fernet is None:
            encoded = base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii")
            return f"plain:{encoded}"
        token = self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")
        return f"fernet:{token}"

    def decrypt(self, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if value.startswith("fernet:"):
            token = value[len("fernet:") :]
            if self._fernet is None:
                raise RuntimeError("Encrypted value found but cryptography is not installed.")
            try:
                return self._fernet.decrypt(token.encode("utf-8")).decode("utf-8")
            except InvalidToken as exc:
                raise RuntimeError("Failed to decrypt stored secret.") from exc
        if value.startswith("plain:"):
            encoded = value[len("plain:") :]
            return base64.urlsafe_b64decode(encoded.encode("ascii")).decode("utf-8")
        return value

    @staticmethod
    def mask(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if len(value) <= 4:
            return "*" * len(value)
        return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"


class MetadataDB:
    def __init__(self, db_path: Optional[Path] = None, env_path: Optional[Path] = None):
        self.db_path = Path(db_path or DB_PATH)
        self.db_dir = self.db_path.parent
        self.env_path = Path(env_path or ENV_PATH)
        key_path = KEY_PATH if db_path is None else self.db_dir / "metadata.key"
        self.codec = SensitiveValueCodec(key_path)
        self.db_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self.synced = False

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @staticmethod
    def _utcnow() -> str:
        return datetime.datetime.now(datetime.timezone.utc).isoformat()

    @staticmethod
    def _dumps_json(value: Any) -> Optional[str]:
        if value is None:
            return None
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def _loads_json(value: Optional[str], default: Any):
        if value in (None, ""):
            return default
        return json.loads(value)

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
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
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS repositories (
                    id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL DEFAULT 'git',
                    url TEXT NOT NULL,
                    branch TEXT NOT NULL DEFAULT 'main',
                    username TEXT,
                    token TEXT,
                    local_path TEXT,
                    description TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (project_id, id),
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS databases (
                    id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    host TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    database_name TEXT NOT NULL,
                    username TEXT,
                    password TEXT,
                    schema_filter TEXT,
                    description TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (project_id, id),
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_bases (
                    id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    path TEXT,
                    index_url TEXT,
                    includes TEXT,
                    description TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (project_id, id),
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS project_experts (
                    expert_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    description TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (project_id, expert_id),
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS project_llm_configs (
                    project_id TEXT PRIMARY KEY,
                    llm_provider TEXT,
                    openai_api_key TEXT,
                    openai_base_url TEXT,
                    openai_model_name TEXT,
                    gemini_api_key TEXT,
                    gemini_model_name TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS project_model_configs (
                    id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    api_key TEXT,
                    base_url TEXT,
                    headers TEXT,
                    model_name TEXT NOT NULL,
                    is_default INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (project_id, id),
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
                """
            )
            self._ensure_column(conn, "project_model_configs", "headers", "TEXT")
            conn.commit()

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, definition: str):
        columns = {
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name not in columns:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

    def _load_env_lines(self) -> List[str]:
        if not self.env_path.exists():
            return []
        return self.env_path.read_text(encoding="utf-8").splitlines()

    def _parse_env(self) -> Dict[str, str]:
        values: Dict[str, str] = {}
        for line in self._load_env_lines():
            if not line or line.lstrip().startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
        return values

    def get_system_llm_defaults(self, include_secrets: bool = False) -> Dict[str, Any]:
        env = self._parse_env()
        openai_api_key = env.get("OPENAI_API_KEY") or None
        gemini_api_key = env.get("GEMINI_API_KEY") or None
        result: Dict[str, Any] = {
            "llm_provider": env.get("LLM_PROVIDER", "openai"),
            "openai_base_url": env.get("OPENAI_BASE_URL", ""),
            "openai_model_name": env.get("OPENAI_MODEL_NAME", ""),
            "gemini_model_name": env.get("GEMINI_MODEL_NAME", ""),
            "has_openai_api_key": bool(openai_api_key),
            "has_gemini_api_key": bool(gemini_api_key),
        }
        if include_secrets:
            result["openai_api_key"] = openai_api_key
            result["gemini_api_key"] = gemini_api_key
        else:
            result["openai_api_key"] = self.codec.mask(openai_api_key)
            result["gemini_api_key"] = self.codec.mask(gemini_api_key)
        return result

    def upsert_project_model(self, project_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = self._utcnow()
        model_id = payload.get("id")
        existing = self.get_project_model(project_id, model_id, include_secrets=True) if model_id else None

        api_key = payload.get("api_key")
        headers = payload.get("headers")
        encrypted_api_key = (
            self.codec.encrypt(api_key)
            if api_key not in (None, "", "******")
            else (existing.get("_api_key_encrypted") if existing else None)
        )
        encrypted_headers = (
            self.codec.encrypt(self._dumps_json(headers))
            if headers not in (None, "", {})
            else (existing.get("_headers_encrypted") if existing else None)
        )

        with self._get_connection() as conn:
            if payload.get("is_default"):
                # Reset other default models for this project
                conn.execute(
                    "UPDATE project_model_configs SET is_default = 0 WHERE project_id = ?",
                    (project_id,),
                )

            conn.execute(
                """
                INSERT INTO project_model_configs (
                    id, project_id, name, provider, api_key, base_url, headers, model_name, is_default, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, id) DO UPDATE SET
                    name=excluded.name,
                    provider=excluded.provider,
                    api_key=excluded.api_key,
                    base_url=excluded.base_url,
                    headers=excluded.headers,
                    model_name=excluded.model_name,
                    is_default=excluded.is_default,
                    updated_at=excluded.updated_at
                """,
                (
                    model_id,
                    project_id,
                    payload.get("name"),
                    payload.get("provider"),
                    encrypted_api_key,
                    payload.get("base_url"),
                    encrypted_headers,
                    payload.get("model_name"),
                    1 if payload.get("is_default") else 0,
                    (existing.get("created_at") if existing else now),
                    now,
                ),
            )
            conn.commit()
        return self.get_project_model(project_id, model_id, include_secrets=False)

    def list_project_models(self, project_id: str, include_secrets: bool = False) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM project_model_configs WHERE project_id = ? ORDER BY is_default DESC, updated_at DESC",
                (project_id,),
            ).fetchall()
        return [self._row_to_model_config(dict(row), include_secrets=include_secrets) for row in rows]

    def delete_project_model(self, project_id: str, model_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM project_model_configs WHERE project_id = ? AND id = ?",
                (project_id, model_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_project_model(self, project_id: str, model_id: str, include_secrets: bool = False) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM project_model_configs WHERE project_id = ? AND id = ?",
                (project_id, model_id),
            ).fetchone()
        return self._row_to_model_config(dict(row), include_secrets=include_secrets) if row else None

    def _row_to_model_config(self, row: Dict[str, Any], include_secrets: bool) -> Dict[str, Any]:
        encrypted_api_key = row.pop("api_key", None)
        encrypted_headers = row.pop("headers", None)
        api_key = self.codec.decrypt(encrypted_api_key) if encrypted_api_key else None
        headers_raw = self.codec.decrypt(encrypted_headers) if encrypted_headers else None
        headers = self._loads_json(headers_raw, None)

        result: Dict[str, Any] = {
            "id": row["id"],
            "project_id": row["project_id"],
            "name": row["name"],
            "provider": row["provider"],
            "base_url": row["base_url"],
            "model_name": row["model_name"],
            "is_default": bool(row["is_default"]),
            "has_api_key": bool(encrypted_api_key),
            "has_headers": bool(encrypted_headers),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        if include_secrets:
            result["api_key"] = api_key
            result["headers"] = headers
            result["_api_key_encrypted"] = encrypted_api_key
            result["_headers_encrypted"] = encrypted_headers
        else:
            result["api_key"] = self.codec.mask(api_key)
            result["headers"] = None
        return result

    def upsert_project(self, project_id: str, name: str, description: Optional[str] = None):
        now = self._utcnow()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO projects (id, name, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    description=excluded.description,
                    updated_at=excluded.updated_at
                """,
                (project_id, name, description, now, now),
            )
            conn.commit()

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return dict(row) if row else None

    def list_projects(self, runtime_states: Optional[Dict[str, Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
        
        projects = []
        for row in rows:
            proj = dict(row)
            # Get project status info
            project_id = proj['id']
            
            # Count versions with all status breakdown
            with self._get_connection() as conn:
                version_rows = conn.execute(
                    "SELECT version_id, run_status FROM versions WHERE project_id = ?",
                    (project_id,)
                ).fetchall()
            
            # Build version status map, overlay with runtime states
            version_statuses = {v['version_id']: v['run_status'] for v in version_rows}
            if runtime_states:
                for version_id, rt_state in runtime_states.items():
                    if rt_state.get('project_id') == project_id:
                        rt_status = rt_state.get('run_status')
                        if rt_status:
                            version_statuses[version_id] = rt_status
            
            # Count all statuses
            status_counts = {
                'running': 0,
                'success': 0,
                'failed': 0,
                'waiting_human': 0,
                'queued': 0,
                'unknown': 0,
            }
            for status in version_statuses.values():
                if status in status_counts:
                    status_counts[status] += 1
                else:
                    status_counts['unknown'] += 1
            
            total_versions = len(version_statuses)
            
            # Determine status
            has_versions = total_versions > 0
            is_active = status_counts['running'] > 0 or status_counts['waiting_human'] > 0
            
            proj['total_versions'] = total_versions
            proj['enabled_experts_count'] = len(self.list_enabled_expert_ids(project_id))
            proj['running_versions'] = status_counts['running']
            proj['success_versions'] = status_counts['success']
            proj['failed_versions'] = status_counts['failed']
            proj['waiting_versions'] = status_counts['waiting_human']
            proj['queued_versions'] = status_counts['queued']
            proj['unknown_versions'] = status_counts['unknown']
            proj['status_counts'] = status_counts
            proj['has_versions'] = has_versions
            proj['is_active'] = is_active
            proj['status'] = 'active' if is_active else ('ready' if has_versions else 'empty')
            
            projects.append(proj)
        
        return projects

    def delete_project(self, project_id: str):
        with self._get_connection() as conn:
            conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            conn.commit()

    def upsert_version(self, project_id: str, version_id: str, requirement: str, run_status: str):
        now = self._utcnow()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO versions (version_id, project_id, requirement, run_status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(version_id, project_id) DO UPDATE SET
                    run_status=excluded.run_status,
                    updated_at=excluded.updated_at
                """,
                (version_id, project_id, requirement, run_status, now, now),
            )
            conn.commit()

    def list_versions(self, project_id: str, page: int = 1, page_size: int = 10) -> Dict[str, Any]:
        offset = (page - 1) * page_size
        with self._get_connection() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM versions WHERE project_id = ?",
                (project_id,),
            ).fetchone()[0]
            rows = conn.execute(
                """
                SELECT * FROM versions
                WHERE project_id = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (project_id, page_size, offset),
            ).fetchall()
        return {
            "versions": [dict(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def delete_version(self, project_id: str, version_id: str):
        with self._get_connection() as conn:
            conn.execute(
                "DELETE FROM versions WHERE project_id = ? AND version_id = ?",
                (project_id, version_id),
            )
            conn.commit()

    def get_version(self, project_id: str, version_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM versions WHERE project_id = ? AND version_id = ?",
                (project_id, version_id),
            ).fetchone()
        return dict(row) if row else None

    def upsert_repository(self, project_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = self._utcnow()
        existing = self.get_repository(project_id, payload["id"], include_secrets=True)
        token = payload.get("token")
        encrypted_token = self.codec.encrypt(token) if token is not None else (existing.get("_token_encrypted") if existing else None)
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO repositories (
                    id, project_id, name, type, url, branch, username, token, local_path,
                    description, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, id) DO UPDATE SET
                    name=excluded.name,
                    type=excluded.type,
                    url=excluded.url,
                    branch=excluded.branch,
                    username=excluded.username,
                    token=excluded.token,
                    local_path=excluded.local_path,
                    description=excluded.description,
                    updated_at=excluded.updated_at
                """,
                (
                    payload["id"],
                    project_id,
                    payload["name"],
                    payload.get("type", "git"),
                    payload["url"],
                    payload.get("branch", "main"),
                    payload.get("username"),
                    encrypted_token,
                    payload.get("local_path"),
                    payload.get("description"),
                    existing.get("created_at") if existing else now,
                    now,
                ),
            )
            conn.commit()
        return self.get_repository(project_id, payload["id"], include_secrets=False)

    def list_repositories(self, project_id: str, include_secrets: bool = False) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM repositories WHERE project_id = ? ORDER BY updated_at DESC",
                (project_id,),
            ).fetchall()
        return [self._row_to_repository(dict(row), include_secrets) for row in rows]

    def get_repository(self, project_id: str, repo_id: str, include_secrets: bool = False) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM repositories WHERE project_id = ? AND id = ?",
                (project_id, repo_id),
            ).fetchone()
        return self._row_to_repository(dict(row), include_secrets) if row else None

    def delete_repository(self, project_id: str, repo_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM repositories WHERE project_id = ? AND id = ?",
                (project_id, repo_id),
            )
            conn.commit()
        return cursor.rowcount > 0

    def _row_to_repository(self, row: Dict[str, Any], include_secrets: bool) -> Dict[str, Any]:
        encrypted_token = row.pop("token", None)
        result = {
            "id": row["id"],
            "project_id": row["project_id"],
            "name": row["name"],
            "type": row["type"],
            "url": row["url"],
            "branch": row["branch"],
            "username": row["username"],
            "local_path": row["local_path"],
            "description": row["description"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        if include_secrets:
            result["token"] = self.codec.decrypt(encrypted_token)
            result["_token_encrypted"] = encrypted_token
        else:
            token = self.codec.decrypt(encrypted_token) if encrypted_token else None
            result["token"] = self.codec.mask(token)
            result["has_token"] = bool(encrypted_token)
        return result

    def upsert_database(self, project_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = self._utcnow()
        existing = self.get_database(project_id, payload["id"], include_secrets=True)
        password = payload.get("password")
        encrypted_password = self.codec.encrypt(password) if password is not None else (existing.get("_password_encrypted") if existing else None)
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO databases (
                    id, project_id, name, type, host, port, database_name, username, password,
                    schema_filter, description, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, id) DO UPDATE SET
                    name=excluded.name,
                    type=excluded.type,
                    host=excluded.host,
                    port=excluded.port,
                    database_name=excluded.database_name,
                    username=excluded.username,
                    password=excluded.password,
                    schema_filter=excluded.schema_filter,
                    description=excluded.description,
                    updated_at=excluded.updated_at
                """,
                (
                    payload["id"],
                    project_id,
                    payload["name"],
                    payload["type"],
                    payload["host"],
                    payload["port"],
                    payload["database"],
                    payload.get("username"),
                    encrypted_password,
                    self._dumps_json(payload.get("schema_filter", [])),
                    payload.get("description"),
                    (existing.get("created_at") if existing and existing.get("created_at") else now),
                    now,
                ),
            )
            conn.commit()
        return self.get_database(project_id, payload["id"], include_secrets=False)

    def list_databases(self, project_id: str, include_secrets: bool = False) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM databases WHERE project_id = ? ORDER BY updated_at DESC",
                (project_id,),
            ).fetchall()
        return [self._row_to_database(dict(row), include_secrets) for row in rows]

    def get_database(self, project_id: str, db_id: str, include_secrets: bool = False) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM databases WHERE project_id = ? AND id = ?",
                (project_id, db_id),
            ).fetchone()
        return self._row_to_database(dict(row), include_secrets) if row else None

    def delete_database(self, project_id: str, db_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM databases WHERE project_id = ? AND id = ?",
                (project_id, db_id),
            )
            conn.commit()
        return cursor.rowcount > 0

    def _row_to_database(self, row: Dict[str, Any], include_secrets: bool) -> Dict[str, Any]:
        encrypted_password = row.pop("password", None)
        result = {
            "id": row["id"],
            "project_id": row["project_id"],
            "name": row["name"],
            "type": row["type"],
            "host": row["host"],
            "port": row["port"],
            "database": row["database_name"],
            "username": row["username"],
            "schema_filter": self._loads_json(row["schema_filter"], []),
            "description": row["description"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        if include_secrets:
            result["password"] = self.codec.decrypt(encrypted_password)
            result["_password_encrypted"] = encrypted_password
        else:
            password = self.codec.decrypt(encrypted_password) if encrypted_password else None
            result["password"] = self.codec.mask(password)
            result["has_password"] = bool(encrypted_password)
        return result

    def upsert_knowledge_base(self, project_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = self._utcnow()
        existing = self.get_knowledge_base(project_id, payload["id"])
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO knowledge_bases (
                    id, project_id, name, type, path, index_url, includes, description, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, id) DO UPDATE SET
                    name=excluded.name,
                    type=excluded.type,
                    path=excluded.path,
                    index_url=excluded.index_url,
                    includes=excluded.includes,
                    description=excluded.description,
                    updated_at=excluded.updated_at
                """,
                (
                    payload["id"],
                    project_id,
                    payload["name"],
                    payload["type"],
                    payload.get("path"),
                    payload.get("index_url"),
                    self._dumps_json(payload.get("includes", [])),
                    payload.get("description"),
                    existing.get("created_at") if existing else now,
                    now,
                ),
            )
            conn.commit()
        return self.get_knowledge_base(project_id, payload["id"])

    def list_knowledge_bases(self, project_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM knowledge_bases WHERE project_id = ? ORDER BY updated_at DESC",
                (project_id,),
            ).fetchall()
        return [self._row_to_knowledge_base(dict(row)) for row in rows]

    def get_knowledge_base(self, project_id: str, kb_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM knowledge_bases WHERE project_id = ? AND id = ?",
                (project_id, kb_id),
            ).fetchone()
        return self._row_to_knowledge_base(dict(row)) if row else None

    def delete_knowledge_base(self, project_id: str, kb_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM knowledge_bases WHERE project_id = ? AND id = ?",
                (project_id, kb_id),
            )
            conn.commit()
        return cursor.rowcount > 0

    def _row_to_knowledge_base(self, row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "name": row["name"],
            "type": row["type"],
            "path": row["path"],
            "index_url": row["index_url"],
            "includes": self._loads_json(row["includes"], []),
            "description": row["description"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def upsert_project_expert(self, project_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = self._utcnow()
        existing = self.get_project_expert(project_id, payload["id"])
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO project_experts (
                    expert_id, project_id, enabled, description, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, expert_id) DO UPDATE SET
                    enabled=excluded.enabled,
                    description=excluded.description,
                    updated_at=excluded.updated_at
                """,
                (
                    payload["id"],
                    project_id,
                    1 if payload.get("enabled", True) else 0,
                    payload.get("description"),
                    (existing.get("created_at") if existing and existing.get("created_at") else now),
                    now,
                ),
            )
            conn.commit()
        return self.get_project_expert(project_id, payload["id"]) or {
            "id": payload["id"],
            "project_id": project_id,
            "name": payload.get("name", payload["id"]),
            "enabled": bool(payload.get("enabled", True)),
            "description": payload.get("description"),
            "created_at": (existing.get("created_at") if existing and existing.get("created_at") else now),
            "updated_at": now,
        }

    def list_project_experts(self, project_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM project_experts WHERE project_id = ? ORDER BY updated_at DESC",
                (project_id,),
            ).fetchall()
        stored = {row["expert_id"]: dict(row) for row in rows}

        try:
            from registry.expert_registry import ExpertRegistry

            registry = ExpertRegistry.get_instance()
            manifests = sorted(registry.get_all_manifests(), key=lambda item: item.capability)
        except RuntimeError:
            manifests = []

        # System experts that should not be configurable per project
        system_experts = {"expert-creator"}

        experts: List[Dict[str, Any]] = []
        for manifest in manifests:
            if manifest.capability in system_experts:
                continue

            row = stored.pop(manifest.capability, None)
            experts.append(
                {
                    "id": manifest.capability,
                    "project_id": project_id,
                    "name": manifest.name or manifest.capability,
                    "enabled": bool(row["enabled"]) if row else False,
                    "description": row["description"] if row and row.get("description") else manifest.description,
                    "created_at": row["created_at"] if row else None,
                    "updated_at": row["updated_at"] if row else None,
                }
            )

        for expert_id, row in stored.items():
            if expert_id in system_experts:
                continue

            experts.append(
                {
                    "id": expert_id,
                    "project_id": project_id,
                    "name": expert_id,
                    "enabled": bool(row["enabled"]),
                    "description": row.get("description"),
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            )

        return experts

    def get_project_expert(self, project_id: str, expert_id: str) -> Optional[Dict[str, Any]]:
        for expert in self.list_project_experts(project_id):
            if expert["id"] == expert_id:
                return expert
        return None

    def list_enabled_expert_ids(self, project_id: str) -> List[str]:
        return [expert["id"] for expert in self.list_project_experts(project_id) if expert.get("enabled")]

    def upsert_project_llm_config(self, project_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = self._utcnow()
        existing = self.get_project_llm_config(project_id, include_secrets=True, merge_defaults=False)

        openai_api_key = payload.get("openai_api_key")
        gemini_api_key = payload.get("gemini_api_key")

        encrypted_openai_api_key = (
            self.codec.encrypt(openai_api_key)
            if openai_api_key not in (None, "")
            else (existing.get("_openai_api_key_encrypted") if existing else None)
        )
        encrypted_gemini_api_key = (
            self.codec.encrypt(gemini_api_key)
            if gemini_api_key not in (None, "")
            else (existing.get("_gemini_api_key_encrypted") if existing else None)
        )

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO project_llm_configs (
                    project_id, llm_provider, openai_api_key, openai_base_url, openai_model_name,
                    gemini_api_key, gemini_model_name, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    llm_provider=excluded.llm_provider,
                    openai_api_key=excluded.openai_api_key,
                    openai_base_url=excluded.openai_base_url,
                    openai_model_name=excluded.openai_model_name,
                    gemini_api_key=excluded.gemini_api_key,
                    gemini_model_name=excluded.gemini_model_name,
                    updated_at=excluded.updated_at
                """,
                (
                    project_id,
                    payload.get("llm_provider") or (existing.get("llm_provider") if existing else None),
                    encrypted_openai_api_key,
                    payload.get("openai_base_url"),
                    payload.get("openai_model_name"),
                    encrypted_gemini_api_key,
                    payload.get("gemini_model_name"),
                    (existing.get("created_at") if existing and existing.get("created_at") else now),
                    now,
                ),
            )
            conn.commit()
        return self.get_project_llm_config(project_id, include_secrets=False, merge_defaults=True)

    def get_project_llm_config(
        self,
        project_id: str,
        *,
        include_secrets: bool = False,
        merge_defaults: bool = True,
    ) -> Dict[str, Any]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM project_llm_configs WHERE project_id = ?",
                (project_id,),
            ).fetchone()

        project_config = self._row_to_project_llm_config(dict(row), include_secrets=include_secrets) if row else None
        if not merge_defaults:
            return project_config or {
                "project_id": project_id,
                "llm_provider": None,
                "openai_api_key": None if include_secrets else None,
                "openai_base_url": None,
                "openai_model_name": None,
                "gemini_api_key": None if include_secrets else None,
                "gemini_model_name": None,
                "has_openai_api_key": False,
                "has_gemini_api_key": False,
            }

        defaults = self.get_system_llm_defaults(include_secrets=include_secrets)
        result: Dict[str, Any] = {
            "project_id": project_id,
            "llm_provider": (project_config or {}).get("llm_provider") or defaults.get("llm_provider") or "openai",
            "openai_base_url": (project_config or {}).get("openai_base_url") or defaults.get("openai_base_url") or "",
            "openai_model_name": (project_config or {}).get("openai_model_name") or defaults.get("openai_model_name") or "",
            "gemini_model_name": (project_config or {}).get("gemini_model_name") or defaults.get("gemini_model_name") or "",
            "has_openai_api_key": bool((project_config or {}).get("has_openai_api_key") or defaults.get("has_openai_api_key")),
            "has_gemini_api_key": bool((project_config or {}).get("has_gemini_api_key") or defaults.get("has_gemini_api_key")),
        }

        if include_secrets:
            result["openai_api_key"] = (project_config or {}).get("openai_api_key") or defaults.get("openai_api_key")
            result["gemini_api_key"] = (project_config or {}).get("gemini_api_key") or defaults.get("gemini_api_key")
        else:
            result["openai_api_key"] = (
                (project_config or {}).get("openai_api_key")
                or defaults.get("openai_api_key")
            )
            result["gemini_api_key"] = (
                (project_config or {}).get("gemini_api_key")
                or defaults.get("gemini_api_key")
            )

        if project_config:
            result["created_at"] = project_config.get("created_at")
            result["updated_at"] = project_config.get("updated_at")
        return result

    def _row_to_project_llm_config(self, row: Dict[str, Any], include_secrets: bool) -> Dict[str, Any]:
        encrypted_openai_api_key = row.pop("openai_api_key", None)
        encrypted_gemini_api_key = row.pop("gemini_api_key", None)
        openai_api_key = self.codec.decrypt(encrypted_openai_api_key) if encrypted_openai_api_key else None
        gemini_api_key = self.codec.decrypt(encrypted_gemini_api_key) if encrypted_gemini_api_key else None

        result: Dict[str, Any] = {
            "project_id": row["project_id"],
            "llm_provider": row["llm_provider"],
            "openai_base_url": row["openai_base_url"],
            "openai_model_name": row["openai_model_name"],
            "gemini_model_name": row["gemini_model_name"],
            "has_openai_api_key": bool(encrypted_openai_api_key),
            "has_gemini_api_key": bool(encrypted_gemini_api_key),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        if include_secrets:
            result["openai_api_key"] = openai_api_key
            result["gemini_api_key"] = gemini_api_key
            result["_openai_api_key_encrypted"] = encrypted_openai_api_key
            result["_gemini_api_key_encrypted"] = encrypted_gemini_api_key
        else:
            result["openai_api_key"] = self.codec.mask(openai_api_key)
            result["gemini_api_key"] = self.codec.mask(gemini_api_key)
        return result


metadata_db = MetadataDB()
