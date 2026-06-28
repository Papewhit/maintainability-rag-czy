"""Collection guards for optional local evaluation regression tooling."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _module_exists(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except ModuleNotFoundError:
        return False


def pytest_ignore_collect(collection_path: Path, config) -> bool:
    if collection_path.name != "test_rag_eval_regression.py":
        return False
    return not _module_exists("scripts.rag_eval.regression")
