import inspect

from fastapi.params import Depends

from backend.routers import admin_documents
from backend.security.auth import require_admin


def _depends_on(function, dependency) -> bool:
    for parameter in inspect.signature(function).parameters.values():
        default = parameter.default
        if isinstance(default, Depends) and default.dependency is dependency:
            return True
    return False


def test_admin_document_routes_require_admin():
    routes = [
        admin_documents.get_parse_meta,
        admin_documents.batch_reindex,
    ]

    for route in routes:
        assert _depends_on(route, require_admin)
