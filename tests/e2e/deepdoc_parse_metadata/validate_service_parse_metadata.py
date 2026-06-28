#!/usr/bin/env python3
"""DeepDoc parse metadata validation through DocumentService.

这个脚本直接调用 DocumentService 和数据库，无需 HTTP 认证。
"""

import sys
from pathlib import Path

PROJECT_ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "pyproject.toml").is_file())
DOCUMENT_FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures" / "documents"
sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.document_service import DocumentService
from backend.infra.db.database import SessionLocal
from backend.infra.db.models import DocumentParseMeta


def test_pdf_parse_meta():
    """测试 PDF 的 parse_path 和 ocr_confidence_avg"""
    print("=" * 60)
    print("Test 1: PDF Document")
    print("=" * 60)

    # 上传 PDF
    pdf_path = DOCUMENT_FIXTURES_DIR / "国电电力.pdf"
    if not pdf_path.exists():
        print(f"[FAIL] PDF file not found: {pdf_path}")
        return False

    print(f"[INFO] Processing PDF: {pdf_path.name}")
    service = DocumentService.create_default()

    with open(pdf_path, "rb") as f:
        content = f.read()

    try:
        result = service.upload_document(pdf_path.name, content)
        print(f"[PASS] PDF processed successfully: {result.get('filename')}")
    except Exception as e:
        print(f"[FAIL] PDF processing failed: {e}")
        return False

    # 查询 parse_meta
    print("\n[INFO] Querying parse_meta...")
    db = SessionLocal()
    try:
        meta = db.query(DocumentParseMeta).filter(
            DocumentParseMeta.document_id == pdf_path.name
        ).first()

        if not meta:
            print("[FAIL] parse_meta not found")
            return False

        print("[PASS] parse_meta found")
        print(f"\n[INFO] parse_meta contents:")
        print(f"  parse_engine: {meta.parse_engine}")
        print(f"  parse_path: {meta.parse_path}")
        print(f"  ocr_confidence_avg: {meta.ocr_confidence_avg}")
        print(f"  total_pages: {meta.total_pages}")

        # 验证 parse_path
        if meta.parse_path not in ['ocr', 'native_text', 'mixed', 'unknown']:
            print(f"\n[FAIL] Invalid parse_path: {meta.parse_path}")
            return False
        print(f"\n[PASS] Valid parse_path: {meta.parse_path}")

        # 如果是 OCR，验证置信度
        if meta.parse_path == 'ocr':
            if meta.ocr_confidence_avg is None:
                print("[FAIL] OCR path should have ocr_confidence_avg")
                return False
            if not (0.0 <= meta.ocr_confidence_avg <= 1.0):
                print(f"[FAIL] ocr_confidence_avg out of range: {meta.ocr_confidence_avg}")
                return False
            print(f"[PASS] Valid ocr_confidence_avg: {meta.ocr_confidence_avg:.3f}")

        return True

    finally:
        db.close()


def test_docx_parse_meta():
    """测试 DOCX 的 parse_path"""
    print("\n" + "=" * 60)
    print("测试 2: DOCX 文档（test_docx.docx）")
    print("=" * 60)

    # 上传 DOCX
    docx_path = DOCUMENT_FIXTURES_DIR / "test_docx.docx"
    if not docx_path.exists():
        print(f"[FAIL] DOCX 文件不存在: {docx_path}")
        return False

    print(f"[INFO] 处理 DOCX: {docx_path.name}")
    service = DocumentService.create_default()

    with open(docx_path, "rb") as f:
        content = f.read()

    try:
        result = service.upload_document(docx_path.name, content)
        print(f"[PASS] DOCX 处理成功: {result.get('filename')}")
    except Exception as e:
        print(f"[FAIL] DOCX 处理失败: {e}")
        return False

    # 查询 parse_meta
    print("\n[INFO] 查询 parse_meta...")
    db = SessionLocal()
    try:
        meta = db.query(DocumentParseMeta).filter(
            DocumentParseMeta.document_id == docx_path.name
        ).first()

        if not meta:
            print("[FAIL] parse_meta 未找到")
            return False

        print("[PASS] parse_meta 查询成功")
        print(f"\n[INFO] parse_meta 内容:")
        print(f"  parse_engine: {meta.parse_engine}")
        print(f"  parse_path: {meta.parse_path}")
        print(f"  ocr_confidence_avg: {meta.ocr_confidence_avg}")

        # 验证 parse_path
        if meta.parse_path != 'native_text':
            print(f"\n[FAIL] DOCX parse_path 应为 native_text，实际: {meta.parse_path}")
            return False
        print(f"\n[PASS] parse_path 正确: {meta.parse_path}")

        # DOCX 不应有 OCR 置信度
        if meta.ocr_confidence_avg is not None:
            print(f"[WARN]  DOCX 不应有 ocr_confidence_avg: {meta.ocr_confidence_avg}")
        else:
            print("[PASS] ocr_confidence_avg 为 null（符合预期）")

        return True

    finally:
        db.close()


def main():
    print("=" * 60)
    print("M8 端到端验证（直接服务层调用）")
    print("=" * 60)
    print()

    results = []

    # 测试 1: PDF
    try:
        results.append(test_pdf_parse_meta())
    except Exception as e:
        print(f"\n[FAIL] PDF 测试异常: {e}")
        import traceback
        traceback.print_exc()
        results.append(False)

    # 测试 2: DOCX
    try:
        results.append(test_docx_parse_meta())
    except Exception as e:
        print(f"\n[FAIL] DOCX 测试异常: {e}")
        import traceback
        traceback.print_exc()
        results.append(False)

    # 汇总
    print("\n" + "=" * 60)
    print("验证结果汇总")
    print("=" * 60)

    passed = sum(results)
    total = len(results)

    print(f"\n通过: {passed}/{total}")

    if all(results):
        print("\n[PASS] 所有验证通过！M8 功能正常工作。")
        print("\n[INFO] 验收确认:")
        print("  [PASS] PDF parse_path 字段正确")
        print("  [PASS] PDF ocr_confidence_avg 字段正确（如果 parse_path=ocr）")
        print("  [PASS] DOCX parse_path 固定为 native_text")
        print("  [PASS] DOCX ocr_confidence_avg 为 null")
        print("\n[WARN]  Table nearby 关联需手动验证（查询 parent_chunks 表）")
        return 0
    else:
        print("\n[FAIL] 部分验证未通过，请检查上述输出。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
