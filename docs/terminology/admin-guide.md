# Terminology Module — 管理员操作指南

## 概述

术语模块维护一份领域术语表，贯穿 RAG 索引和查询两侧：

- **BM25 分词保护**：多字术语（"主减速齿轮箱"）在 jieba 分词时保持完整，不被切碎
- **查询扩展**：用户查询中的变体自动替换为 canonical 形式，同时展开所有同义变体用于 BM25 检索
- **Chunk 标注**：上传文档时自动扫描 chunk 正文，标注命中的术语（entity_types / term_match_count）

---

## 术语表管理

### 查看术语表

```bash
# 查看全部术语
curl -H "Authorization: Bearer <token>" http://localhost:8000/admin/terminology

# 按类型筛选
curl -H "Authorization: Bearer <token>" http://localhost:8000/admin/terminology?entity_type=component

# 查看统计
curl -H "Authorization: Bearer <token>" http://localhost:8000/admin/terminology/stats
```

### 新增术语

```bash
curl -X POST -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  http://localhost:8000/admin/terminology \
  -d '{
    "canonical": "主减速齿轮箱",
    "entity_type": "component",
    "variants": ["主齿轮箱", "主减速器", "MRG", "main reduction gearbox"],
    "description": "船舶主推进系统中的核心减速传动部件"
  }'
```

**规则:**
- `entity_type` 必须是以下之一：`product_model`, `equipment`, `component`, `parameter`, `maintenance_action`
- `(entity_type, canonical)` 组合必须唯一，重复创建返回 409
- `variants` 自动去重，空字符串自动过滤

### 更新术语

```bash
curl -X PUT -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  http://localhost:8000/admin/terminology/1 \
  -d '{...}'
```

### 删除术语

```bash
curl -X DELETE -H "Authorization: Bearer <token>" \
  http://localhost:8000/admin/terminology/1
```

---

## 批量导入

支持 CSV 和 JSON 两种格式。

### CSV 格式

```csv
canonical,entity_type,variants,description
主减速齿轮箱,component,MRG|主齿轮箱|主减速器,船舶主推进系统减速传动部件
拆卸,maintenance_action,分解|拆解|disassembly,设备拆解作业
```

```bash
curl -X POST -H "Authorization: Bearer <token>" \
  -F "file=@terms.csv" \
  http://localhost:8000/admin/terminology/bulk
```

- variants 字段用 `|` 分隔多个变体
- 编码：UTF-8（带 BOM 也可）

### JSON 格式

```bash
curl -X POST -H "Authorization: Bearer <token>" \
  -F "file=@terms.json" \
  http://localhost:8000/admin/terminology/bulk
```

---

## Rescan 操作

术语表变更后，**需要执行 rescan** 才能让新术语在以下位置生效：

- 已有 chunk 的 entity_types / term_match_count
- jieba 分词保护（重新注入 userdict）
- BM25 倒排索引重建

### 触发 rescan

```bash
curl -X POST -H "Authorization: Bearer <token>" \
  http://localhost:8000/admin/terminology/rescan
# 返回: {"task_id": "a1b2c3d4...", "status": "started"}
```

### 查询进度

```bash
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/admin/terminology/rescan/a1b2c3d4...
# 返回: {"task_id": "...", "status": "running", "processed_chunks": 5000, "total_chunks": 10000}
```

状态值：
- `pending` — 已创建，等待执行
- `running` — 正在执行中
- `completed` — 执行完成
- `failed` — 执行失败（查看 error 字段）

### 注意事项

1. **Rescan 期间受影响的写入被阻塞**：术语表 CRUD 和文档上传统统被锁。查询不受影响（使用旧 BM25 state）。
2. **BM25 原子切换**：rescan 写入临时文件 `bm25_state.new.json`，完成后原子 rename。查询永远看到旧版本或新版本，不会看到半成品。
3. **失败回滚**：BM25 旧 state 在 rescan 开始前备份到 `.bak` 文件；失败时自动恢复。
4. **不要并发执行两个 rescan**：API 会返回 409 拒绝第二个请求。

---

## 常见问题

### Q: 新增术语后为什么查询没变化？

A: 术语写入内存表后立刻在查询 preflight 生效（query 扩展和规范化）。但已索引的 chunk metadata **不会**自动更新——需要执行 rescan。

### Q: Rescan 需要多长时间？

A: 取决于 collection 规模。10 万 chunk 级别约 10-30 分钟（主要耗时在 Milvus upsert 和 BM25 重建）。

### Q: 删除了术语，但 jieba 还在保护它？

A: jieba 的 `load_userdict` 是累加操作。rescan 会重建 userdict 并清除旧的 `FREQ` 缓存。如果不想等 rescan，重启服务也可清除。

### Q: Rescan 失败后怎么办？

A: BM25 自动回滚到 rescan 前的备份。查看失败原因（`GET /rescan/{task_id}` 的 error 字段），修复问题后重新触发。
