---
document_type: validation_guide
status: historical
scope: test.ingestion
last_verified_commit: 8babe339cda636936c6c0af3c95a99e7c77c2f19
last_verified_time: 2026-07-12T00:00:00+08:00
---

# M8 端到端验证 - 快速开始

## 当前状态

- ✅ 代码已实现并通过单元测试（12/12）
- ✅ 回归测试通过（124/124）
- ✅ Subagent 审查通过
- ⚠️ 端到端验证待执行（需服务启动）

---

## 验证步骤

### 第一步：启动服务

```bash
# 1. 启动基础设施（如果未运行）
docker compose up -d postgres redis milvus-standalone

# 2. 启动 FastAPI 服务
uv run uvicorn backend.main:app --reload --port 8000

# 3. 确认服务可达
curl http://localhost:8000/
```

### 第二步：执行自动化验证

```bash
# 运行快速验证脚本
bash tests/e2e/deepdoc_parse_metadata/quick_http_parse_metadata.sh
```

**预期输出：**
```
✓ 服务已连接
✓ PDF 上传成功
✓ parse_meta 查询成功
✓ parse_path 有效: ocr
✓ ocr_confidence_avg 有效: 0.850
✓ PDF 验证通过
✓ DOCX 上传成功
✓ parse_path 正确: native_text
✓ ocr_confidence_avg 为 null
✓ DOCX 验证通过
✓ M8 自动化验证完成！
```

### 第三步（可选）：手动验证 Table Nearby

**方法 1: 直接查询 DB**
```sql
SELECT 
  chunk_id,
  chunk_role,
  parent_extras->'nearby_block_ids' as nearby_blocks,
  substring(text, 1, 300) as text_preview
FROM parent_chunks
WHERE filename = '国电电力.pdf'
  AND chunk_role = 'table_root'
LIMIT 5;
```

**验证点：**
- nearby_block_ids 应非空（如果 PDF 有表格）
- text 应包含表格前后的解释段落

**方法 2: 使用 Python 脚本**
```python
from backend.infra.db.database import SessionLocal
from backend.infra.db.models import ParentChunk

db = SessionLocal()
chunks = db.query(ParentChunk).filter(
    ParentChunk.filename == '国电电力.pdf',
    ParentChunk.chunk_role == 'table_root'
).all()

for chunk in chunks:
    print(f"Chunk ID: {chunk.chunk_id}")
    print(f"Nearby blocks: {chunk.parent_extras.get('nearby_block_ids')}")
    print(f"Text preview: {chunk.text[:200]}")
    print("-" * 60)
```

---

## 验收标准

| 项目 | 标准 | 状态 |
|------|------|------|
| PDF parse_path | ocr/native_text/mixed 之一 | ⏳ 待验证 |
| PDF ocr_confidence_avg | 0.0-1.0（如果 parse_path=ocr） | ⏳ 待验证 |
| DOCX parse_path | 固定为 native_text | ⏳ 待验证 |
| DOCX ocr_confidence_avg | null | ⏳ 待验证 |
| Table nearby_block_ids | 非空（如果有表格） | ⏳ 待验证 |
| Table parent text | 包含周围解释段落 | ⏳ 待验证 |

---

## 故障排查

### 服务无法启动
```bash
# 检查端口占用
netstat -ano | grep :8000

# 检查依赖
uv run pip list | grep fastapi

# 查看错误日志
uv run uvicorn backend.main:app --reload --log-level debug
```

### parse_meta API 返回 404
```bash
# 直接查询 DB 确认数据是否写入
psql -U postgres -d langchain_app -c "SELECT * FROM document_parse_meta WHERE document_id = '国电电力.pdf';"
```

### parse_path 为 null 或 unknown
- 检查 DeepDoc 日志
- 手动运行 adapter.py 测试
- 查看 parse_warnings 字段

---

## 完成验证后

1. **更新交付报告**
   - 在 `.claude/m8-delivery-summary.md` 中标记验证完成
   - 记录实际的 parse_path 和 ocr_confidence_avg 值

2. **提交验证结果**
```bash
git add .
git commit -m "docs(M8): 端到端验证完成

验证结果：
- PDF parse_path: [实际值]
- PDF ocr_confidence_avg: [实际值]
- DOCX parse_path: native_text
- Table nearby: 已验证

M8 交付完成 ✓"
```

3. **合并到主分支**
```bash
git checkout main
git merge rag-fusion-design
git push origin main
```

---

## 联系方式

如有问题，请查阅：
- 详细验证指南：`docs/validation/deepdoc-parse-metadata-validation.md`
- 实施报告：`.claude/m8-final-delivery-report.md`
- 交付摘要：`.claude/m8-delivery-summary.md`

