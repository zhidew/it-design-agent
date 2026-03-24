"""
Connectivity service for various resource types.
Provides reusable test functions for repositories, databases, and knowledge bases.
"""
import os
import subprocess
from base64 import b64encode
from pathlib import Path
from typing import Any, Dict
from urllib.parse import quote, urlsplit, urlunsplit


class TestResult:
    """Test result container with success status and message."""
    def __init__(self, success: bool, message: str, details: Dict[str, Any] = None):
        self.success = success
        self.message = message
        self.details = details or {}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            **self.details
        }


def _default_git_username(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    if host == "github.com" or host.endswith(".github.com"):
        return "x-access-token"
    if host == "gitlab.com" or host.endswith(".gitlab.com"):
        return "oauth2"
    return "git"


def _build_git_url_with_credentials(url: str, username: str | None, token: str | None) -> str:
    if not token:
        return url

    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return url

    auth_username = username or _default_git_username(url)
    netloc = f"{quote(auth_username, safe='')}:{quote(token, safe='')}@{parsed.hostname}"
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"

    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def _build_git_auth_header(username: str | None, token: str | None, url: str) -> str | None:
    if not token:
        return None
    auth_username = username or _default_git_username(url)
    encoded = b64encode(f"{auth_username}:{token}".encode("utf-8")).decode("ascii")
    return f"Authorization: Basic {encoded}"


def test_repository_connection(config: Dict[str, Any]) -> TestResult:
    """
    Test repository connection by attempting to access the repository.
    Supports Git repositories.
    """
    repo_type = config.get("type", "git").lower()
    url = config.get("url", "").strip()
    branch = config.get("branch", "main")
    username = config.get("username")
    token = config.get("token")
    local_path = config.get("local_path")
    
    if not url:
        return TestResult(False, "Repository URL is required.")
    
    if repo_type != "git":
        return TestResult(False, f"Unsupported repository type: {repo_type}")
    
    git_url = _build_git_url_with_credentials(url, username, token)
    
    # If local path exists, test if it's a valid git directory
    if local_path:
        local_path_obj = Path(local_path)
        if local_path_obj.exists():
            # Check if it's a git repo
            try:
                result = subprocess.run(
                    ["git", "-C", str(local_path_obj), "rev-parse", "--git-dir"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0:
                    return TestResult(
                        True, 
                        f"Local repository is valid. Git directory found at {local_path}",
                        {"local": True}
                    )
            except Exception as e:
                return TestResult(False, f"Failed to access local repository: {str(e)}")
    
    # Test remote connection using git ls-remote
    try:
        cmd = [
            "git",
            "-c",
            "credential.helper=",
            "-c",
            "core.askPass=",
            "-c",
            "credential.interactive=never",
            "ls-remote",
            "--heads",
        ]
        auth_header = _build_git_auth_header(username, token, url)
        if auth_header:
            cmd.extend(["-c", f"http.extraHeader={auth_header}"])
        cmd.extend([git_url, branch])
        env = os.environ.copy()
        # Force Git/GCM into non-interactive mode so the test reflects only the supplied config.
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_ASKPASS"] = ""
        env["SSH_ASKPASS"] = ""
        env["GCM_INTERACTIVE"] = "never"
        env["GCM_MODAL_PROMPT"] = "0"
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            env=env
        )
        
        if result.returncode == 0:
            # Check if we got any refs back
            if result.stdout.strip():
                return TestResult(
                    True,
                    f"Successfully connected to repository. Branch '{branch}' exists.",
                    {"remote": True}
                )
            else:
                return TestResult(
                    False,
                    f"Repository accessible but branch '{branch}' not found."
                )
        else:
            error_msg = result.stderr.strip() if result.stderr else "Unknown error"
            lowered = error_msg.lower()
            if (
                "authentication" in lowered
                or "credential" in lowered
                or "could not read username" in lowered
                or "terminal prompts disabled" in lowered
            ):
                return TestResult(False, "Authentication failed. Please check username and token.")
            if "not found" in lowered:
                return TestResult(False, "Repository not found. Please check the URL.")
            return TestResult(False, f"Failed to connect: {error_msg}")
            
    except subprocess.TimeoutExpired:
        return TestResult(False, "Connection timed out. Please check the URL and try again.")
    except FileNotFoundError:
        return TestResult(False, "Git is not installed or not in PATH.")
    except Exception as e:
        return TestResult(False, f"Error testing repository: {str(e)}")


def test_database_connection(config: Dict[str, Any]) -> TestResult:
    """
    Test database connection by attempting to connect and run a simple query.
    """
    db_type = config.get("type", "").lower()
    host = config.get("host", "").strip()
    port = config.get("port", 0)
    database = config.get("database", "").strip()
    username = config.get("username")
    password = config.get("password")
    
    if not host:
        return TestResult(False, "Database host is required.")
    if not database:
        return TestResult(False, "Database name is required.")
    
    # SQLite is a special case - just check if we can access the file
    if db_type == "sqlite":
        db_path = Path(database)
        if db_path.exists():
            if os.access(db_path, os.R_OK):
                return TestResult(True, f"SQLite database file is accessible: {database}")
            else:
                return TestResult(False, f"Cannot read SQLite database file: {database}")
        else:
            # Try to create the file path's directory to test write access
            parent = db_path.parent
            if parent.exists() and os.access(parent, os.W_OK):
                return TestResult(True, f"SQLite database path is valid (file may be created): {database}")
            return TestResult(False, f"Cannot access SQLite database path: {database}")
    
    if not port or port <= 0:
        return TestResult(False, "Valid port number is required.")
    
    # Test based on database type
    if db_type == "postgresql":
        return _test_postgresql(host, port, database, username, password)
    elif db_type == "mysql":
        return _test_mysql(host, port, database, username, password)
    elif db_type == "opengauss":
        return _test_opengauss(host, port, database, username, password)
    elif db_type == "dws":
        return _test_dws(host, port, database, username, password)
    elif db_type == "oracle":
        return _test_oracle(host, port, database, username, password)
    else:
        return TestResult(False, f"Unsupported database type: {db_type}")


def _test_postgresql(host: str, port: int, database: str, username: str, password: str) -> TestResult:
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=host,
            port=port,
            database=database,
            user=username or "postgres",
            password=password or "",
            connect_timeout=10
        )
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        cursor.close()
        conn.close()
        return TestResult(
            True,
            f"Successfully connected to PostgreSQL. Server version: {version[0][:80]}...",
            {"server_version": version[0]}
        )
    except ImportError:
        return TestResult(False, "psycopg2 library not installed. Cannot test PostgreSQL connection.")
    except Exception as e:
        error_msg = str(e)
        if "connection refused" in error_msg.lower():
            return TestResult(False, f"Cannot connect to {host}:{port}. Is the server running?")
        if "authentication failed" in error_msg.lower():
            return TestResult(False, "Authentication failed. Please check username and password.")
        if "database" in error_msg.lower() and "does not exist" in error_msg.lower():
            return TestResult(False, f"Database '{database}' does not exist.")
        return TestResult(False, f"Connection failed: {error_msg}")


def _test_mysql(host: str, port: int, database: str, username: str, password: str) -> TestResult:
    try:
        import pymysql
        conn = pymysql.connect(
            host=host,
            port=port,
            database=database,
            user=username or "root",
            password=password or "",
            connect_timeout=10
        )
        cursor = conn.cursor()
        cursor.execute("SELECT VERSION();")
        version = cursor.fetchone()
        cursor.close()
        conn.close()
        return TestResult(
            True,
            f"Successfully connected to MySQL. Server version: {version[0]}",
            {"server_version": version[0]}
        )
    except ImportError:
        return TestResult(False, "pymysql library not installed. Cannot test MySQL connection.")
    except Exception as e:
        error_msg = str(e)
        if "connection refused" in error_msg.lower():
            return TestResult(False, f"Cannot connect to {host}:{port}. Is the server running?")
        if "access denied" in error_msg.lower():
            return TestResult(False, "Authentication failed. Please check username and password.")
        if "unknown database" in error_msg.lower():
            return TestResult(False, f"Database '{database}' does not exist.")
        return TestResult(False, f"Connection failed: {error_msg}")


def _test_opengauss(host: str, port: int, database: str, username: str, password: str) -> TestResult:
    # OpenGauss uses psycopg2 as well
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=host,
            port=port,
            database=database,
            user=username or "postgres",
            password=password or "",
            connect_timeout=10
        )
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        cursor.close()
        conn.close()
        return TestResult(
            True,
            f"Successfully connected to OpenGauss. Server version: {version[0][:80]}...",
            {"server_version": version[0]}
        )
    except ImportError:
        return TestResult(False, "psycopg2 library not installed. Cannot test OpenGauss connection.")
    except Exception as e:
        return TestResult(False, f"Connection failed: {str(e)}")


def _test_dws(host: str, port: int, database: str, username: str, password: str) -> TestResult:
    # DWS (Huawei GaussDB) also uses psycopg2
    return _test_opengauss(host, port, database, username, password)


def _test_oracle(host: str, port: int, database: str, username: str, password: str) -> TestResult:
    try:
        import cx_Oracle
        dsn = cx_Oracle.makedsn(host, port, service_name=database)
        conn = cx_Oracle.connect(username or "system", password or "", dsn)
        version = conn.version
        conn.close()
        return TestResult(
            True,
            f"Successfully connected to Oracle. Server version: {version}",
            {"server_version": version}
        )
    except ImportError:
        return TestResult(False, "cx_Oracle library not installed. Cannot test Oracle connection.")
    except Exception as e:
        error_msg = str(e)
        if "connection" in error_msg.lower():
            return TestResult(False, f"Cannot connect to Oracle: {error_msg}")
        return TestResult(False, f"Connection failed: {error_msg}")


def test_knowledge_base_connection(config: Dict[str, Any]) -> TestResult:
    """
    Test knowledge base connection by checking if the path or URL is accessible.
    """
    kb_type = config.get("type", "local").lower()
    path = config.get("path", "").strip()
    index_url = config.get("index_url", "").strip()
    
    if kb_type == "local":
        if not path:
            return TestResult(False, "Local path is required for local knowledge base.")
        
        path_obj = Path(path)
        if path_obj.exists():
            if path_obj.is_dir():
                # Check if directory is readable
                try:
                    files = list(path_obj.iterdir())
                    return TestResult(
                        True,
                        f"Directory is accessible. Contains {len(files)} items.",
                        {"item_count": len(files)}
                    )
                except PermissionError:
                    return TestResult(False, "Directory exists but not readable. Check permissions.")
            else:
                # It's a file
                if path_obj.is_file() and os.access(path_obj, os.R_OK):
                    size = path_obj.stat().st_size
                    return TestResult(
                        True,
                        f"File is accessible. Size: {size} bytes.",
                        {"size": size}
                    )
                else:
                    return TestResult(False, "File exists but not readable.")
        else:
            # Path doesn't exist, check if parent is writable
            parent = path_obj.parent
            if parent.exists() and os.access(parent, os.W_OK):
                return TestResult(
                    True,
                    f"Path is valid (will be created on first use): {path}",
                    {"will_create": True}
                )
            return TestResult(False, f"Path does not exist and cannot be created: {path}")
    
    elif kb_type == "remote":
        if not index_url:
            return TestResult(False, "Index URL is required for remote knowledge base.")
        
        # Test if the URL is reachable
        try:
            import requests
            response = requests.get(index_url, timeout=10)
            if response.status_code == 200:
                return TestResult(
                    True,
                    f"Successfully connected to remote knowledge base. Status: {response.status_code}",
                    {"status_code": response.status_code}
                )
            elif response.status_code == 401 or response.status_code == 403:
                return TestResult(False, "Authentication required. Please check credentials.")
            else:
                return TestResult(
                    False,
                    f"Server returned status {response.status_code}"
                )
        except ImportError:
            return TestResult(False, "requests library not installed. Cannot test remote knowledge base.")
        except Exception as e:
            error_msg = str(e)
            if "connection" in error_msg.lower():
                return TestResult(False, f"Cannot connect to {index_url}")
            return TestResult(False, f"Connection failed: {error_msg}")
    
    else:
        return TestResult(False, f"Unsupported knowledge base type: {kb_type}")
