---
document_type: generated_historical_analysis
status: historical
superseded_by: docs/ARCHITECTURE.md
last_verified_commit: 8babe339cda636936c6c0af3c95a99e7c77c2f19
last_verified_date: 2026-07-12
---

> **Historical generated document:** The body below is intentionally not maintained and must not be used as current implementation evidence. See [ARCHITECTURE.md](ARCHITECTURE.md).

# 文档预处理链路与可借鉴 Insights

## 目标

本文档不重复源码逐行解释，而是从工程设计角度总结 `backend/documents/` 相关链路：

- 当前项目的文档预处理链路是如何组织的
- 哪些设计值得在其他 RAG / 企业知识库项目中复用
- 这些设计分别解决什么问题
- 当前实现还存在哪些边界和风险

## 当前链路概览

当前链路的核心目标不是“把文件切块后存库”这么简单，而是把文档预处理做成一条可检索、可分层回升、可诊断的索引流水线。

主流程如下：

1. 管理员通过 `/documents/upload` 上传 PDF / Word / Excel。
2. 路由层对文件名做 basename 规整，阻断路径穿越和异常文件名输入。
3. `DocumentService` 先将文件写入 `.pending-<filename>` 临时文件。
4. `DocumentLoader` 根据文件类型选择解析器，抽取原始文本。
5. Loader 先判断文档形态：
   - 如果标题特征明显，走 structured 模式
   - 否则走 generic 模式
6. Loader 产出两类 chunk：
   - root chunk：章节级或较大语义块
   - leaf chunk：更细粒度、用于召回的块
7. 每个 chunk 在切分时补齐元数据：
   - `chunk_id`
   - `parent_chunk_id`
   - `root_chunk_id`
   - `chunk_level`
   - `page_start` / `page_end`
   - `section_title` / `section_path`
   - `anchor_id`
8. 同时生成一份面向检索的 `retrieval_text`，把正文和结构线索拼接起来。
9. 只有在 loader 成功产出 leaf chunk 后，系统才清理旧索引：
   - 移除旧 BM25 统计
   - 删除 Milvus 中该文件的旧 leaf chunk
   - 删除 PostgreSQL + Redis 中该文件的旧 parent chunk
10. 新索引写入时采用分层落库：
   - parent chunk 写入 `ParentChunkStore`
   - leaf chunk 写入 Milvus，并生成 dense + sparse embedding
11. 检索阶段默认只召回 leaf chunk；当多个兄弟 leaf 同时命中时，再按 `parent_chunk_id` 回升到 parent chunk 作为更完整的上下文。

这条链路本质上是在做三件事：

- 为召回准备高粒度叶子块
- 为上下文恢复准备父块结构
- 为检索质量准备显式结构特征

## 链路拆解

### 1. 上传与安全处理

上传层的设计比较克制，只做三件必要的事：

- 限制允许的文件类型
- 将文件名规整为 basename
- 把业务逻辑委托给 `DocumentService`

这个边界是合理的。路由层不承担文档解析策略，也不直接操作 Milvus / Redis / PostgreSQL。

### 2. 先解析，再替换旧索引

`DocumentService` 的关键处理顺序是：

1. 写 pending 文件
2. 跑 loader
3. 确认生成 leaf chunk
4. 再清理旧索引并替换正式文件

这个顺序很重要。它避免了一个常见问题：新文件本身不可解析时，把旧知识先删掉，导致知识库短暂或永久空洞。

### 3. 文档形态识别先于切分

`DocumentLoader` 不假设所有文档都适合同一套切分规则，而是先做 profile 判断：

- structured：适合制度文档、手册、规程、标准、带章节编号的正文
- generic：适合无明显层级结构的普通文本页

这是当前链路里最值得借鉴的一个点。大量 RAG 项目召回质量一般，不是 embedding 模型不够强，而是预处理层对所有文档“一刀切”。

### 4. structured 模式不是纯语义切分，而是规则驱动的层级切分

当前 structured 模式会识别这类标题或锚点：

- `第X章 / 第X节 / 第X条`
- `1.2 / 1.2.3`
- `一、`
- `（一）`
- `附录A / 附件1`

然后把 section 抽出来：

- section 标题成为结构锚点
- section 正文成为 leaf 切分对象
- section 路径保留为 `section_path`

这不是“高级 NLP”，但在企业制度、设备手册、规范文档里性价比非常高。

### 5. generic 模式是页面兜底

如果文档无法可靠识别结构，就按页切：

- 先切较大的 root chunk
- 再切更小的 leaf chunk

这样做的价值是：即便结构抽取失败，系统仍然能保留“分页 + 层级父子关系”的最小可用检索能力，而不是退化为完全扁平化文本。

### 6. `retrieval_text` 与原始 `text` 分离

这是整个链路的另一个高价值设计。

系统不会简单拿原始正文直接做 embedding，而是单独构造 `retrieval_text`：

- 默认模式 `title_context`
- 可选模式 `raw`
- 可选模式 `title_context_filename`

`retrieval_text` 可能包含：

- 当前标题
- 父标题
- 文件名
- 页码
- 锚点
- 正文内容

这样做的本质是：把对检索有帮助、但正文里不一定重复出现的结构线索，前移到索引阶段显式注入。

### 7. 叶子块和父块分开存

当前系统不是把所有块都塞进 Milvus，而是做了职责拆分：

- leaf chunk 进 Milvus，负责高精度召回
- parent chunk 进 PostgreSQL + Redis，负责后续上下文回升

这比“所有层都向量化后一起召回”更可控：

- 召回池更干净
- ANN 噪音更少
- 上下文恢复逻辑更明确
- 结构化调试更容易做

### 8. 检索阶段默认只看 leaf，命中后再回升 parent

检索侧默认过滤 `chunk_level == LEAF_RETRIEVE_LEVEL`。也就是说，检索入口对高粒度内容更偏好，只有在多个 leaf 共同指向同一 parent 时，才提升到父块。

这是一种比较成熟的“先 precision，再补 recall/context”的策略，而不是在向量召回阶段就把上下文做得过大。

## 值得借鉴的 Insights

下面这些点最值得迁移到其他项目中。

### Insight 1：索引更新要采用“prepare before replace”

可借鉴原则：

- 新文件先准备好
- 新 chunk 先成功生成
- 只有满足最小成功条件，再清理旧索引

它解决的问题：

- 防止坏上传直接破坏线上知识库
- 降低解析器偶发失败的破坏面

适用场景：

- 任何支持文档覆盖上传的知识库系统

### Insight 2：检索文本要独立设计，不要等同于原始正文

可借鉴原则：

- `text` 用于存档和展示
- `retrieval_text` 用于 embedding / sparse / rerank 输入

它解决的问题：

- 标题、页码、文件名等结构信息无法参与召回
- 同系列文档 hard negative 难分
- 编号类查询难命中正确 section

适用场景：

- 手册、制度、标准、产品文档、运维文档

### Insight 3：文档预处理要先分类，再切分

可借鉴原则：

- 不同文档形态，使用不同 chunking 策略

它解决的问题：

- 单一 chunking 策略对结构文档效果差
- 标题密集文档被错误切碎
- 普通文本又被过度结构化

适用场景：

- 混合型知识库，尤其是 PDF / Word 来源复杂的场景

### Insight 4：分层 chunking 的价值不在“多一层”，而在“分工明确”

可借鉴原则：

- 小块负责召回
- 大块负责补全上下文
- 两者不要混成一个索引目标

它解决的问题：

- 大块召回不准
- 小块回答上下文不足
- 同时把大小块都丢进 ANN 导致噪音上升

适用场景：

- 需要同时兼顾精确定位和长答案上下文的问答系统

### Insight 5：父块不一定要进向量库

可借鉴原则：

- 把 parent chunk 看作“结构恢复层”而不是“召回层”

它解决的问题：

- 向量库体积和检索池复杂度膨胀
- 不同粒度 chunk 互相干扰排序

适用场景：

- 有 Redis / PostgreSQL 等补充存储时尤其适合

### Insight 6：规则抽标题和锚点，投入小但收益高

可借鉴原则：

- 在高结构文档里优先利用规则，不必一上来就依赖复杂模型

它解决的问题：

- 章节定位弱
- 条款编号问题召回差
- rerank 缺少结构先验

适用场景：

- 中文制度、合同、招投标文档、设备手册、操作规范

### Insight 7：索引数据模型要为评测和实验预留空间

可借鉴原则：

- 提前设计 `index_profile`
- 不把用户可见 `chunk_id` 和内部实验 profile 强耦合

它解决的问题：

- A/B 实验需要重建整套外部主键
- 评测索引与默认索引互相污染

适用场景：

- 要长期做 RAG 调优、离线评测、版本对照的项目

## 当前实现的边界与不足

这些点同样值得记录，因为它们决定了哪些经验可以直接复用，哪些需要补齐后再复用。

### 1. 当前没有 OCR

当前 PDF 处理依赖文本型 loader。对扫描件、图片型 PDF、低质量复印件，这条链路的提取成功率会明显下降。

借鉴结论：

- 如果目标场景包含大量扫描件，OCR 不是锦上添花，而是基础能力

### 2. 逻辑上预留了 L2，但实际只生成 L1 和 L3

当前数据模型允许 `chunk_level in (1, 2, 3)`，但实际 loader 只产出：

- `1`：root
- `3`：leaf

这说明设计上为更多层级预留了空间，但当前实现仍是两层结构。

借鉴结论：

- 先把两层做好通常比草率上三层更有价值
- 预留扩展位可以有，但不要让模型层级和实际产物脱节太久

### 3. 上传链路不是强事务

当前顺序已经比“先删再解析”稳很多，但仍然存在窗口：

- 旧索引已经删除
- 新文件已经替换
- 后续 parent / leaf 写入如果失败，索引可能不完整

借鉴结论：

- 真正的生产级链路最好补 staging 状态、幂等写入、任务补偿或回滚机制

### 4. 删除只删索引，不删本地源文件

这意味着“知识库删除”和“物理文件删除”不是同一个动作。

借鉴结论：

- 如果项目有审计、回放、重建索引需求，这种分离是合理的
- 如果项目目标是完全删除数据，则还要额外设计源文件生命周期

## 推荐迁移顺序

如果要把这些经验迁移到其他项目，建议按下面顺序做，而不是一次性全部照搬。

### 第一阶段：最低成本高收益

- 引入 `retrieval_text`
- 增加 basename 规整和 pending 文件机制
- 统一 leaf chunk 元数据模型

### 第二阶段：提升结构理解

- 增加 structured / generic 分流
- 增加标题与锚点规则
- 增加 `section_title` / `section_path`

### 第三阶段：完善分层检索

- 引入 parent chunk 独立存储
- 检索只召回 leaf
- 命中后按 parent / root 自动回升上下文

### 第四阶段：生产级增强

- OCR
- 异步索引任务
- 幂等与回滚
- 索引 profile 管理
- 评测与 trace

## 总结

这条文档预处理链路最值得借鉴的，不是某个单点技巧，而是它的整体取向：

- 不把“文件解析”当成单纯 ETL
- 不把“切块”当成孤立步骤
- 不把“向量化”当成唯一索引手段

它把预处理直接设计成检索系统的一部分：切分策略服务于召回，父子关系服务于上下文恢复，`retrieval_text` 服务于 mixed retrieval，`index_profile` 服务于长期演进。

如果只抽象成一句话，这条链路最核心的经验是：

**预处理不是为“存进去”服务，而是为“后续能被稳定、可解释地找回来”服务。**
