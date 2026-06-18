"""Utility functions extracted from swxy/ragflow DeepDoc internals.

All functions that DeepDoc vision/parser modules imported from
``service.core.rag.nlp``, ``service.core.rag.utils``, and
``service.core.api.utils.file_utils`` are provided here so that
the copied DeepDoc code has zero external swxy dependencies.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Model directory resolution
# ---------------------------------------------------------------------------

_PROJECT_BASE: str | None = None


def get_model_dir(*subdirs: str) -> str:
    """Return the DeepDoc model directory.

    Resolution order:
    1. ``DEEPDOC_MODEL_DIR`` env var (absolute path).
    2. ``models/`` directory next to this file (for vendored models).
    3. HuggingFace cache (``HF_HOME`` / ``~/.cache/huggingface``).

    When *subdirs* are given, they are joined onto the base directory
    (this matches the ragflow ``get_project_base_directory(*args)`` API).
    """
    global _PROJECT_BASE
    if _PROJECT_BASE is None:
        env_dir = os.environ.get("DEEPDOC_MODEL_DIR")
        if env_dir:
            _PROJECT_BASE = env_dir
        else:
            # Default: models/ directory next to this utils file.
            _PROJECT_BASE = str(Path(__file__).resolve().parent / "models")
    if subdirs:
        return os.path.join(_PROJECT_BASE, *subdirs)
    return _PROJECT_BASE


# ---------------------------------------------------------------------------
# Encoding detection (used by excel_parser, html_parser, json_parser, utils)
# ---------------------------------------------------------------------------

_ALL_CODECS = [
    "utf-8", "gb2312", "gbk", "utf_16", "ascii", "big5", "big5hkscs",
    "cp037", "cp437", "cp500", "cp850", "cp852", "cp855", "cp857",
    "cp860", "cp861", "cp862", "cp863", "cp864", "cp865", "cp866", "cp869",
    "cp874", "cp875", "cp932", "cp949", "cp950", "cp1006", "cp1026", "cp1140",
    "cp1250", "cp1251", "cp1252", "cp1253", "cp1254", "cp1255", "cp1256",
    "cp1257", "cp1258", "euc_jp", "euc_jis_2004", "euc_jisx0213", "euc_kr",
    "gb18030", "hz", "iso2022_jp", "iso2022_jp_1", "iso2022_jp_2",
    "iso2022_jp_2004", "iso2022_jp_3", "iso2022_jp_ext", "iso2022_kr",
    "latin_1", "iso8859_2", "iso8859_3", "iso8859_4", "iso8859_5",
    "iso8859_6", "iso8859_7", "iso8859_8", "iso8859_9", "iso8859_10",
    "iso8859_11", "iso8859_13", "iso8859_14", "iso8859_15", "iso8859_16",
    "johab", "koi8_r", "koi8_t", "koi8_u", "kz1048", "mac_cyrillic",
    "mac_greek", "mac_iceland", "mac_latin2", "mac_roman", "mac_turkish",
    "ptcp154", "shift_jis", "shift_jis_2004", "shift_jisx0213",
    "utf_32", "utf_32_be", "utf_32_le", "utf_16_be", "utf_16_le", "utf_7",
    "windows-1250", "windows-1251", "windows-1252", "windows-1253",
    "windows-1254", "windows-1255", "windows-1256", "windows-1257",
    "windows-1258", "latin-2",
]


def find_codec(blob: bytes) -> str:
    """Detect the text encoding of *blob*.

    Tries ``chardet`` first, then brute-forces a list of common codecs.
    Falls back to ``"utf-8"`` if nothing matches.
    """
    try:
        import chardet
        detected = chardet.detect(blob[:1024])
        if detected.get("confidence", 0) > 0.5:
            enc = detected.get("encoding")
            if enc:
                return enc
    except ImportError:
        pass

    for c in _ALL_CODECS:
        try:
            blob[:1024].decode(c)
            return c
        except (UnicodeDecodeError, LookupError):
            pass
        try:
            blob.decode(c)
            return c
        except (UnicodeDecodeError, LookupError):
            pass

    return "utf-8"


# ---------------------------------------------------------------------------
# Language detection (used by pdf_parser for English vs Chinese path)
# ---------------------------------------------------------------------------


def is_english(texts: list[str]) -> bool:
    """Return True if >80% of *texts* look like English."""
    if not texts:
        return False
    eng = 0
    for t in texts:
        if re.match(r"[ `a-zA-Z.,':;/\"?<>!\(\)-]", t.strip()):
            eng += 1
    return eng / len(texts) > 0.8


# ---------------------------------------------------------------------------
# Token counting (used by txt_parser and nlp module)
# ---------------------------------------------------------------------------


def num_tokens_from_string(string: str) -> int:
    """Return the approximate token count using tiktoken cl100k_base.

    If tiktoken is not installed, falls back to ``len(string) // 2``
    (rough approximation for mixed Chinese / English text).
    """
    try:
        import tiktoken
        encoder = tiktoken.get_encoding("cl100k_base")
        return len(encoder.encode(string))
    except Exception:
        # Fallback: rough heuristic.
        return max(1, len(string) // 2)
