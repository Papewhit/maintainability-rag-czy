## 1. 发布候选与评测身份准备

- [ ] 1.1 指定 FAST_MODEL、answer model、judge model、embedding、reranker、Milvus、BM25 与运行设备的发布候选配置
- [ ] 1.2 固定 source commit、versioned source fingerprint、intent dataset/filename registry fingerprint 与配置 fingerprint
- [ ] 1.3 为发布 Milvus corpus/index 建立稳定 fingerprint，并记录语料、collection、index profile 与 BM25 state 身份
- [ ] 1.4 验证真实评测环境不使用测试替身、合成 trace 或开发语料，缺失项作为 blocking evidence 记录

## 2. 真实 Intent Classifier 评测

- [ ] 2.1 使用真实 FAST_MODEL 运行 100 条标注意图数据集，生成绑定模型与 source/config/dataset fingerprint 的报告
- [ ] 2.2 使用真实 judge 计算 intent accuracy、plan validity 与 sub-query quality，并保留失败/超时/降级明细
- [ ] 2.3 审核 filename registry 与发布语料的映射，区分 plan parsing validity 和 release-corpus retrieval evidence

## 3. Comprehensive Paired A/B

- [ ] 3.1 在同一 case ids、源码、配置、数据集、语料和资源环境下运行 `quality_first_v1`
- [ ] 3.2 仅替换 effective profile 为 `eval_no_crossencoder_v1`，运行成对消融
- [ ] 3.3 验证 runner 拒绝不一致 source/config/dataset/corpus fingerprints 或不一致 case ids
- [ ] 3.4 比较生成分支代表率、引用有效性、回答质量、embedding/search calls、rerank pairs、P50/P95、CPU/GPU 峰值、错误/降级率和预算耗尽率

## 4. 阈值与激活证据

- [ ] 4.1 基于首轮可信真实基线提出质量、延迟、资源与可靠性数值阈值，记录制定依据
- [ ] 4.2 评审并冻结阈值；使用冻结阈值执行最终 gate，禁止用确定性替身或同一未隔离样本自证通过
- [ ] 4.3 新建 governed activation validation 报告，绑定运行身份、原始结果位置、阈值和 `passed|partial|failed` 结论
- [ ] 4.4 未通过时确认 `RAG_INTENT_CLASSIFIER_ENABLED=false`，记录阻塞项并停止默认启用工作

## 5. 显式配置灰度

- [ ] 5.1 在灰度前记录 cohort、至少 10% 的起始流量、后续阶段、观察窗口、最低样本量和停止/回滚条件
- [ ] 5.2 保持代码默认 false，仅对灰度 cohort 显式设置 `RAG_INTENT_CLASSIFIER_ENABLED=true`
- [ ] 5.3 每阶段采集 intent 分布、classifier/graph P50/P95、失败/规则降级、分支代表率、检索/rerank 成本、错误/降级和预算耗尽指标
- [ ] 5.4 任一停止条件触发时回滚显式开关、停止扩大流量并记录 governed evidence
- [ ] 5.5 全部灰度阶段通过后，在 activation validation 报告中记录最终结论

## 6. 默认启用

- [ ] 6.1 仅在真实评测与灰度均通过后，将 runtime config 的 intent classifier 默认值改为 true
- [ ] 6.2 同步更新 `.env.example`、默认值契约测试与关闭开关回滚测试
- [ ] 6.3 更新 `docs/ARCHITECTURE.md` 的 feature status、默认行为、验证提交和 activation evidence 链接
- [ ] 6.4 运行受影响的 unit、integration、E2E、eval 与 documentation validation，并将最终证据绑定到实现提交

## 7. Evidence Disposition Gate

- [ ] New findings classified, or `No new findings` recorded
- [ ] Code, test, review, runtime, or invalidation evidence linked
- [ ] Every confirmed Finding has a durable disposition or evidenced in-place closure
- [ ] Residual risks have durable typed destinations
- [ ] Planned work has an OpenSpec change or issue owner where required
- [ ] ARCHITECTURE impact assessed
- [ ] No undispositioned design ambiguity remains
