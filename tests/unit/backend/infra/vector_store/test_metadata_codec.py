import pytest

from backend.infra.vector_store.metadata_codec import decode_entity_types, encode_entity_types


def test_entity_types_codec_normalizes_list_and_json_string_equally():
    expected = ["component", "maintenance_action"]

    assert decode_entity_types(["component", "maintenance_action", "component", ""]) == expected
    assert decode_entity_types('["component", "maintenance_action", "component"]') == expected
    assert encode_entity_types(expected) == '["component","maintenance_action"]'


def test_entity_types_codec_safely_rejects_malformed_or_non_array_values():
    assert decode_entity_types("not-json") == []
    assert decode_entity_types('"component"') == []
    assert decode_entity_types({"type": "component"}) == []
    assert decode_entity_types(None) == []


def test_entity_types_encoder_enforces_milvus_varchar_budget():
    with pytest.raises(ValueError, match="exceeds 512 bytes"):
        encode_entity_types(["x" * 513])
