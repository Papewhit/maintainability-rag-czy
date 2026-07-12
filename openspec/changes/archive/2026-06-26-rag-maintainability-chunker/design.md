> **Durable navigation:** Current behavior is documented in `docs/ARCHITECTURE.md`. The parent/leaf storage contract is in `docs/architecture/decisions/ADR-0001-parent-leaf-evidence-storage.md`. This archived design remains historical change evidence.

## Context

当前 `DocumentLoader` 是个一体化模块，"读文件 → 切 chunk" 一次完成，中间没有可重用的中间结构。在融合方案下要求：

- DeepDoc 取代 LangChain 各 loader 作为主解析器（更强的 PDF/扫描件/表格/图示处理能力，内置降级）
- 解析层、结构化层、分块层职责严格分离，每层有明确的输入输出契约
- 分块层引入维修性领域规则（步骤组保护、图文关联、参数表绑定）
- 索引时调用术语扫描写入 entity metadata（依赖 `rag-terminology-module`）

设计文档（`docs/superpowers/specs/2026-05-20-rag-fusion-design.md` 4.4-4.7）的一些边界没有完全清晰，因为 DeepDoc 内部能力到底覆盖到哪一层（标题树？表头合并？figure caption？）需要看源代码才能精确分离。本次设计明确"软边界"待定项，避免装作已经想清楚。

## Goals / Non-Goals

**Goals：**
- 解析、结构化、分块三层职责清晰，各层契约稳定
- 维修步骤的编号列表不被字符级硬切，跨页步骤组能保持完整证据
- 图文、参数表等高价值证据有专门的 parent chunk 形态
- chunk metadata 中的领域信号供下游 rerank/confidence/scope 使用
- 阶段化上线：每个阶段独立可发布，不强求一次性完整改造

**Non-Goals：**
- 不做自动术语发现（术语注入由 `rag-terminology-module` 提供，且只接受管理员手工注入）
- 不支持 Excel 的复杂版面（合并单元格、嵌套表）—— Excel parser 只保证基本读取
- 不做文档相似性查重（属于业务层，不属于解析/分块）
- 不在 v1 引入文档级关系图谱（设计文档 3.5 节明确这是二期方向）
- 不解决 DeepDoc 部署/打包/CPU/GPU 调度问题（假设 DeepDoc 已就绪，本 change 只对接其输出）

## Decisions

### 决策 1：DeepDoc 作为上位替代，不留 LangChain fallback

替代方案：保留 PyPDFLoader 等作为外部 fallback，DeepDoc 失败时回退。但这会让降级路径不可解释（DeepDoc 内部已经有降级机制，外部再套一层会导致"哪个层级失败了"难以诊断）。

决定：
- Parse Adapter 注册表里只有 DeepDoc（PDF/DOCX/DOC）和 Excel Parser（XLSX/XLS）
- DeepDoc 失败直接报错，由 document_service 标记文档状态为 `parse_failed`，记录 DeepDoc 内部诊断信息
- 用户可通过管理后台重试解析

### 决策 2：三层契约严格分离

```python
# Parse Adapter 输出
@dataclass(frozen=True)
class ParsedBlock:
    block_id: str
    page_no: int
    block_type: Literal["heading", "paragraph", "list_item",
                         "table_caption", "figure_caption", "footnote"]
    text: str
    bbox: tuple[float, float, float, float] | None
    ocr_confidence: float | None
    order_index: int
    style: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class ParsedTable:
    table_id: str
    page_no: int
    caption: str
    cells_markdown: str
    cells_structured: list[list[str]]
    bbox: tuple[float, float, float, float] | None
    nearby_block_ids: list[str]      # DeepDoc 已知的话，否则 normalizer 补

@dataclass(frozen=True)
class ParsedFigureAnchor:
    figure_id: str
    page_no: int
    caption: str
    bbox: tuple[float, float, float, float] | None
    nearby_block_ids: list[str]

@dataclass(frozen=True)
class ParsedDocument:
    filename: str
    file_type: str
    blocks: list[ParsedBlock]
    tables: list[ParsedTable]
    figures: list[ParsedFigureAnchor]
    parse_meta: ParseMeta             # 解析引擎、版本、警告、统计信息

# Structure Normalizer 输出
@dataclass(frozen=True)
class NormalizedBlock(ParsedBlock):
    section_path: str                  # "第3章 > 3.2 维修步骤"
    section_title: str
    anchor_id: str
    list_marker: str | None            # "1." / "(一)" / "①"
    list_level: int | None
    list_item_index: int | None        # 在所属 list_group 中的位置

@dataclass(frozen=True)
class NormalizedDocument:
    parsed: ParsedDocument
    normalized_blocks: list[NormalizedBlock]
    list_groups: list[ListGroup]       # 通用 list_group (Normalizer 已聚合相邻同级 list_item)
    figure_associations: list[FigureAssociation]  # figure_id ↔ nearby blocks (Normalizer 已验证)
    heading_tree: HeadingNode          # 完整标题树

# Chunker 输出
@dataclass(frozen=True)
class MaintenanceChunk:
    chunk_id: str
    parent_chunk_id: str
    root_chunk_id: str
    chunk_level: int
    chunk_role: Literal["root", "leaf"]
    block_type: str
    text: str
    retrieval_text: str
    # 结构信号
    section_title: str
    section_path: str
    anchor_id: str
    page_start: int
    page_end: int
    # 列表/步骤
    list_group_id: str | None
    list_order: int | None
    list_marker: str | None
    list_level: int | None
    list_complete: bool
    # 表格/图示
    table_id: str | None
    table_role: str | None
    figure_id: str | None
    figure_role: str | None
    # 术语（由 terminology 模块写入）
    entity_types: list[str]
    term_match_count: int
    # parent store 携带的重字段（不进 Milvus）
    parent_extras: dict[str, Any] = field(default_factory=dict)
```

每层只接受上一层的输出作为输入；不能跨层引用（例如 chunker 不直接读 ParsedDocument，必须通过 NormalizedDocument）。

### 决策 3：软边界条目（M7 已澄清）

经过 M0-M6 实现，下列能力归属已明确（详见 M7 软边界澄清表）：

| 能力 | 归属层 | 说明 |
|------|--------|------|
| 标题层级构建 | Normalizer (heading_normalizer) | 端口 DocumentLoader 逻辑，DeepDoc 不识别标题 |
| 表头识别合并 | DeepDoc (TSR) + Normalizer (table_normalizer) 验证 | DeepDoc 主导，Normalizer 补漏 |
| 表格 markdown 转换 | DeepDoc (TSR) 主导 + Normalizer (table_normalizer) 兜底 | cells_markdown 已有则跳过，缺失则从 cells_structured 生成 |
| Figure caption 提取 | DeepDoc (Layout) 主导 + Normalizer (figure_normalizer) 关联 | 提取由 adapter 完成，Normalizer 做 nearby 关联 |
| ParsedBlock order_index | Parse Adapter 主导 | DeepDoc 提供 order_index，Normalizer 不做二次排序 |

实施时（已落实）：
- 阶段 1 完成后，组织一次 DeepDoc 源代码 review，把上述条目精确分配到 Parse Adapter 或 Normalizer
- 软边界条目在 design.md 中显式标注（不假装已决定）
- 一旦确定，更新 design.md 并修改对应实现

### 决策 4：水印过滤是 DeepDoc 内部能力，不上升到 Normalizer

设计文档（融合方案 4.5）原本把水印过滤写在 Structure Normalizer。但水印过滤需要的信号（OCR token + bbox + 跨页频率统计）天然属于 PDF 解析层，且：
- 仅 PDF 涉及（DOCX/Excel 无 OCR）
- Normalizer 接收的是文本块流，再做水印过滤会损失 bbox 信息
- DeepDoc 可能已经有水印处理能力（按其设计）

决定：水印过滤在 DeepDoc 内部完成，输出的 ParsedBlock 已是过滤后的内容。Normalizer 和 Chunker 不感知水印。水印过滤统计（filter_ratio）落到 `document.parse_meta`。

### 决策 5：list_group 由 Normalizer + Chunker 共担

讨论时考虑三种方案：A) Normalizer 只识别 list_item，Chunker 聚合 list_group；B) Normalizer 输出完整 list_group；C) 共担。

选 C：
- **Normalizer**：识别 list_item、list_level、list_marker，聚合连续同级 item 为通用 ListGroup（不带领域信号）
- **Chunker**：在通用 ListGroup 上加领域增强（维修动作词作为边界辅助信号，决定 list_group 是否需要在中间切分）

理由：list_item 识别是通用结构问题（所有领域通用），但"动作词作为边界"是领域规则。共担让两层职责清晰。

### 决策 6：figure nearby 双向匹配

设计文档原文是 "figure caption 与前后段落建立 nearby relation"。明确：
- nearby 匹配前向 + 后向（不限于单方向）
- 默认窗口：同页 + bbox 距离 < 阈值 + 文本中包含 "图 x"/"表 x" 反向引用
- Chunker 生成 figure parent chunk 时，caption 前置（在 chunk 文本开头）

### 决策 7：术语标注由 chunker 顺手做，rescan 任务独立

讨论结论：terminology 扫描在 chunking 阶段 inline 做（顺手扫一遍 chunk body，写入 metadata）。术语表更新时由 `rag-terminology-module` 的 rescan 任务负责更新已有 chunk 的 metadata，不重切 chunk。

Chunker 调用接口：
```python
matches = terminology_matcher.scan_text(chunk.retrieval_text)
chunk.entity_types = sorted({m.canonical_type for m in matches})
chunk.term_match_count = len(matches)
chunk.parent_extras["term_matches"] = [m.to_dict() for m in matches]
chunk.parent_extras["protected_tokens"] = [m.surface for m in matches if len(m.surface) >= 2]
```

terminology_matcher 未就绪时（terminology change 未上线前），chunker 跳过此步骤，metadata 留空字段（不影响其他逻辑）。

### 决策 8：阶段化上线策略

- **阶段 1**：list_group 识别 + 步骤保护
  - 最小落地：仅识别 list_item 和聚合 list_group_id，禁止字符级硬切
  - 新 RAG_INDEX_PROFILE = `v4_step_protection`
  - 验收：维修步骤类样本召回不再断步骤
- **阶段 2**：图文 nearby 关联
  - 增量字段：figure_id, figure_role, nearby_block_ids (parent store)
  - 新 profile = `v4_figure_nearby`
- **阶段 3**：表格 + 参数表
  - 增量字段：table_id, table_role, table_markdown (parent store)
  - 新 profile = `v4_table_aware`
- **阶段 4**：术语标注集成
  - 依赖 `rag-terminology-module` 上线
  - 增量字段：entity_types, term_match_count
  - 新 profile = `v4_full`

每阶段都可独立切 profile 发布，下游模块（rerank、confidence）可以条件性使用新字段（缺失时降级到旧行为）。

### 决策 9：Schema 与现有 RAG_INDEX_PROFILE 系统的衔接

当前 `RAG_INDEX_PROFILE` 默认空字符串，profile naming convention 由 `backend/rag/profile_naming.py` 控制。本 change 引入新 profile 名约定：`v4_<phase>`。

向后兼容：
- 旧 profile（v1/v2/v3）保留只读，旧 chunk 继续可查询
- 新文档默认上传到 `RAG_INDEX_PROFILE` 配置的当前 profile（部署方控制）
- 评测时可同时索引到旧和新 profile，对比效果

## Risks / Trade-offs

**风险 1：DeepDoc 集成复杂度**

DeepDoc 来自 swxy 项目，其包结构、依赖（PaddleOCR / OpenCV）、模型权重、CPU/GPU 调度都未在本仓库验证。集成可能耗时远超阶段 1 预期。

缓解：
- 实施前先做 DeepDoc spike：单文件 Python 脚本调通最小 PDF 解析，验证依赖、性能、API
- spike 结果决定是把 DeepDoc 作为子模块嵌入还是包装成独立服务（HTTP API）
- 短期内 Excel 走独立 parser，不阻塞 PDF/DOCX 的 DeepDoc 集成

**风险 2：阶段 1 单独上线收益不明显**

阶段 1 只做 list_group 识别和步骤保护，没有图文/表格/术语支持。如果不切换 profile，旧数据仍是字符切法，"步骤保护"在旧数据上无效；切换 profile 又意味着旧数据要重新索引。

缓解：
- 提供管理员工具：选择"试点文档"重新索引到新 profile
- 评测对比新旧 profile 在维修步骤召回上的差异，量化收益
- 阶段 1 的目标是"让架构骨架立起来"，单纯阶段 1 的业务收益不大但是后续阶段的基础

**风险 3：软边界条目的不确定性**

把"DeepDoc 还是 Normalizer 做表头/figure caption"这类问题留到后续，可能导致两层都实现了同样能力（重复工作）或都没实现（漏掉）。

缓解：
- design.md 显式列出软边界条目
- 每个阶段开工前先 review 当前阶段涉及的软边界，做最小必要的 DeepDoc 源代码阅读
- 软边界条目纳入 change 的 review checklist

**风险 4：Schema 演进**

每阶段都引入新 Milvus 字段，频繁切 profile 会导致 collection 数量膨胀。

缓解：
- profile 命名严格遵循 `v4_<phase>` 约定
- 提供 `openspec` 之外的 profile lifecycle 管理工具（创建/标记 deprecated/删除）
- 阶段 1-4 完成后，rollup 一个稳定 profile `v4_stable`，作为长期默认

**Trade-off：DeepDoc 内嵌 vs HTTP 服务**

DeepDoc 内嵌：实现简单，进程内调用，无网络开销
- 缺点：DeepDoc 的 OCR 模型权重大（几百 MB），加载时间长，影响主服务启动
- 缺点：CPU/GPU 资源与主服务共享，需要协调

DeepDoc 作为 HTTP 服务：解耦清晰，可独立扩缩容
- 缺点：增加部署复杂度（多一个服务）、网络延迟
- 缺点：本仓库是单体 FastAPI，引入新服务改变架构

v1 倾向内嵌，理由：项目规模未到必须微服务化的程度，运维成本低。如果 DeepDoc 加载导致主服务启动慢，再考虑独立服务。

## 依赖与衔接

- **依赖 `rag-terminology-module`**：terminology_matcher API；未就绪前 chunker 跳过术语扫描步骤
- **被 `rag-intent-routing` 受益**：意图分类不阻塞 chunker，但 intent 中的 entities 与 chunk metadata 的 entity_types 共享术语规范
- **被 `rag-postprocess-evidence` 严格依赖**：EvidenceBuilder 的 step_chain_check 依赖 list_group_id / list_order；图文证据合并依赖 figure_id / nearby_block_ids；表格证据合并依赖 table_id
- **被 `rag-multilevel-fallback` 间接依赖**：Level 2 scope relax 利用 entity_types 做精确 → 模糊降级

实施顺序建议：阶段 1（step protection）可独立先行；阶段 2-3 可与 evidence change 协同推进；阶段 4 等 terminology change 上线后再做。

## M7 软边界澄清（2026-06-18）

经过 M0-M6 实现，以下归属已明确：

| 能力 | 归属层 | 说明 |
|------|--------|------|
| 标题树构建 | Normalizer (heading_normalizer) | 端口 DocumentLoader._build_structured_chunks |
| 列表检测 | Normalizer (list_normalizer) | 通用层，无领域信号 |
| 维修动作词边界 | Chunker (step_chunker) | 领域信号，可选启用 |
| 图文关联 | Normalizer (figure_normalizer) + Chunker (_chunk_figure) | 两层协作 |
| 表格校验+兜底 | Normalizer (table_normalizer) | Markdown fallback |
| 参数表识别 | converters.py (_detect_parameter_table) | 启发式，无需额外 Normalizer pass |
| 术语扫描 | converters.py (_scan_terminology_on_chunks) | 后置处理，接入 TerminologyTable |
| 水印过滤 | Parse Adapter (DeepDoc) | 由 _filter_forpages 处理，Normalizer 不重复 |
| figure caption 关联 | Normalizer (figure_normalizer) | bbox proximity + text reference |

已移除的设计模糊条目：无。所有此前标注 "待 DeepDoc 源代码核对" 的能力已在实现中明确归属。

## M8 补全项（2026-06-25）

经 Codex 最终审查，M0-M7 实现中遗留两项未完成能力，现补全设计并实施。

### M8.1 Table Nearby 关联策略

**问题：** design.md § 决策 2 中 `ParsedTable.nearby_block_ids` 字段已定义，但 DeepDoc adapter 输出时未填充，table_normalizer 也无 nearby 关联逻辑。导致表格 parent chunk 缺失解释段落。

**归属层：** Normalizer (`table_nearby.py`) 新增 `associate_nearby_blocks` 函数，与 `figure_normalizer` 平行。

**算法（保守版本）：**
1. **bbox proximity：** 同页垂直距离 ≤ 150 doc units（比 figure 的 200 更严格，表格通常紧贴文本）
2. **text reference：** 在 ±3 个 block 窗口内搜索 "表 x" / "Table x" 反向引用（比 figure 的 ±4 更小）
3. **跨页策略：** 表格跨页时，caption 所在页为锚定页，±1 页内的引用段有效
4. **优先级：** bbox proximity > text reference > caption 前置 block

**调用时机：** `normalizer/pipeline.py` 中 `validate_and_enrich_tables()` 之后、返回 `NormalizedDocument` 之前。

**Chunker 使用：** `converters.py` 构造 table parent chunk 时（95-98 行），按 `nearby_block_ids` 顺序拼接解释段：
```python
parent_text = caption + "\n" + nearby_texts + "\n" + table_markdown
```

**Parent store 保留：** `nearby_block_ids` 写入 `parent_extras`，供 evidence builder 使用。

### M8.2 ParseMeta 扩展字段：OCR Confidence + Parse Path

**问题：** 
- `ParseMeta.ocr_confidence_avg` 字段已定义但未填充（DeepDoc OCR 模块返回 score，但 adapter 丢弃）
- `ParseMeta.parse_path` 字段缺失，无法区分原生文本 vs OCR 路径

**parse_path 字段定义：**

允许值（枚举）：
- `"native_text"` — DOCX、Excel 等原生格式，或 PDF 中的可选中文本
- `"ocr"` — 扫描 PDF 经 OCR 识别
- `"mixed"` — PDF 同时包含原生文本和 OCR 区域
- `"unknown"` — 无法判断（降级行为）

**判断算法（PDF）：**
```python
if not blocks:
    parse_path = "unknown"
else:
    known_blocks = [b for b in blocks if b.style.get("parse_sources")]
    if not known_blocks:
        parse_path = "unknown"
    else:
        ocr_blocks = [
            b for b in known_blocks
            if "ocr" in b.style.get("parse_sources", [])
        ]
        ocr_ratio = len(ocr_blocks) / len(blocks)
        if ocr_ratio >= 0.8:
            parse_path = "ocr"
        elif ocr_ratio <= 0.2:
            parse_path = "native_text"
        else:
            parse_path = "mixed"
```

**OCR confidence 数据来源：**
- `_ocr.py:598` 的 `recognize()` 方法内部获取 `(text, score)`，但当前只返回 `text`（604行）
- 修改为返回元组 `(text, score)`，向后兼容：score < drop_score 时返回 `("", 0.0)`
- `_pdf_parser.py:362` 调用 `recognize()` 接收 `(text, score)`，存入 `b["score"]`
- pdfplumber 原生文本 block 标记 `parse_source="native_text"`，`score=1.0`
- OCR 识别 block 标记 `parse_source="ocr"`，携带 OCR score
- `adapter._convert_text_blocks()` 从 tag 提取 `score` 和 `parse_source`；仅 OCR block 写入 `ParsedBlock.ocr_confidence`
- `adapter._parse_pdf()` 基于转换后的 `ParsedBlock` 计算 `parse_path` 和 `ocr_confidence_avg`，避免 parser.boxes 与 blocks 计数不一致

**DOCX/Excel 路径：** `parse_path = "native_text"`，`ocr_confidence_avg = None`

**降级行为：**
- 如果 OCR 模块不返回置信度，`ocr_confidence` 保持 `None`，记录 warning：`"OCR confidence not available"`
- 如果无法区分 native/OCR，`parse_path = "unknown"`，记录 warning：`"Cannot determine parse path"`

**Schema 变更：**
- `ParseMeta` 添加 `parse_path: str | None = None`
- `DocumentParseMeta` 表添加列 `parse_path VARCHAR(20) NULL`
- Admin API `/admin/documents/{document_id}/parse_meta` 返回中添加 `parse_path` 字段

**实施原则：** 最小修改，不引入新依赖，不修改 DeepDoc 底层模型逻辑（只改 Python 包装层）。
