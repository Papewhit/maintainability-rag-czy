from __future__ import annotations

import pytest

from backend.evaluation.answer_eval import citation_evidence_validity


pytestmark = pytest.mark.unit


def test_citation_evidence_validity_checks_citations_against_retrieved_docs():
    docs = [
        {"filename": "泵站维护手册.pdf", "page_number": 3},
        {"filename": "检修规程.docx", "page_start": 8},
    ]

    result = citation_evidence_validity(
        "启动前检查见 [泵站维护手册.pdf p.3]，另一项见 [检修规程 p.99]。",
        docs,
    )

    assert result["citation_validity"] == 0.5
    assert result["citation_count"] == 2
    assert result["valid_citation_count"] == 1


def test_citation_evidence_validity_is_zero_when_answer_has_no_citations():
    result = citation_evidence_validity("没有引用的回答", [{"filename": "手册.pdf", "page_number": 1}])

    assert result == {
        "citation_validity": 0.0,
        "citation_count": 0,
        "valid_citation_count": 0,
    }
