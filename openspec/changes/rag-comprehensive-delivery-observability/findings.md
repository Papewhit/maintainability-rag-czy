---
document_type: finding_ledger
change: rag-comprehensive-delivery-observability
last_verified_commit: 961eb0f29677a23d2a0bcf5ff4da720ab701fa79
last_verified_date: 2026-07-21
---

# Change Findings

## RAG-CDO-F001

- Kind: behavior_defect
- Primary scope: rag.fallback.level3
- Evidence status: confirmed
- Observation: Independent spec-loyalty review found that the first implementation described Level 3 delivery as typed but exposed it internally and through the public API as unconstrained `dict[str, Any]` / `Dict[str, Any]`. The wire schema accepted incomplete contracts and unknown modes.
- Inference: Without an enumerated mode and required nested fields, persisted or non-stream payloads could lose the promised delivery/evidence contract and an unknown mode could reach the wrong renderer branch.
- Decision: Define internal `Level3Mode`, evidence-ref, dimension-evidence, and delivery `TypedDict` contracts; define strict nested Pydantic wire models with required fields, enumerated modes, and forbidden extras; use the typed contract through trace, delivery, and renderer boundaries.
- Residual risk: none
- Evidence: Independent spec-loyalty review; `backend/rag/types.py`; `backend/contracts/schemas.py`; `backend/rag/level3_answer.py`; `backend/chat/rag_execution.py`; `tests/unit/backend/contracts/test_rag_trace_schema.py` incomplete/unknown contract rejection tests.
- Disposition: closed_in_place
- Disposition target: null
- Resolution evidence: The strict internal/public types are implemented and the focused backend suite passes `56 passed`; invalid and incomplete Level 3 payloads now fail Pydantic validation.
