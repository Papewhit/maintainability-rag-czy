> **Durable navigation:** Current behavior is documented in `docs/ARCHITECTURE.md`. Long-lived storage decisions are in `docs/architecture/decisions/ADR-0001-parent-leaf-evidence-storage.md`; unresolved schema/history items are in `docs/known-issues/`. This archived design remains historical change evidence.

## Context

当前项目 BM25 实现位于 `backend/infra/embedding.py` 的 `EmbeddingService`，状态持久化为 JSON 文件，分词依赖 jieba。jieba 默认词典对船舶/机械领域专业术语覆盖不全：
- 多字组合术语（"主减速齿轮箱"）被切成基础词（"主"/"减速"/"齿轮箱"）
- 中英文混合术语（"MRG"、"PLC 控制器"）切分不稳定
- 型号代码（"XYZ123-A"）被字符分词器拆分

QueryPlan 模块（`backend/rag/query_plan.py`）已经引入了 jieba，但只用在文件名模糊匹配，未对术语本身做保护。

设计文档（`docs/superpowers/specs/2026-05-20-rag-fusion-design.md` 4.7）要求术语模块同时服务：
- sparse 检索（避免被切碎、支持同义扩展）
- query expansion（preflight 阶段把变体规范化）
- chunk metadata（rerank 和 confidence gate 使用 entity_types 信号）
- scope/boost（filter 模式下精确匹配 entity_types）

这是一个真正的"贯穿模块"，必须同时改动索引和查询两侧。

## Goals / Non-Goals

**Goals：**
- 把术语表作为一等公民引入系统，可被管理员维护、自动加载、被多个模块共享
- 多字术语在 jieba 分词时受保护，BM25 召回稳定
- chunk metadata 中的 `entities` 字段成为 rerank/confidence/filter 的统一信号源
- 术语表变更可在不重切 chunk 的前提下生效

**Non-Goals：**
- 不做自动术语发现（即不让系统从文档中自动提取新术语写入术语表），原因：缺乏专家审核、成本高、容易引入垃圾术语
- 不做术语版本化/灰度（v1 假设管理员变更是原子事件，rescan 完成即生效）
- 不做术语翻译（中英文映射依靠管理员手工配置）
- 不在 retrieval_text 中拼接同义词（理由见 Decision 4）

## Decisions

### 决策 1：术语表落到数据库 + 内存

替代方案：JSON 文件。但术语表是动态资源（管理员频繁增删改），DB 表更合适。同时启动时全量加载到内存 dict + Aho-Corasick 自动机，避免每次查询去 DB。

```sql
-- backend/infra/db/models.py 新增表
CREATE TABLE terminology_entries (
    id          BIGSERIAL PRIMARY KEY,
    canonical   VARCHAR(200) NOT NULL,
    entity_type VARCHAR(50)  NOT NULL,    -- product_model | equipment | component | parameter | maintenance_action
    variants    JSONB        NOT NULL,    -- ["主齿轮箱", "main reduction gearbox", "MRG"]
    description TEXT,
    metadata    JSONB        DEFAULT '{}',
    created_at  TIMESTAMP    DEFAULT NOW(),
    updated_at  TIMESTAMP    DEFAULT NOW(),
    UNIQUE (entity_type, canonical)
);
CREATE INDEX idx_terminology_canonical ON terminology_entries (canonical);
CREATE INDEX idx_terminology_entity_type ON terminology_entries (entity_type);
```

内存表达：

```python
@dataclass(frozen=True)
class TerminologyEntry:
    canonical: str
    entity_type: EntityType
    variants: tuple[str, ...]       # tuple 保证不可变
    description: str | None
    metadata: dict
```

加载时构建：
- `_by_canonical: dict[str, TerminologyEntry]`
- `_surface_to_canonical: dict[str, tuple[str, EntityType]]`（所有 canonical + 所有 variants → 规范化形式）
- `_aho_corasick`: 多模式匹配自动机

### 决策 2：jieba userdict 由 TerminologyTable 生成

```python
def build_jieba_userdict(table: TerminologyTable) -> Path:
    """构建 jieba userdict 文件，每行格式: 词 频率 词性"""
    lines = []
    for entry in table.all():
        # canonical 和所有 variants 都注入
        terms = {entry.canonical, *entry.variants}
        for term in terms:
            # 频率给个高值（1000）确保不被基础词典覆盖
            # 词性按 entity_type 映射 (nz=专有名词)
            lines.append(f"{term} 1000 nz")
    path = Path("data/jieba_userdict.txt")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path

def reload_jieba_with_terminology(table: TerminologyTable):
    """启动时或术语表变更后调用"""
    path = build_jieba_userdict(table)
    jieba.load_userdict(str(path))
```

启动时调用一次；rescan 任务执行前再调用一次。

### 决策 3：Aho-Corasick 多模式最长匹配

term scan 需要对一段文本扫描出所有命中的术语，且对重叠匹配取最长（"主减速齿轮箱" 优先于 "齿轮箱"）。

```python
def scan_text(text: str) -> list[TermMatch]:
    """
    输入: chunk body 或 user query
    输出: 命中的 term 列表 [{surface, canonical, type, start, end}]
    """
    raw_matches = self._aho_corasick.iter(text)   # 所有命中
    # 按 start 排序，取最长匹配的非重叠子集
    return _longest_non_overlapping(raw_matches)
```

依赖 `pyahocorasick`（推荐）或纯 Python 实现（性能差但无依赖）。Aho-Corasick 时间复杂度 O(n + 命中数)，对单 chunk 扫描（~500 字符）几乎瞬时；对 collection 全量 rescan（10 万 chunk）也在分钟级。

### 决策 4：不在 retrieval_text 中拼接同义词

讨论时考虑过两种方案：
- A. 在 chunk 的 retrieval_text 中拼接术语和所有变体（"[术语:主减速齿轮箱;主齿轮箱;MRG] ... 原始正文"）
- B. retrieval_text 保持干净，术语扩展放在 query 时

选 B。理由：
- chunk 的 body 本身就有原始术语（chunker 是从 body 扫描得到 entities 的），canonical 形式不一定出现，但至少一个 variant 一定出现
- 同义词扩展在 query 侧做（preflight 阶段把 query 展成所有 variant 的 sparse_expansion），这样不污染索引、术语表变更无需重建 retrieval_text
- metadata 的 `entity_types` 字段独立承担"过滤/加权"职责（filter 模式下用 metadata，不用 body 字符串）

### 决策 5：metadata 字段分两层存储

进 Milvus（参与检索/过滤的字段，定长化）：
- `entity_types`: JSON array of strings，例如 `["product_model", "component"]`
- `term_match_count`: int，chunk 命中的术语总数（密度信号，供 rerank 用）

进 Parent Chunk Store（完整证据，不参与检索）：
- `term_matches`: 完整 JSON 数组，每项 `{surface, canonical, type, start, end}`
- `protected_tokens`: 该 chunk 中的多字术语列表（供前端高亮）

理由：Milvus VARCHAR 字段有长度限制（一般 1024 或 2048），完整 term_matches JSON 可能超长，且不需要在 Milvus 层过滤。

### 决策 6：rescan 任务设计

触发场景：
- 管理员创建/更新/删除术语条目
- 管理员手工触发 `POST /admin/terminology/rescan`

执行流程：
1. 加锁，禁止术语表变更和文档上传
2. 重新生成 jieba userdict，调用 `jieba.load_userdict()`
3. 拉取当前 collection 全部 chunk（按 1000 条分页 query Milvus）
4. 对每个 chunk 重新跑 `scan_text(chunk.retrieval_text)` → 新的 entities
5. 用 Milvus upsert 更新 chunk 的 `entity_types` 和 `term_match_count` 字段
6. 用 ParentChunkStore upsert 更新 `term_matches` 和 `protected_tokens`
7. 重建 BM25 state：
   - 用新 jieba 分词重跑 collection 全部 retrieval_text
   - 重算 vocab 和 DF
   - 写回 BM25 JSON 文件
8. 解锁

整个过程在后台任务中异步执行，进度通过 task status 表暴露给管理员。

预估耗时：10 万 chunk 量级在 10-30 分钟（主要耗时是 Milvus upsert 和 BM25 重建）。

### 决策 7：术语表变更的原子性

v1 不引入版本化，简化处理：
- 锁机制：rescan 期间所有写操作（术语表 CRUD、文档上传索引）全部 reject 或 queue
- 用户查询不受影响（rescan 期间仍能用旧 BM25 state 查询，只是新术语暂不生效）
- rescan 完成后切换内存术语表 + 重载 jieba + BM25 state，原子完成

如果未来需要版本化（rescan 期间查询使用新版术语表），可以引入 BM25 双 buffer 或 collection 别名切换，作为后续优化。

## Risks / Trade-offs

**风险 1：jieba userdict 热重载的副作用**

jieba 的 `load_userdict` 是累加而非替换。如果不重启进程，旧的术语条目（已删除的）仍残留在词典中。

缓解：
- 用 `jieba.dt.FREQ.clear()` 清空后重新加载（私有 API，pin jieba 版本）
- 或 rescan 后建议重启服务（在 admin UI 提示）
- 单元测试覆盖：删除术语 → 重载 → 验证旧术语在分词中不再受保护

**风险 2：BM25 重建期间查询性能下降**

rescan 期间 BM25 state 处于"半构建"状态。如果允许查询，可能返回不一致结果。

缓解：
- rescan 写新 BM25 state 到 `bm25_state.new.json`，构建完成后原子 rename 为 `bm25_state.json`
- EmbeddingService 检测文件 mtime 变化时热重载
- 查询期间持有旧 state（即使 rename 发生在查询中）

**风险 3：Aho-Corasick 内存占用**

10 万级别术语 + variants 总规模可能 50 万 patterns，Aho-Corasick 自动机内存可达 100MB+。

缓解：
- v1 假设术语规模 < 5000 条 entry × 平均 5 variants = 25000 patterns，内存可控
- 内存监控指标暴露在 `/admin/terminology/stats`
- 超规模时降级到 trie + 朴素扫描（牺牲性能换内存）

**风险 4：管理员误操作**

管理员一次性删除大量术语，触发全量 rescan，期间业务受影响。

缓解：
- 术语表批量操作必须经过 admin 二次确认
- rescan 任务支持取消（restore 到 rescan 前的 BM25 state 备份）
- audit log 记录所有术语表变更

**Trade-off：完整 rescan vs 增量 rescan**

完整 rescan 简单但慢（10-30 分钟）。增量 rescan（只更新受新术语影响的 chunk）实现复杂但快（数十秒）。

v1 选完整 rescan：
- 实现简单，可靠性高
- 频率低（管理员每周/每月级别变更），可以容忍延迟
- 增量 rescan 留作后续优化（需要术语版本号 + chunk 级 last_scan_term_version 字段）

## 依赖与衔接

- **被 `rag-intent-routing` 依赖**：intent classifier 输出的 entities 用 terminology 做 normalize；terminology 未上线前 intent classifier 可以原样输出。
- **被 `rag-maintainability-chunker` 依赖**：chunker 在生成 chunk 后调用 `matcher.scan_text` 写 metadata；chunker 未改造前可以由现有 loader 在 post-processing 阶段调用。
- **被 `rag-postprocess-evidence` 依赖**：rerank score fusion 使用 `term_match_count`；confidence gate 使用 `entity_coverage`（基于 metadata.entity_types 计算）。
- **被 `rag-multilevel-fallback` 依赖**：preflight 阶段术语扩展是 fallback Level 0 的必做预处理。

实施时建议：先做 jieba 注入和 query 时扩展（最小可用闭环），再做 chunker 集成和 metadata 写入，最后做 rescan 任务和管理 API。
