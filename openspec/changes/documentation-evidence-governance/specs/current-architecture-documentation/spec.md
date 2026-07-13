## ADDED Requirements

### Requirement: Single current-system overview
`docs/ARCHITECTURE.md` SHALL be the only document that presents a complete current-system architecture overview. Other architecture snapshots SHALL declare historical or superseded status and link to it.

#### Scenario: Reader opens competing architecture document
- **WHEN** a reader opens `docs/knowledge-and-architecture.md` or the generated preprocessing insights document
- **THEN** a prominent status notice identifies it as superseded or historical and directs the reader to `docs/ARCHITECTURE.md`

### Requirement: Verification and status boundary
The architecture overview SHALL identify its verified commit, verification date, evidence boundary, current facts, implemented-but-default-disabled behavior, and planned behavior. Planned `rag-intent-routing` and `rag-multilevel-fallback` behavior SHALL NOT appear in the active flow.

#### Scenario: Runtime feature status is documented
- **WHEN** the architecture status matrix lists step-chain checking, confidence gating, score fusion, auto-merge, structure reranking, or candidate strategy
- **THEN** its default state matches `backend/rag/runtime_config.py` at the documented verification commit

### Requirement: Ingestion architecture coverage
The architecture overview SHALL document the active Adapter Registry to DeepDoc/Excel Parse Adapter to Structure Normalizer to Maintainability Chunker to terminology scan to parent/leaf split to ParentChunkStore/Milvus flow and its failure boundary.

#### Scenario: Maintainer traces a document upload
- **WHEN** a maintainer follows the ingestion diagram
- **THEN** every named implementation path exists and the diagram shows parents stored outside Milvus and leaves indexed in Milvus

### Requirement: Chunk and storage contract coverage
The architecture overview SHALL document chunk level, role, parent/root identifiers, list metadata, entity metadata, parent extras, Milvus wire encoding, and runtime decoding boundaries, including responsibilities of PostgreSQL, Redis, Milvus, and BM25 state.

#### Scenario: Entity metadata crosses Milvus boundary
- **WHEN** architecture describes `entity_types`
- **THEN** it distinguishes runtime `list[str]` from compact JSON-string Milvus wire representation and documents malformed-data degradation

### Requirement: Retrieval and postprocess coverage
The architecture overview SHALL document dense and sparse embeddings, BM25 state, Milvus candidate retrieval, standard and layered candidate strategies, and the fixed shared postprocess order `rerank -> auto_merge -> step_chain_check -> structure_rerank -> top_k_truncate -> confidence_gate`.

#### Scenario: A postprocess stage fails
- **WHEN** any shared postprocess stage raises a recoverable error
- **THEN** the documented contract states that the previous stage output continues to later safe stages and trace records the stage error, skip/error state, and timing

### Requirement: Trace evaluation and navigation coverage
The architecture overview SHALL document trace contracts, evaluation boundaries, known limitations, ADRs, OpenSpec current/planned artifacts, validation evidence entry points, and runnable architecture verification commands.

#### Scenario: Reader verifies architecture claims
- **WHEN** a reader follows the architecture verification section
- **THEN** the listed commands validate code paths, documentation governance, relevant unit tests, and OpenSpec status without requiring undocumented steps
