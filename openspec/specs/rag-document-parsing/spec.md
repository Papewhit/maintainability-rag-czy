# rag-document-parsing

文档解析适配层：定义统一的 ParseAdapter 契约，将 DeepDoc 作为 PDF/DOCX 主解析路径，Excel 为独立解析器，通过注册表按扩展名分发。所有解析器返回 ParsedDocument，包含 ParsedBlock 流、ParsedTable 列表、ParsedFigureAnchor 列表及 ParseMeta 元数据。

## Requirements

### Requirement: Parse Adapter 统一契约
所有文档解析器 MUST 实现 `ParseAdapter` 协议，接受文件路径，返回 `ParsedDocument`。ParsedDocument MUST 包含 ParsedBlock 流、ParsedTable 列表、ParsedFigureAnchor 列表，以及解析元数据 ParseMeta。

#### Scenario: PDF 文档解析
- **WHEN** 上传一份 PDF 文档，注册表分发到 DeepDoc adapter
- **THEN** adapter 返回 ParsedDocument，blocks 至少包含一个 heading/paragraph/list_item 类型的块；如有表格或图示，对应 ParsedTable/ParsedFigureAnchor 也被填充

#### Scenario: Excel 文档解析
- **WHEN** 上传一份 XLSX 文档，注册表分发到 Excel parser
- **THEN** adapter 返回 ParsedDocument，blocks 包含每个 sheet 的数据（按表格语义识别）；ParsedDocument.tables 列表至少有一个项

#### Scenario: 不支持的文件类型
- **WHEN** 上传不支持的扩展名（如 .ppt）
- **THEN** 注册表抛出 `UnsupportedFileType` 异常；document_service 标记 document 状态为 `unsupported`

### Requirement: DeepDoc 作为 PDF/DOCX 主路径
DeepDoc SHALL 是 PDF、DOCX、DOC、扫描件解析的唯一主路径，MUST NOT 保留 LangChain PyPDF/Docx2txt 作为外部 fallback。DeepDoc 内部的降级机制（OCR / 版面 / 表格抽取 / 水印抑制）由 DeepDoc 自行管理。

#### Scenario: DeepDoc 解析成功
- **WHEN** DeepDoc 成功解析文档
- **THEN** ParsedDocument.parse_meta 记录 `parse_engine="deepdoc"`、版本号、内部降级路径（如有）、警告列表

#### Scenario: DeepDoc 解析失败
- **WHEN** DeepDoc 抛出无法恢复的异常
- **THEN** document_service 标记文档状态为 `parse_failed`，error 字段记录 DeepDoc 异常信息；不尝试任何外部 fallback parser

### Requirement: 水印过滤是 PDF 解析层职责
水印过滤 MUST 由 DeepDoc 内部完成，MUST NOT 上升到 Normalizer。ParsedBlock 输出的内容 SHALL 已是过滤后的文本。

#### Scenario: 水印过滤统计落到 parse_meta
- **WHEN** PDF 解析完成
- **THEN** ParseMeta 中 `watermark_filter_ratio` 字段记录过滤比例；具体哪些 token 被过滤不在 ParsedBlock 中暴露

#### Scenario: DOCX/Excel 不涉及水印
- **WHEN** 解析 DOCX 或 Excel
- **THEN** ParseMeta 中 `watermark_filter_ratio = 0` 或 null；不报告水印相关警告

### Requirement: ParsedBlock bbox 与 OCR confidence
PDF 来源的 ParsedBlock SHALL 在 DeepDoc 走 OCR 路径时携带 bbox 和 ocr_confidence 字段。DOCX/Excel 来源或 DeepDoc 原生文本路径下的 block 这些字段 MAY 为 null。

#### Scenario: PDF OCR 路径
- **WHEN** 扫描 PDF 经过 OCR
- **THEN** 每个 ParsedBlock 的 bbox 和 ocr_confidence 字段填充；ParseMeta 中 `ocr_confidence_avg` 反映全文均值

#### Scenario: DOCX 原生文本
- **WHEN** 解析 DOCX 原生文本
- **THEN** ParsedBlock.bbox = null、ocr_confidence = null；ParseMeta 标记 `parse_path="native_text"`

### Requirement: 解析元数据持久化
每次文档解析完成后，ParsedDocument.parse_meta MUST 落到 `document_parse_meta` 数据库表，供管理员审计和评测使用。

#### Scenario: 写入 parse_meta
- **WHEN** document_service 完成解析阶段
- **THEN** `document_parse_meta` 表中新增一行，包含 document_id、parse_engine、parse_engine_version、parse_path、watermark_filter_ratio、ocr_confidence_avg、hierarchy_validation_warnings、parse_warnings、parse_duration_ms

#### Scenario: 管理员查询
- **WHEN** 管理员调用 `GET /admin/documents/{id}/parse_meta`
- **THEN** API 返回该文档的完整 parse_meta JSON
