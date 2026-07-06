import os
import logging
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE_PATH = BASE_DIR / "data" / "ragtenance.db"
DEFAULT_DOCKER_DATABASE_URL = "postgresql+psycopg2://postgres:postgres@127.0.0.1:5433/langchain_app"
_PRIMARY_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    DEFAULT_DOCKER_DATABASE_URL,
)
DATABASE_URL = _PRIMARY_DATABASE_URL
FALLBACK_DATABASE_URL = os.getenv(
    "FALLBACK_DATABASE_URL",
    f"sqlite:///{DEFAULT_SQLITE_PATH.as_posix()}",
)
ALLOW_DATABASE_FALLBACK = os.getenv("ALLOW_DATABASE_FALLBACK", "1").strip().lower() not in {"0", "false", "no"}
DATABASE_FALLBACK_USED = False
DATABASE_FALLBACK_REASON: str | None = None

class Base(DeclarativeBase):
    pass


def _build_engine(database_url: str):
    engine_options = {
        "pool_pre_ping": True,
        "pool_size": int(os.getenv("DB_POOL_SIZE", "5")),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "10")),
        "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT_SECONDS", "30")),
        "pool_recycle": int(os.getenv("DB_POOL_RECYCLE_SECONDS", "1800")),
    }

    if database_url.startswith("sqlite"):
        for key in ("pool_size", "max_overflow", "pool_timeout", "pool_recycle"):
            engine_options.pop(key, None)

    return create_engine(database_url, **engine_options)


def _ensure_sqlite_parent_dir(database_url: str) -> None:
    parsed = make_url(database_url)
    if parsed.drivername != "sqlite" or not parsed.database or parsed.database == ":memory:":
        return
    Path(parsed.database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


def _configure_engine(database_url: str, fallback_reason: str | None = None) -> None:
    global DATABASE_URL, engine, DATABASE_FALLBACK_USED, DATABASE_FALLBACK_REASON
    DATABASE_URL = database_url
    DATABASE_FALLBACK_USED = database_url != _PRIMARY_DATABASE_URL
    DATABASE_FALLBACK_REASON = fallback_reason if DATABASE_FALLBACK_USED else None
    _ensure_sqlite_parent_dir(database_url)
    engine = _build_engine(database_url)
    SessionLocal.configure(bind=engine)


engine = _build_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_runtime_indexes() -> None:
    statements: list[str] = []
    if engine.dialect.name == "postgresql":
        statements.extend(
            [
                "ALTER TABLE parent_chunks ADD COLUMN IF NOT EXISTS index_profile VARCHAR(120) NOT NULL DEFAULT 'legacy'",
                "ALTER TABLE parent_chunks ADD COLUMN IF NOT EXISTS term_matches JSON",
                "ALTER TABLE parent_chunks ADD COLUMN IF NOT EXISTS protected_tokens JSON",
                "ALTER TABLE parent_chunks ADD COLUMN IF NOT EXISTS parent_extras JSON",
                "ALTER TABLE document_parse_meta ADD COLUMN IF NOT EXISTS parse_path VARCHAR(20)",
                "CREATE INDEX IF NOT EXISTS ix_chat_sessions_user_updated ON chat_sessions (user_id, updated_at DESC)",
                "CREATE INDEX IF NOT EXISTS ix_chat_messages_session_id_order ON chat_messages (session_ref_id, id)",
                "CREATE INDEX IF NOT EXISTS ix_parent_chunks_filename_chunk ON parent_chunks (filename, chunk_id)",
                "CREATE INDEX IF NOT EXISTS ix_parent_chunks_profile_filename ON parent_chunks (index_profile, filename)",
                "CREATE TABLE IF NOT EXISTS document_parse_meta (document_id VARCHAR(256) PRIMARY KEY, parse_engine VARCHAR(50) NOT NULL DEFAULT '', parse_engine_version VARCHAR(20) NOT NULL DEFAULT '', parse_duration_ms INTEGER NOT NULL DEFAULT 0, total_pages INTEGER NOT NULL DEFAULT 0, watermark_filter_ratio FLOAT, ocr_confidence_avg FLOAT, parse_path VARCHAR(20), parse_warnings JSON, hierarchy_validation_warnings JSON, created_at TIMESTAMP NOT NULL DEFAULT NOW())",
            ]
        )
    elif engine.dialect.name == "sqlite":
        with engine.begin() as connection:
            columns = {
                row[1]
                for row in connection.execute(text("PRAGMA table_info(parent_chunks)")).fetchall()
            }
            if "index_profile" not in columns:
                connection.execute(
                    text("ALTER TABLE parent_chunks ADD COLUMN index_profile VARCHAR(120) NOT NULL DEFAULT 'legacy'")
                )
            if "parent_extras" not in columns:
                connection.execute(
                    text("ALTER TABLE parent_chunks ADD COLUMN parent_extras JSON")
                )
            if "term_matches" not in columns:
                connection.execute(
                    text("ALTER TABLE parent_chunks ADD COLUMN term_matches JSON")
                )
            if "protected_tokens" not in columns:
                connection.execute(
                    text("ALTER TABLE parent_chunks ADD COLUMN protected_tokens JSON")
                )
            parse_meta_columns = {
                row[1]
                for row in connection.execute(text("PRAGMA table_info(document_parse_meta)")).fetchall()
            }
            if "parse_path" not in parse_meta_columns:
                connection.execute(
                    text("ALTER TABLE document_parse_meta ADD COLUMN parse_path VARCHAR(20)")
                )
        statements.extend(
            [
                "CREATE INDEX IF NOT EXISTS ix_parent_chunks_filename_chunk ON parent_chunks (filename, chunk_id)",
                "CREATE INDEX IF NOT EXISTS ix_parent_chunks_profile_filename ON parent_chunks (index_profile, filename)",
                "CREATE TABLE IF NOT EXISTS document_parse_meta (document_id VARCHAR(256) PRIMARY KEY, parse_engine VARCHAR(50) NOT NULL DEFAULT '', parse_engine_version VARCHAR(20) NOT NULL DEFAULT '', parse_duration_ms INTEGER NOT NULL DEFAULT 0, total_pages INTEGER NOT NULL DEFAULT 0, watermark_filter_ratio FLOAT, ocr_confidence_avg FLOAT, parse_path VARCHAR(20), parse_warnings JSON, hierarchy_validation_warnings JSON, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)",
            ]
        )
    else:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def init_db() -> None:
    global DATABASE_FALLBACK_USED, DATABASE_FALLBACK_REASON
    # Delayed import to avoid circular dependency.
    from backend.infra.db import models  # noqa: F401

    try:
        Base.metadata.create_all(bind=engine)
        _ensure_runtime_indexes()
        DATABASE_FALLBACK_USED = DATABASE_URL != _PRIMARY_DATABASE_URL
        if not DATABASE_FALLBACK_USED:
            DATABASE_FALLBACK_REASON = None
    except OperationalError as exc:
        primary_error = str(exc).splitlines()[0] if str(exc) else "primary database unavailable"
        should_fallback = (
            ALLOW_DATABASE_FALLBACK
            and not DATABASE_URL.startswith("sqlite")
            and FALLBACK_DATABASE_URL
            and FALLBACK_DATABASE_URL != DATABASE_URL
        )
        if not should_fallback:
            raise
        logger.warning(
            "Primary database unavailable; using fallback database %s",
            make_url(FALLBACK_DATABASE_URL).render_as_string(hide_password=True),
        )
        _configure_engine(FALLBACK_DATABASE_URL, fallback_reason=primary_error)
        Base.metadata.create_all(bind=engine)
        _ensure_runtime_indexes()
