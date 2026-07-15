from pathlib import Path

from backend.evaluation.comprehensive_routing import routing_source_fingerprint
from scripts.source_fingerprint import canonical_source_sha256


def test_canonical_source_fingerprint_is_line_ending_independent(tmp_path: Path):
    source = tmp_path / "sample.py"
    source.write_bytes(b"first\nsecond\n")
    lf_hash = canonical_source_sha256(tmp_path, ["sample.py"])

    source.write_bytes(b"first\r\nsecond\r\n")
    crlf_hash = canonical_source_sha256(tmp_path, ["sample.py"])

    assert crlf_hash == lf_hash


def test_canonical_source_fingerprint_frames_paths_and_content(tmp_path: Path):
    (tmp_path / "a").write_bytes(b"bc")
    (tmp_path / "ab").write_bytes(b"c")

    assert canonical_source_sha256(tmp_path, ["a"]) != canonical_source_sha256(tmp_path, ["ab"])


def test_intent_routing_fingerprint_covers_public_trace_schema():
    repo_root = Path(__file__).resolve().parents[4]

    fingerprint = routing_source_fingerprint(repo_root)

    assert "backend/contracts/schemas.py" in fingerprint["source_files"]
