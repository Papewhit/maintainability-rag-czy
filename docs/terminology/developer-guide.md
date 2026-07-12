# Terminology Module — 开发者指南

## 模块架构

```
backend/rag/terminology/
    __init__.py       # 公共导出
    table.py          # TerminologyEntry / EntityType / TerminologyTable / QueryTerminologyResult
    matcher.py        # Aho-Corasick 自动机 (纯 Python + pyahocorasick 可选加速)
    jieba_dict.py     # jieba userdict 构建、重载、热更新
    rescan.py         # 后台 rescan 任务 + BM25 原子重建
```

外加：

```
backend/routers/admin_terminology.py   # 管理员 CRUD API + rescan 触发
backend/infra/db/models.py             # TerminologyEntryModel / AuditLog / RescanTaskModel
data/terminology_seed.csv             # 预设术语 seed (205 条)
data/jieba_userdict.txt               # 运行时生成的 jieba 词典文件
```

---

## 核心类与 API

### EntityType（枚举）

```python
from backend.rag.terminology import EntityType

EntityType.PRODUCT_MODEL       # 产品型号 (TBD234, CAT3516...)
EntityType.EQUIPMENT           # 设备 (燃气轮机, 螺旋桨...)
EntityType.COMPONENT           # 组件 (轴承, 活塞...)
EntityType.PARAMETER           # 参数 (转速, 温度...)
EntityType.MAINTENANCE_ACTION  # 维修动作 (拆卸, 对中, 探伤...)
```

### TerminologyEntry（数据类）

```python
@dataclass(frozen=True)
class TerminologyEntry:
    canonical: str              # 规范化形式
    entity_type: EntityType     # 实体类型
    variants: tuple[str, ...]   # 同义变体列表
    description: str | None     # 可选描述
    metadata: dict              # 扩展字段
```

### TerminologyTable（单例）

```python
from backend.rag.terminology.table import get_terminology_table, TerminologyTable

table = get_terminology_table()

# 访问
entry = table.get(EntityType.COMPONENT, "主减速齿轮箱")
canonical, etype = table.resolve_canonical("MRG")  # -> ("主减速齿轮箱", EntityType.COMPONENT)

# 扫描
matches: list[TermMatch] = table.scan_text("MRG 拆卸时需专用工具")
# -> [TermMatch(surface="MRG", canonical="主减速齿轮箱", ...), TermMatch(surface="拆卸", ...)]

# 查询预检
result: QueryTerminologyResult = table.query_preflight("MRG 拆卸怎么做")
# result.query_entities     -> 命中的实体列表
# result.normalized_query   -> "主减速齿轮箱 拆卸怎么做"
# result.sparse_expansion   -> 所有变体并入的查询字符串
# result.protected_tokens   -> 多字术语列表
```

### Aho-Corasick 匹配器

```python
from backend.rag.terminology.matcher import AhoCorasick, TermMatch, scan_text, longest_non_overlapping

ac = AhoCorasick()
ac.add_pattern("主减速齿轮箱", "主减速齿轮箱", "component")
ac.add_pattern("齿轮箱", "齿轮箱", "component")
ac.build()

raw = ac.scan("检查主减速齿轮箱")  # 所有命中（包含重叠）
kept = longest_non_overlapping(raw)  # 最长匹配、非重叠子集
```

`pyahocorasick` 会在可用时自动启用加速（`import ahocorasick`）；否则使用纯 Python 实现。

### jieba 用户词典

```python
from backend.rag.terminology.jieba_dict import (
    build_jieba_userdict_file,
    reload_jieba_with_terminology,
    get_terminology_surfaces,
)

# 从术语表提取所有 surface forms
surfaces = get_terminology_surfaces(table)  # -> [(surface, entity_type), ...]

# 构建并加载 jieba userdict（含清除旧缓存）
reload_jieba_with_terminology(surfaces)
```

**重要：** `jieba.load_userdict` 是累加操作。必须在加载前调用 `reload_jieba_with_terminology` 来清除旧的 `FREQ` 缓存（私有 API `jieba.dt.FREQ.clear()`）。

### Rescan 任务

```python
from backend.rag.terminology.rescan import run_rescan, get_task_status, is_rescan_running

# 触发
task_id = run_rescan(triggered_by="admin")

# 查询进度
status = get_task_status(task_id)
# -> {"task_id": "...", "status": "running", "processed_chunks": 5000, "total_chunks": 10000}

# 检查锁
if is_rescan_running():
    ...  # 不能执行术语表写操作
```

Rescan 流程：
1. 获取全局锁（阻止术语表 CRUD + 文档上传）
2. 重载 jieba userdict
3. 遍历 collection 全部 chunk，重新扫描 metadata
4. 批量 upsert Milvus + ParentChunkStore
5. 重建 BM25 state（临时文件 + 原子 rename）
6. 释放锁

---

## 扩展新的 EntityType

### 1. 添加枚举值

在 `backend/rag/terminology/table.py` 的 `EntityType` 中添加：

```python
class EntityType(StrEnum):
    ...
    SAFETY_SYSTEM = "safety_system"  # 新增
```

### 2. 更新 seed CSV

在 `data/terminology_seed.csv` 中添加新类型的术语行。

### 3. 更新索引时注释（如需要）

在 `backend/documents/loader.py` 的 `_scan_terminology` 中无需更改——它通用扫描所有 entity_type。

### 4. 更新下游（如需要）

rerank / confidence gate 的 entity 信号处理（位于 `backend/rag/utils.py` 和 `backend/rag/confidence.py`）目前按 entity_type 聚合，新类型自动参与计分，无需显式注册。

---

## 数据流

```
管理员 API (CRUD) ──→ terminology_entries 表 ──→ 启动时加载到 TerminologyTable
                                           └──→ 内存更新后重建 jieba userdict

文档上传 ──→ DocumentLoader.load_document()
              └──→ _scan_terminology()     ← 使用 TerminologyTable.ac_scan()
                      ├──→ entity_types, term_match_count → Milvus
                      └──→ term_matches, protected_tokens → ParentChunkStore

用户查询 ──→ prepare_candidate_retrieval()
              └──→ terminology_preflight()  ← 使用 TerminologyTable.query_preflight()
                      ├──→ normalized_query → dense embedding
                      ├──→ sparse_expansion → BM25 sparse embedding
                      └──→ term_matches → rag_trace

术语表变更 ──→ POST /admin/terminology/rescan
                  └──→ RescanTask (后台线程)
                          ├──→ 重扫全部 chunk metadata
                          ├──→ upsert Milvus + ParentChunkStore
                          └──→ 原子重建 BM25 state
```

---

## Entity Types 存储契约

`entity_types` 的 Milvus 存储表示与 Python 运行时表示必须分离：

| 边界 | 表示 | 示例 |
| --- | --- | --- |
| chunker / terminology runtime | `list[str]` | `["component", "maintenance_action"]` |
| Milvus wire format | UTF-8 JSON string，最多 512 字节 | `["component","maintenance_action"]` |
| RAG retrieval / rerank runtime | 去重后的 `list[str]` | `["component", "maintenance_action"]` |

正常 ingestion writer 与 terminology rescan 使用
`backend.infra.vector_store.metadata_codec.encode_entity_types()` 写入。hybrid、split dense/sparse、
dense fallback 三条检索路径使用 `decode_entity_types()` 解码后再返回候选文档。

读取端兼容历史 Milvus dynamic-field 数组与 JSON 字符串。非法 JSON、非数组 JSON 和不支持的
类型降级为空列表，不阻断检索；写入端超过 512 字节时拒绝写入，避免产生违反存储契约的记录。
rerank fusion 和 rerank cache signature 使用同一个 decoder，因此语义相同的历史数组和新 JSON
字符串产生相同的 entity coverage、fusion 分数和缓存键。

本次调整不要求立即重建 collection。读取兼容层允许历史数组和新 JSON 字符串共存；所有新写入
统一为 JSON 字符串。
