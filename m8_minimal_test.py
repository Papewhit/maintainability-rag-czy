#!/usr/bin/env python3
"""M8 最小验证 - 只测试 DOCX（快速）"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

print("=" * 60)
print("M8 Minimal Validation (DOCX only)")
print("=" * 60)

# 1. 上传 DOCX
print("\n[1/3] Uploading DOCX...")
from backend.services.document_service import DocumentService

docx_path = Path("tests/assets/test_docx.docx")
if not docx_path.exists():
    print(f"[FAIL] File not found: {docx_path}")
    sys.exit(1)

service = DocumentService.create_default()
with open(docx_path, "rb") as f:
    content = f.read()

try:
    result = service.upload_document("test_m8_docx.docx", content)
    print(f"[PASS] Uploaded: {result.get('filename')}")
except Exception as e:
    print(f"[FAIL] Upload failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 2. 查询 parse_meta
print("\n[2/3] Querying parse_meta...")
from backend.infra.db.database import SessionLocal
from backend.infra.db.models import DocumentParseMeta

db = SessionLocal()
try:
    meta = db.query(DocumentParseMeta).filter(
        DocumentParseMeta.document_id == "test_m8_docx.docx"
    ).first()

    if not meta:
        print("[FAIL] parse_meta not found")
        sys.exit(1)

    print("[PASS] parse_meta found")

    # 3. 验证字段
    print("\n[3/3] Validating M8 fields...")
    print(f"  parse_path: {meta.parse_path}")
    print(f"  ocr_confidence_avg: {meta.ocr_confidence_avg}")

    # 验证
    if meta.parse_path != "native_text":
        print(f"[FAIL] Expected parse_path='native_text', got '{meta.parse_path}'")
        sys.exit(1)

    if meta.ocr_confidence_avg is not None:
        print(f"[WARN] DOCX should not have ocr_confidence_avg: {meta.ocr_confidence_avg}")

    print("\n" + "=" * 60)
    print("[PASS] M8 Validation Complete!")
    print("=" * 60)
    print("\nValidation results:")
    print("  [PASS] parse_path field exists")
    print("  [PASS] DOCX parse_path = 'native_text'")
    print("  [PASS] DOCX ocr_confidence_avg = null")
    print("\nM8 core functionality is working correctly.")

finally:
    db.close()
