import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "pyproject.toml").is_file())

import backend.infra.vector_store.milvus_client as milvus_client  # noqa: E402
from backend.infra.vector_store.milvus_client import MilvusManager  # noqa: E402


class FlakyMilvusClient:
    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.closed = False

    def query(self, **kwargs):
        if self.should_fail:
            raise RuntimeError("Cannot invoke RPC on closed channel!")
        return [{"filename": "manual.pdf", "file_type": "PDF"}]

    def close(self):
        self.closed = True


class MilvusManagerReconnectTests(unittest.TestCase):
    def test_query_reconnects_once_when_rpc_channel_is_closed(self):
        clients = [FlakyMilvusClient(should_fail=True), FlakyMilvusClient()]

        def client_factory(uri):
            self.assertEqual(uri, "http://127.0.0.1:19530")
            return clients.pop(0)

        with patch("backend.infra.vector_store.milvus_client.MilvusClient", side_effect=client_factory) as factory:
            manager = MilvusManager()
            manager.host = "127.0.0.1"
            manager.port = "19530"
            manager.uri = "http://127.0.0.1:19530"

            result = manager.query(output_fields=["filename", "file_type"], limit=5)

        self.assertEqual(result, [{"filename": "manual.pdf", "file_type": "PDF"}])
        self.assertEqual(factory.call_count, 2)

    def test_query_retries_multiple_closed_channel_failures(self):
        clients = [
            FlakyMilvusClient(should_fail=True),
            FlakyMilvusClient(should_fail=True),
            FlakyMilvusClient(),
        ]

        def client_factory(uri):
            self.assertEqual(uri, "http://127.0.0.1:19530")
            return clients.pop(0)

        with patch("backend.infra.vector_store.milvus_client.MilvusClient", side_effect=client_factory) as factory:
            manager = MilvusManager()
            manager.host = "127.0.0.1"
            manager.port = "19530"
            manager.uri = "http://127.0.0.1:19530"

            result = manager.query(output_fields=["filename", "file_type"], limit=5)

        self.assertEqual(result, [{"filename": "manual.pdf", "file_type": "PDF"}])
        self.assertEqual(factory.call_count, 3)


class MilvusEntityMetadataTests(unittest.TestCase):
    def setUp(self):
        self.manager = MilvusManager()

    def test_hybrid_retrieve_decodes_entity_metadata(self):
        hit = {
            "id": 1,
            "chunk_id": "c1",
            "text": "pump",
            "entity_types": '["component"]',
            "term_match_count": 2,
            "distance": 0.8,
        }
        with (
            patch.object(milvus_client, "_ensure_pymilvus"),
            patch.object(milvus_client, "AnnSearchRequest", side_effect=lambda **kwargs: kwargs),
            patch.object(milvus_client, "RRFRanker", side_effect=lambda **kwargs: kwargs),
            patch.object(self.manager, "_call_with_reconnect", return_value=[[hit]]),
        ):
            docs = self.manager.hybrid_retrieve([0.1], {1: 0.5})

        self.assertEqual(docs[0]["entity_types"], ["component"])
        self.assertEqual(docs[0]["term_match_count"], 2)

    def test_split_retrieve_decodes_entity_metadata(self):
        dense_hit = {
            "id": 1,
            "entity": {
                "chunk_id": "c1",
                "text": "pump",
                "entity_types": '["component"]',
                "term_match_count": 2,
            },
            "distance": 0.8,
        }
        sparse_hit = {
            "id": 1,
            "entity": {
                "chunk_id": "c1",
                "text": "pump",
                "entity_types": ["component"],
                "term_match_count": 2,
            },
            "distance": 0.6,
        }
        with patch.object(
            self.manager,
            "_call_with_reconnect",
            side_effect=[[[dense_hit]], [[sparse_hit]]],
        ):
            docs = self.manager.split_retrieve([0.1], {1: 0.5})

        self.assertEqual(docs[0]["entity_types"], ["component"])
        self.assertEqual(docs[0]["term_match_count"], 2)

    def test_dense_retrieve_decodes_entity_metadata(self):
        hit = {
            "id": 1,
            "entity": {
                "chunk_id": "c1",
                "text": "pump",
                "entity_types": '["component"]',
                "term_match_count": 2,
            },
            "distance": 0.8,
        }
        with patch.object(self.manager, "_call_with_reconnect", return_value=[[hit]]):
            docs = self.manager.dense_retrieve([0.1])

        self.assertEqual(docs[0]["entity_types"], ["component"])
        self.assertEqual(docs[0]["term_match_count"], 2)


if __name__ == "__main__":
    unittest.main()

