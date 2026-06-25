# M8 端到端验证指南

## 前置条件

1. **启动服务**
```bash
# 确保基础设施运行
docker compose up -d postgres redis milvus-standalone

# 启动 FastAPI 服务
uv run uvicorn backend.main:app --reload --port 8000
```

2. **确认服务可达**
```bash
curl http://localhost:8000/health
# 或
curl http://localhost:8000/
```

---

## 方法 1: 使用自动化脚本

```bash
uv run python m8_e2e_validation.py
```

**预期输出：**
```
✓ 服务已连接
✓ PDF parse_path 合理: ocr/native_text/mixed
✓ ocr_confidence_avg 有效: 0.850
✓ DOCX parse_path 正确: native_text
✓ 所有验证通过！
```

---

## 方法 2: 手动验证（推荐）

### 步骤 1: 上传 PDF 文档

```bash
curl -X POST http://localhost:8000/documents/upload \
  -F "file=@tests/assets/国电电力.pdf" \
  -o /tmp/pdf_upload_result.json

cat /tmp/pdf_upload_result.json | python -m json.tool
```

**检查点：**
- 返回状态 200
- 响应包含 `filename`

### 步骤 2: 查询 PDF 的 parse_meta

```bash
curl http://localhost:8000/admin/documents/国电电力.pdf/parse_meta \
  -o /tmp/pdf_parse_meta.json

cat /tmp/pdf_parse_meta.json | python -m json.tool
```

**验收标准：**
```json
{
  "document_id": "国电电力.pdf",
  "parse_engine": "deepdoc",
  "parse_path": "ocr",  // 或 "native_text" 或 "mixed"
  "ocr_confidence_avg": 0.85,  // 如果 parse_path="ocr"，应在 0.0-1.0 之间
  "total_pages": 7,
  ...
}
```

**验证点：**
- ✅ `parse_path` 字段存在
- ✅ `parse_path` 值为 `"ocr"` / `"native_text"` / `"mixed"` / `"unknown"` 之一
- ✅ 如果 `parse_path="ocr"`，则 `ocr_confidence_avg` 应在 0.0-1.0 之间
- ✅ 如果 `parse_path="native_text"`，则 `ocr_confidence_avg` 可能为 null

### 步骤 3: 上传 DOCX 文档

```bash
curl -X POST http://localhost:8000/documents/upload \
  -F "file=@tests/assets/test_docx.docx" \
  -o /tmp/docx_upload_result.json
```

### 步骤 4: 查询 DOCX 的 parse_meta

```bash
curl http://localhost:8000/admin/documents/test_docx.docx/parse_meta \
  -o /tmp/docx_parse_meta.json

cat /tmp/docx_parse_meta.json | python -m json.tool
```

**验收标准：**
```json
{
  "document_id": "test_docx.docx",
  "parse_engine": "deepdoc",
  "parse_path": "native_text",  // DOCX 应固定为 native_text
  "ocr_confidence_avg": null,  // DOCX 无 OCR
  ...
}
```

**验证点：**
- ✅ `parse_path` 固定为 `"native_text"`
- ✅ `ocr_confidence_avg` 为 `null`

### 步骤 5: 验证 Table Nearby（高级）

**方法 A: 通过 DB 查询**
```sql
-- 查询 parent chunk store 中的表格 chunk
SELECT 
  chunk_id, 
  chunk_role, 
  parent_extras->'nearby_block_ids' as nearby_blocks,
  substring(text, 1, 200) as text_preview
FROM parent_chunks
WHERE filename = '国电电力.pdf'
  AND chunk_role = 'table_root'
LIMIT 5;
```

**验证点：**
- ✅ `parent_extras['nearby_block_ids']` 非空（如果 PDF 有表格）
- ✅ `text` 字段包含表格前后的解释段落（不只是表格 markdown）

**方法 B: 通过 API 查询（如果有 chunk 查询接口）**
```bash
# 假设有 /chunks API
curl "http://localhost:8000/chunks?filename=国电电力.pdf&role=table_root"
```

---

## 快速验证脚本（简化版）

```bash
#!/bin/bash
set -e

echo "=== M8 快速验证 ==="

# 1. 上传 PDF
echo "上传 PDF..."
curl -s -X POST http://localhost:8000/documents/upload \
  -F "file=@tests/assets/国电电力.pdf" > /dev/null
sleep 2

# 2. 查询 parse_meta
echo "查询 PDF parse_meta..."
curl -s http://localhost:8000/admin/documents/国电电力.pdf/parse_meta | \
  python -c "
import sys, json
data = json.load(sys.stdin)
print(f\"parse_path: {data.get('parse_path')}\")
print(f\"ocr_confidence_avg: {data.get('ocr_confidence_avg')}\")

# 验证
assert data.get('parse_path') in ['ocr', 'native_text', 'mixed', 'unknown'], 'Invalid parse_path'
if data.get('parse_path') == 'ocr':
    conf = data.get('ocr_confidence_avg')
    assert conf is not None and 0 <= conf <= 1, 'Invalid ocr_confidence_avg'
print('✓ PDF 验证通过')
"

# 3. 上传 DOCX
echo "上传 DOCX..."
curl -s -X POST http://localhost:8000/documents/upload \
  -F "file=@tests/assets/test_docx.docx" > /dev/null
sleep 2

# 4. 查询 DOCX parse_meta
echo "查询 DOCX parse_meta..."
curl -s http://localhost:8000/admin/documents/test_docx.docx/parse_meta | \
  python -c "
import sys, json
data = json.load(sys.stdin)
print(f\"parse_path: {data.get('parse_path')}\")
print(f\"ocr_confidence_avg: {data.get('ocr_confidence_avg')}\")

# 验证
assert data.get('parse_path') == 'native_text', 'DOCX should be native_text'
assert data.get('ocr_confidence_avg') is None, 'DOCX should not have OCR confidence'
print('✓ DOCX 验证通过')
"

echo ""
echo "=== ✓ M8 验证完成 ==="
```

保存为 `m8_quick_test.sh`，执行：
```bash
bash m8_quick_test.sh
```

---

## 故障排查

### 问题 1: parse_meta API 返回 404

**原因：** parse_meta 未持久化（best-effort 写入可能失败）

**解决：**
1. 检查 DB 连接是否正常
2. 检查 `document_service.py` 日志是否有持久化错误
3. 手动查询 DB：
```sql
SELECT * FROM document_parse_meta WHERE document_id = '国电电力.pdf';
```

### 问题 2: parse_path 为 null 或 unknown

**原因：** 
- PDF 中所有 block 无 parse_source 标记
- DeepDoc 解析失败

**排查：**
1. 检查 DeepDoc 日志
2. 检查 `ParsedBlock` 是否有 `parse_source` 元数据
3. 手动测试 adapter.py 的 `_summarize_pdf_parse_path`

### 问题 3: ocr_confidence_avg 为 null（parse_path="ocr"）

**原因：** OCR score 提取失败

**排查：**
1. 检查 `_ocr.py` 的 `recognize()` 是否返回 score
2. 检查 `_pdf_parser.py` 是否存储 score
3. 打印 `parser.boxes` 查看 score 字段

---

## 成功标准

- ✅ PDF 的 `parse_path` 为 ocr/native_text/mixed 之一
- ✅ PDF OCR 路径的 `ocr_confidence_avg` 在 0.0-1.0 之间
- ✅ DOCX 的 `parse_path` 固定为 `native_text`
- ✅ DOCX 的 `ocr_confidence_avg` 为 null
- ✅ Table nearby：parent_extras['nearby_block_ids'] 非空（如果有表格）

**全部通过即 M8 验证完成 ✓**
