#!/bin/bash
# M8 快速验证脚本
# 要求：服务已在 localhost:8000 启动

set -e

echo "============================================================"
echo "M8 快速验证"
echo "============================================================"

# 检查服务
echo ""
echo "检查服务连接..."
if ! curl -s -f http://localhost:8000/ > /dev/null 2>&1; then
  echo "ERROR: 无法连接服务 http://localhost:8000"
  echo "请先启动服务: uv run uvicorn backend.main:app --reload --port 8000"
  exit 1
fi
echo "✓ 服务已连接"

# 1. 上传 PDF
echo ""
echo "============================================================"
echo "测试 1: PDF 文档 (国电电力.pdf)"
echo "============================================================"
echo "上传 PDF..."
curl -s -X POST http://localhost:8000/documents/upload \
  -F "file=@tests/assets/国电电力.pdf" > /tmp/m8_pdf_upload.json

if [ $? -ne 0 ]; then
  echo "ERROR: PDF 上传失败"
  exit 1
fi

echo "✓ PDF 上传成功"
sleep 2  # 等待持久化

# 2. 查询 PDF parse_meta
echo "查询 PDF parse_meta..."
curl -s http://localhost:8000/admin/documents/国电电力.pdf/parse_meta > /tmp/m8_pdf_meta.json

if [ $? -ne 0 ]; then
  echo "ERROR: parse_meta 查询失败"
  exit 1
fi

echo "✓ parse_meta 查询成功"
echo ""
echo "PDF parse_meta 内容:"
cat /tmp/m8_pdf_meta.json | python -m json.tool

# 验证 PDF
python -c "
import sys, json
with open('/tmp/m8_pdf_meta.json') as f:
    data = json.load(f)

parse_path = data.get('parse_path')
ocr_conf = data.get('ocr_confidence_avg')

print()
print('验证 PDF parse_path:')
print(f'  parse_path = {parse_path}')
print(f'  ocr_confidence_avg = {ocr_conf}')

# 检查 parse_path
if parse_path not in ['ocr', 'native_text', 'mixed', 'unknown']:
    print(f'✗ parse_path 无效: {parse_path}')
    sys.exit(1)
print(f'✓ parse_path 有效: {parse_path}')

# 如果是 OCR，检查置信度
if parse_path == 'ocr':
    if ocr_conf is None:
        print('✗ OCR 路径应有 ocr_confidence_avg')
        sys.exit(1)
    if not (0.0 <= ocr_conf <= 1.0):
        print(f'✗ ocr_confidence_avg 超出范围: {ocr_conf}')
        sys.exit(1)
    print(f'✓ ocr_confidence_avg 有效: {ocr_conf:.3f}')

print('✓ PDF 验证通过')
"

if [ $? -ne 0 ]; then
  echo "ERROR: PDF 验证失败"
  exit 1
fi

# 3. 上传 DOCX
echo ""
echo "============================================================"
echo "测试 2: DOCX 文档 (test_docx.docx)"
echo "============================================================"
echo "上传 DOCX..."
curl -s -X POST http://localhost:8000/documents/upload \
  -F "file=@tests/assets/test_docx.docx" > /tmp/m8_docx_upload.json

if [ $? -ne 0 ]; then
  echo "ERROR: DOCX 上传失败"
  exit 1
fi

echo "✓ DOCX 上传成功"
sleep 2

# 4. 查询 DOCX parse_meta
echo "查询 DOCX parse_meta..."
curl -s http://localhost:8000/admin/documents/test_docx.docx/parse_meta > /tmp/m8_docx_meta.json

if [ $? -ne 0 ]; then
  echo "ERROR: parse_meta 查询失败"
  exit 1
fi

echo "✓ parse_meta 查询成功"
echo ""
echo "DOCX parse_meta 内容:"
cat /tmp/m8_docx_meta.json | python -m json.tool

# 验证 DOCX
python -c "
import sys, json
with open('/tmp/m8_docx_meta.json') as f:
    data = json.load(f)

parse_path = data.get('parse_path')
ocr_conf = data.get('ocr_confidence_avg')

print()
print('验证 DOCX parse_path:')
print(f'  parse_path = {parse_path}')
print(f'  ocr_confidence_avg = {ocr_conf}')

# 检查 parse_path
if parse_path != 'native_text':
    print(f'✗ DOCX parse_path 应为 native_text, 实际: {parse_path}')
    sys.exit(1)
print(f'✓ parse_path 正确: {parse_path}')

# DOCX 不应有 OCR 置信度
if ocr_conf is not None:
    print(f'⚠ DOCX 不应有 ocr_confidence_avg: {ocr_conf}')
    # 不阻塞，只警告
else:
    print('✓ ocr_confidence_avg 为 null (符合预期)')

print('✓ DOCX 验证通过')
"

if [ $? -ne 0 ]; then
  echo "ERROR: DOCX 验证失败"
  exit 1
fi

# 5. Table nearby 提示
echo ""
echo "============================================================"
echo "测试 3: Table Nearby 关联"
echo "============================================================"
echo "⚠ Table nearby 验证需要手动检查 parent_chunk_store"
echo ""
echo "手动验证步骤:"
echo "1. 查询 DB: SELECT chunk_id, parent_extras->'nearby_block_ids' FROM parent_chunks WHERE filename='国电电力.pdf' AND chunk_role='table_root';"
echo "2. 检查 nearby_block_ids 是否非空"
echo "3. 检查 root chunk 的 text 是否包含表格前后的解释段落"
echo ""
echo "如果 PDF 无表格，此检查可跳过"

# 汇总
echo ""
echo "============================================================"
echo "验证结果汇总"
echo "============================================================"
echo "✓ PDF parse_path 验证通过"
echo "✓ PDF ocr_confidence_avg 验证通过 (如果 parse_path=ocr)"
echo "✓ DOCX parse_path 验证通过"
echo "⚠ Table nearby 需要手动验证"
echo ""
echo "============================================================"
echo "✓ M8 自动化验证完成！"
echo "============================================================"

exit 0
