## ADDED Requirements

### Requirement: 标题层级树构建
Normalizer SHALL attempt 从 ParsedBlock 流中识别标题块并构建层级树。当 DeepDoc 已提供标题结构时 SHALL 只做验证; 当解析层级提取失败时 MUST NOT 阻断分块流程, 至多在 parse_meta 中记录警告并降级到无层级模式。每个非标题 block SHOULD 尽可能标注所属的 section_path 和 section_title。

#### Scenario: 多级标题嵌套
- **WHEN** 文档包含 "第3章 维修" / "3.2 拆卸步骤" / "3.2.1 主减速齿轮箱" 三级标题
- **THEN** NormalizedBlock 中"主减速齿轮箱"小节下的 paragraph block 的 section_path = "第3章 维修 > 3.2 拆卸步骤 > 3.2.1 主减速齿轮箱"

#### Scenario: 无标题文档
- **WHEN** 文档无任何标题块（detected_profile=generic）
- **THEN** 所有 block 的 section_path 为空字符串；section_title 为空；不阻塞分块流程

#### Scenario: 标题层级验证
- **WHEN** Normalizer 检测到层级跳跃（如直接从一级跳到三级）
- **THEN** 在 parse_meta.hierarchy_validation_warnings 中记录警告；不阻断处理；按实际深度继续构建

### Requirement: list_item 识别与 list_group 聚合
Normalizer MUST 识别 ParsedBlock 中的 list_item 块，提取 list_marker（编号文本）和 list_level（嵌套深度），并 SHALL 将连续同级 list_item 聚合为通用 ListGroup。这一层 MUST NOT 包含领域规则。

#### Scenario: 编号列表识别
- **WHEN** ParsedBlock 文本以 "1." "2." "3." 开头
- **THEN** 这些 block 的 block_type 标记为 list_item；list_marker 分别为 "1." "2." "3."；list_level 推断为 1（顶层）；聚合为一个 ListGroup

#### Scenario: 嵌套列表识别
- **WHEN** "1. 顶层步骤" 后跟 "(1) 子步骤 a" "(2) 子步骤 b"
- **THEN** "(1)" 和 "(2)" 的 list_level = 2；属于父 list_item "1." 的子 ListGroup

#### Scenario: 列表中断
- **WHEN** 编号列表中间被一个 paragraph block 打断
- **THEN** 中断前后各自形成独立 ListGroup；不强行合并

### Requirement: figure nearby 双向关联
Normalizer MUST 为每个 ParsedFigureAnchor 建立 nearby_blocks 关联，SHALL 匹配前向和后向的相关 paragraph 或 list_item block。

#### Scenario: 标准 figure caption
- **WHEN** 文档中 figure 紧邻 caption "图 3-2 主轴承装配"
- **THEN** Normalizer 创建 FigureAssociation，figure_id 关联到该 caption block 以及前后窗口内提到 "图 3-2" 的段落

#### Scenario: 跨页 figure
- **WHEN** figure 在第 5 页，caption 在第 6 页开头
- **THEN** 关联跨页生效，nearby_block_ids 包含两页相关 block

#### Scenario: 无明显 caption
- **WHEN** figure 无独立 caption block
- **THEN** Normalizer 用 bbox 距离 + 反向文本引用启发匹配；如果都无命中，nearby_block_ids 为空列表（不报错）

### Requirement: 表格 cells 校验补漏
Normalizer SHALL attempt 校验 ParsedTable.cells_markdown 和 cells_structured 的合理性。DeepDoc 已转换的表格 SHALL 只做验证（记录异常但不修改）；缺失型表格 SHALL 由 Normalizer 兜底转换；不可恢复型表格 SHALL 标记 invalid 并记录 warning。本要求总体定位为"补漏"而非"强制"。

#### Scenario: DeepDoc 已转换表格
- **WHEN** ParsedTable.cells_markdown 非空且 cells_structured 非空
- **THEN** Normalizer 校验行列数一致；如发现异常（如行长度不一致），记录 warning，不修改 cells

#### Scenario: 表格转换缺失
- **WHEN** ParsedTable.cells_markdown 为空但 cells_structured 非空
- **THEN** Normalizer 从 cells_structured 生成 markdown，填充到 cells_markdown

#### Scenario: 完全无效表格
- **WHEN** ParsedTable.cells_markdown 和 cells_structured 都为空或损坏
- **THEN** 在 parse_meta.parse_warnings 中记录；该 table 标记为 invalid，不进入 chunker

### Requirement: NormalizedDocument 输出契约
Normalizer MUST 输出 NormalizedDocument，必须包含原 ParsedDocument、normalized_blocks（带 section/list 信息）、list_groups（聚合后）、figure_associations、heading_tree。

#### Scenario: 字段完整性
- **WHEN** Normalizer 处理完一份 ParsedDocument
- **THEN** 输出 NormalizedDocument 必有上述 5 个字段；list_groups 可为空列表；figure_associations 可为空；heading_tree 至少有 root 节点（即使文档无标题）

#### Scenario: 不修改原 ParsedDocument
- **WHEN** Normalizer 处理 ParsedDocument
- **THEN** 原 ParsedDocument 实例不被修改；NormalizedDocument.parsed 持有原引用（frozen dataclass 保证不可变）
