from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend import api as api_module
from backend.infra.db.database import SessionLocal, init_db

BASE_DIR = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    _init_terminology()
    yield


def _init_terminology() -> None:
    """Load the terminology table into memory and configure jieba at startup."""
    import csv
    import logging

    logger = logging.getLogger(__name__)
    try:
        from backend.infra.db.models import TerminologyEntryModel
        from backend.rag.terminology.table import TerminologyTable, set_terminology_table
        from backend.rag.terminology.jieba_dict import get_terminology_surfaces, reload_jieba_with_terminology

        db = SessionLocal()
        try:
            # Auto-load seed data if table is empty
            count = db.query(TerminologyEntryModel).count()
            if count == 0:
                seed_path = BASE_DIR / "data" / "terminology_seed.csv"
                if seed_path.is_file():
                    _load_seed_csv(db, seed_path)
                    logger.info("Terminology seed data loaded from %s", seed_path)
                else:
                    logger.info("No seed file at %s; terminology table starts empty", seed_path)

            table = TerminologyTable.load_from_db(db)
            set_terminology_table(table)
            logger.info("Terminology table loaded: %d entries", table.entry_count())

            # Inject terminology into jieba so BM25 indexing protects compound terms
            if table.entry_count() > 0:
                surfaces = get_terminology_surfaces(table)
                reload_jieba_with_terminology(surfaces)
                logger.info("jieba userdict injected with %d terms", len(surfaces))
        finally:
            db.close()
    except Exception:
        logger.warning("Failed to load terminology table; terminology features disabled", exc_info=True)


def _load_seed_csv(db, seed_path: Path) -> None:
    """Load terminology entries from the seed CSV into the database."""
    import csv
    import logging

    logger = logging.getLogger(__name__)
    from backend.infra.db.models import TerminologyEntryModel

    with open(seed_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        count = 0
        for row in reader:
            canonical = (row.get("canonical") or "").strip()
            entity_type = (row.get("entity_type") or "").strip().lower()
            variants_raw = (row.get("variants") or "").strip()
            variants = [v.strip() for v in variants_raw.split("|") if v.strip()] if variants_raw else []
            description = (row.get("description") or "").strip() or None

            if not canonical or not entity_type:
                continue

            db.add(TerminologyEntryModel(
                canonical=canonical,
                entity_type=entity_type,
                variants=variants,
                description=description,
                metadata={},
            ))
            count += 1
        db.commit()
        logger.info("Loaded %d seed terminology entries", count)


def create_app() -> FastAPI:
    app = FastAPI(title="Ragtenance API", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def _no_cache(request, call_next):
        response = await call_next(request)
        path = request.url.path or ""
        if path == "/" or path.endswith((".html", ".js", ".css")):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    app.include_router(api_module.router)

    if FRONTEND_DIR.exists():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="static")

    return app


app = create_app()


__all__ = ["app", "create_app"]
