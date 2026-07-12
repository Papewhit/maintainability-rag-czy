## MODIFIED Requirements

### Requirement: Metadata 字段分层存储
术语扫描的结果 MUST 按使用场景分层存储：参与检索/过滤的核心字段 SHALL 进 Milvus（保持定长），完整证据 JSON SHALL 进 ParentChunkStore。

#### Scenario: Milvus 字段
- **WHEN** 索引新 chunk 到 Milvus
- **THEN** Milvus schema 中包含 `entity_types`（VARCHAR）和 `term_match_count`（INT64）；entity_types 序列化为 JSON 字符串数组，长度不超过 512 字节；正常 ingestion 与 rescan MUST 使用同一 encoder

#### Scenario: entity_types 读取兼容
- **WHEN** 检索读取新 JSON 字符串记录或历史 dynamic-field 数组记录
- **THEN** vector-store 适配层将两种表示统一解码为去重后的字符串数组；非法 JSON 或非数组值安全降级为空数组

#### Scenario: ParentChunkStore 字段
- **WHEN** chunk 上传到 ParentChunkStore
- **THEN** 记录中包含 `term_matches`（完整 JSON 数组，每项含 surface/canonical/type/start/end）、`protected_tokens`（多字术语字符串列表）
