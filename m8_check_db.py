#!/usr/bin/env python3
"""M8 快速验证 - 检查 DB 中已有的 parse_meta"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from backend.infra.db.database import SessionLocal
from backend.infra.db.models import DocumentParseMeta


def check_parse_meta():
    """检查数据库中所有 parse_meta 记录"""
    print("=" * 60)
    print("M8 Parse Meta Validation")
    print("=" * 60)

    db = SessionLocal()
    try:
        # 查询所有 parse_meta
        all_meta = db.query(DocumentParseMeta).all()

        if not all_meta:
            print("\n[INFO] No parse_meta records found in database")
            print("[INFO] Please upload documents first to test M8 features")
            return 1

        print(f"\n[INFO] Found {len(all_meta)} parse_meta records\n")

        has_parse_path = 0
        has_ocr_conf = 0

        for meta in all_meta:
            print(f"Document: {meta.document_id}")
            print(f"  parse_engine: {meta.parse_engine}")
            print(f"  parse_path: {meta.parse_path}")
            print(f"  ocr_confidence_avg: {meta.ocr_confidence_avg}")
            print(f"  total_pages: {meta.total_pages}")

            # 统计
            if meta.parse_path is not None:
                has_parse_path += 1

                # 验证 parse_path 值
                if meta.parse_path not in ['ocr', 'native_text', 'mixed', 'unknown']:
                    print(f"  [WARN] Invalid parse_path: {meta.parse_path}")
                else:
                    print(f"  [PASS] Valid parse_path")

                # 验证 OCR confidence
                if meta.parse_path == 'ocr':
                    if meta.ocr_confidence_avg is not None:
                        if 0.0 <= meta.ocr_confidence_avg <= 1.0:
                            print(f"  [PASS] Valid ocr_confidence_avg: {meta.ocr_confidence_avg:.3f}")
                            has_ocr_conf += 1
                        else:
                            print(f"  [WARN] ocr_confidence_avg out of range: {meta.ocr_confidence_avg}")
                    else:
                        print(f"  [WARN] OCR path should have ocr_confidence_avg")
            else:
                print(f"  [INFO] parse_path is NULL (document processed before M8)")

            print()

        # 汇总
        print("=" * 60)
        print("Summary")
        print("=" * 60)
        print(f"Total documents: {len(all_meta)}")
        print(f"With parse_path: {has_parse_path}")
        print(f"With valid OCR confidence: {has_ocr_conf}")

        if has_parse_path > 0:
            print("\n[PASS] M8 parse_path feature is working!")
            print("[INFO] Found documents with parse_path field")
            return 0
        else:
            print("\n[WARN] No documents with parse_path found")
            print("[INFO] This may mean:")
            print("  1. All documents were processed before M8 implementation")
            print("  2. Parse meta persistence is not working")
            print("\n[ACTION] Upload a new document to test M8:")
            print("  uv run python -c \"")
            print("from pathlib import Path")
            print("from backend.services.document_service import DocumentService")
            print("service = DocumentService.create_default()")
            print("with open('tests/assets/test_docx.docx', 'rb') as f:")
            print("    result = service.upload_document('test_m8.docx', f.read())")
            print("print('Uploaded:', result)")
            print("\"")
            return 1

    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(check_parse_meta())
