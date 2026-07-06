import inspect

from fastapi.params import Depends

from backend.infra.db import database
from backend.routers import admin_documents, admin_terminology


def _dependency_for(function, parameter_name: str):
    default = inspect.signature(function).parameters[parameter_name].default
    assert isinstance(default, Depends)
    return default.dependency


def test_admin_terminology_routes_use_shared_db_dependency():
    assert hasattr(database, "get_db")
    routes = [
        admin_terminology.list_entries,
        admin_terminology.get_entry,
        admin_terminology.create_entry,
        admin_terminology.update_entry,
        admin_terminology.delete_entry,
        admin_terminology.bulk_import,
    ]

    for route in routes:
        assert _dependency_for(route, "db") is database.get_db


def test_admin_documents_parse_meta_uses_shared_db_dependency():
    assert hasattr(database, "get_db")
    assert _dependency_for(admin_documents.get_parse_meta, "db") is database.get_db
