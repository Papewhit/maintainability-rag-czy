## Why

当前文档处理流程把"解析"和"分块"强绑定在 `DocumentLoader` 中（`backend/documents/loader.py`），存在三个根本问题：

1. **解析能力受限**：用 LangChain 的 PyPDFLoader / Docx2txtLoader / UnstructuredExcelLoader，无 OCR、无版面识别、无表格抽取、无图示锚点。扫描 PDF、含图表的工程文档处理效果差。
2. **分块基于字符数**：`RecursiveCharacterTextSplitter` 用 `chunk_size=500` + 分隔符回退，对维修步骤的编号列表会无声截断（"1. 拆卸 ... 2. 检查"会被切成两个 chunk，破坏步骤链完整性）。
3. **缺乏领域元数据**：chunk metadata 没有 list_group、figure_id、table_id、entity_types 等领域信号；下游 rerank/confidence 没有维修语义信号可用。

设计文档（融合方案 4.4-4.7）要求：
- 解析层引入 DeepDoc 作为上位替代，覆盖 OCR、版面、表格、图示、水印抑制
- 中间引入 Structure Normalizer，把解析结果统一为 ParsedBlock / ParsedTable / ParsedFigureAnchor 流
- 重做 Chunker，按维修性领域规则生成 parent + leaf chunk，保护步骤链完整性，关联图文证据
- 术语标注作为索引时单次扫描（由 `rag-terminology-module` 提供）

## What Changes

把单层的 `DocumentLoader` 重构为三层解耦的处理管线：

```
Parse Adapter → Structure Normalizer → Maintainability Chunker → Index Writer
```

1. **Parse Adapter（解析层）**：
   - **DeepDoc 作为主路径**（PDF/DOCX/DOC，含扫描件），内置降级机制（OCR / 版面 / 表格 / 水印抑制）
   - Excel 走独立 parser（不依赖 OCR/版面）
   - 不保留 PyPDF/Docx2txt 作为外部 fallback（DeepDoc 内部已有降级）
   - 输出统一 `ParsedDocument`，包含 ParsedBlock 流、ParsedTable 列表、ParsedFigureAnchor 列表

2. **Structure Normalizer（结构化层）**：
   - 标题层级树（heading hierarchy）、section_path
   - list_item 识别 + list_marker + list_level（通用结构识别，不带领域）
   - figure caption ↔ nearby_blocks 双向关联建立
   - 表格 markdown / structured cells 验证和补漏（DeepDoc 已做的部分只校验）
   - 输出 `NormalizedDocument`（在 ParsedDocument 基础上加结构化标注）

3. **Maintainability Chunker（领域分块层）**：
   - 在 Normalizer 输出的 list_item 基础上聚合 list_group_id（带领域增强：维修动作词作为边界辅助信号）
   - 生成 parent chunk = 一个 section / 一个完整步骤组 / 一个图示+nearby / 一个参数表+解释段
   - 生成 leaf chunk = parent 内的可检索片段，保留 parent_id / section_path / list_range / table_id / figure_id
   - 步骤保护规则：连续编号列表不在中间硬切；超长步骤组按一级步骤切，子步骤跟父；图示 caption 优先与紧邻步骤同 parent
   - 调用 terminology matcher 写入 entities metadata（依赖 `rag-terminology-module`）

4. **Schema 升级**：
   - Milvus collection 切换到新 `RAG_INDEX_PROFILE`（如 `v4_maintainability`）
   - 新字段：list_group_id / list_order / list_marker / list_level / list_complete / block_type / table_id / table_role / figure_id / figure_role / entity_types / term_match_count
   - 重字段（table_markdown / table_cells / nearby_block_ids / term_matches）进 ParentChunkStore
   - Document 级 parse_meta（水印过滤比、OCR 置信度分布、parser 版本）落 DB 表

**阶段化实施**：

- 阶段 1：list_group 识别 + 步骤保护（最痛点，独立可上线）
- 阶段 2：图文 nearby 关联
- 阶段 3：表格 + 参数表
- 阶段 4：术语标注集成（与 `rag-terminology-module` 衔接）

每阶段都可独立切 profile 发布；前阶段未做的字段在 schema 中保留 null。

## Capabilities

### New Capabilities
- `rag-document-parsing`: Parse Adapter 接口和 DeepDoc/Excel 实现
- `rag-structure-normalization`: ParsedDocument → NormalizedDocument 的结构化层
- `rag-maintainability-chunking`: 维修性领域分块规则和 parent/leaf 生成

### Modified Capabilities
<!-- 现有 openspec/specs/ 无既有 spec -->

## Impact

**代码影响：**
- 新增 `backend/documents/parse_adapter/`：
  - `base.py`：`ParseAdapter` 协议，`ParsedDocument`、`ParsedBlock`、`ParsedTable`、`ParsedFigureAnchor` 数据类
  - `deepdoc.py`：DeepDoc 包装实现（依赖 swxy 提供的 DeepDoc 模块或重新对接）
  - `excel.py`：Excel 专用 parser
  - `registry.py`：按文件扩展名分发到对应 adapter
- 新增 `backend/documents/normalizer/`：
  - `heading_tree.py`：标题层级树构建
  - `list_recognition.py`：list_item / list_marker / list_level 识别
  - `figure_nearby.py`：figure 与 nearby_blocks 双向关联
  - `table_verify.py`：表格 markdown / cells 校验补漏
- 新增 `backend/documents/chunker/`：
  - `maintainability.py`：核心分块逻辑
  - `step_group.py`：步骤组识别和切分规则
  - `figure_chunk.py`：图文 parent chunk 生成
  - `table_chunk.py`：表格 parent chunk 生成
- 删除/弃用 `backend/documents/loader.py` 中的 `RecursiveCharacterTextSplitter` + 标题分块逻辑（转移到新模块）
- 修改 `backend/infra/vector_store/milvus_client.py`：新增 schema 字段，支持新 RAG_INDEX_PROFILE
- 修改 `backend/services/document_service.py`：调用新三层管线
- 数据库新增 `document_parse_meta` 表存 parse engine 元数据
- 新增 `tests/test_parse_adapter.py`、`test_normalizer.py`、`test_maintainability_chunker.py`

**接口影响：**
- 上传文档 API 行为兼容（输入参数不变）；响应中可选增加 `parse_engine` 和 `parse_warnings` 字段
- chunk 检索 API（内部使用）返回更丰富的 metadata；外部 chat API 不破坏现有契约
- 新 `RAG_INDEX_PROFILE` 命名约定：`v4_<feature>`（如 `v4_step_only` / `v4_full`）

**依赖：**
- 新依赖：DeepDoc（需评估 swxy 提供的版本 vs 单独引入）；可能需要 OpenCV、PaddleOCR 等 DeepDoc 子依赖
- 依赖 `rag-terminology-module` 提供的 `terminology_matcher.scan_text()`

**数据迁移：**
- 现有 collection（旧 profile）保留兼容，新文档上传到新 profile
- 提供管理员工具：选定一批历史文档重新跑新管线，索引到新 profile（用于评测对比）
- 默认 profile 切换由部署方控制（环境变量 `RAG_INDEX_PROFILE`）
