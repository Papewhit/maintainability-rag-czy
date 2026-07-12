import unittest


from backend.rag.trace import (
    RAG_CONTEXT_FORMAT_VERSION,
    TRACE_SIGNATURE_VERSION,
    append_stage_error,
    build_initial_rag_trace,
    build_retrieval_meta,
    golden_trace_signature,
    mark_context_delivery,
    merge_expanded_rag_trace,
    trace_text_hash,
)


class RagTraceTests(unittest.TestCase):
    def test_trace_text_hash_normalizes_whitespace(self):
        self.assertEqual(trace_text_hash("a\r\n b"), trace_text_hash("a b"))

    def test_golden_trace_signature_captures_stable_ids(self):
        trace = {
            "retrieval_mode": "hybrid",
            "fallback_required": False,
            "candidate_count_before_rerank": 1,
            "rerank_input_count": 1,
            "candidates_before_rerank": [
                {"chunk_id": "c1", "retrieval_text": "heading\nbody", "filename": "m.pdf", "page_number": 2}
            ],
            "candidates_after_rerank": [{"chunk_id": "c1"}],
            "candidates_after_structure_rerank": [{"chunk_id": "c1", "filename": "m.pdf", "page_number": 2}],
        }

        signature = golden_trace_signature("q1", "GS3", trace)

        self.assertEqual(signature["signature_version"], TRACE_SIGNATURE_VERSION)
        self.assertEqual(signature["candidate_ids_before_rerank"], ["c1"])
        self.assertEqual(signature["final_top5_file_pages"][0]["filename"], "m.pdf")

    def test_retrieval_trace_builders_keep_standard_mode_contract(self):
        meta = build_retrieval_meta(
            {
                "retrieval_mode": "hybrid",
                "timings": {"total_retrieve_ms": 12.0},
                "stage_errors": [],
                "fallback_required": False,
                "pipeline_stage_model": "rag-l0-l3-v1",
                "candidate_strategy_requested": "layered",
                "candidate_strategy_effective": "layered",
                "candidate_strategy_version": "candidate-strategy-v2",
                "candidate_strategy_detail": "layered_split",
                "rerank_contract": "shared_rerank",
                "rerank_contract_version": "shared-rerank-v2",
                "rerank_execution_mode": "executed",
                "rerank_candidate_pool_size": 20,
                "candidate_count_before_rerank": 30,
                "candidate_count_after_rerank": 20,
                "candidate_count_after_structure_rerank": 18,
                "final_top_k_count": 5,
                "term_matches": [{"entity_type": "component", "canonical": "pump"}],
                "query_entities": [{"type": "component", "value": "pump"}],
                "auto_merge_skipped": True,
                "auto_merge_error": "recovered",
                "step_chain_check_enabled": True,
                "step_chain_repaired_groups": ["g1"],
                "step_chain_completion_count": 1,
                "entity_metadata_score_applied": True,
                "entity_type_coverage": 1.0,
                "entity_match_density": 0.6,
                "postprocess_contract": "shared_retrieval_postprocess",
                "postprocess_contract_version": "shared-postprocess-v1",
            }
        )

        self.assertEqual(meta["execution_mode"], "STANDARD")
        self.assertFalse(meta["deep_executed"])
        self.assertFalse(meta["plan_applied"])

        trace = build_initial_rag_trace(
            query="q",
            docs=[{"chunk_id": "c1", "text": "body"}],
            context="body",
            retrieve_meta=meta,
            context_files=["manual.pdf"],
            attached_docs=[{"chunk_id": "a1"}],
            attached_meta={"attached_context_count": 1},
        )

        self.assertEqual(trace["rerank_candidate_pool_size"], 20)
        self.assertEqual(trace["candidate_count_before_rerank"], 30)
        self.assertEqual(trace["final_top_k_count"], 5)
        self.assertEqual(trace["term_matches"][0]["canonical"], "pump")
        self.assertEqual(trace["query_entities"][0]["type"], "component")
        self.assertEqual(trace["step_chain_repaired_groups"], ["g1"])
        self.assertTrue(trace["auto_merge_skipped"])
        self.assertEqual(trace["auto_merge_error"], "recovered")
        self.assertTrue(trace["entity_metadata_score_applied"])
        self.assertEqual(trace["entity_type_coverage"], 1.0)
        append_stage_error(trace, "rerank", "boom", "ranked_candidates")
        merge_expanded_rag_trace(
            trace,
            {
                "expanded_query": "expanded q",
                "retrieved_chunks": [],
                "expanded_retrieved_chunks": [],
                "retrieval_stage": "expanded",
            },
            timings={"expanded_retrieve_ms": 3.0},
            stage_errors=[{"stage": "hyde_retrieve", "error": "late", "fallback_to": "initial_retrieval"}],
        )

        self.assertEqual(trace["retrieval_stage"], "expanded")
        self.assertEqual(trace["attached_context_count"], 1)
        self.assertEqual(trace["candidate_strategy_requested"], "layered")
        self.assertEqual(trace["candidate_strategy_effective"], "layered")
        self.assertEqual(trace["candidate_strategy_detail"], "layered_split")
        self.assertEqual(trace["rerank_contract"], "shared_rerank")
        self.assertEqual(trace["rerank_execution_mode"], "executed")
        self.assertEqual(trace["timings"]["expanded_retrieve_ms"], 3.0)
        self.assertEqual(trace["stage_errors"][0]["stage"], "rerank")
        self.assertEqual(trace["stage_errors"][0]["fallback_to"], "ranked_candidates")
        self.assertEqual(trace["stage_errors"][1]["stage"], "hyde_retrieve")

    def test_mark_context_delivery_records_shared_boundary_fields(self):
        trace = {"retrieval_mode": "hybrid", "context_chars": 0}
        docs = [{"chunk_id": "c1"}, {"chunk_id": "c2"}]

        marked = mark_context_delivery(
            trace,
            delivery_mode="tool_response",
            context="retrieved context",
            docs=docs,
        )

        self.assertIsNot(marked, trace)
        self.assertEqual(marked["context_delivery_mode"], "tool_response")
        self.assertEqual(marked["context_format_version"], RAG_CONTEXT_FORMAT_VERSION)
        self.assertEqual(marked["context_chars"], len("retrieved context"))
        self.assertEqual(marked["retrieved_chunk_count"], 2)
        self.assertEqual(marked["final_context_chunk_count"], 2)


if __name__ == "__main__":
    unittest.main()
