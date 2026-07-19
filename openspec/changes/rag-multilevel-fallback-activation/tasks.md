## 1. 发布候选与真实运行身份

- [ ] 1.1 指定 intent/FAST、rewrite、answer、judge、embedding、reranker、Milvus、BM25 与运行设备的发布候选配置
- [ ] 1.2 固定 source commit、versioned source fingerprint、runtime config 与 config fingerprint
- [ ] 1.3 为真实 corpus/Milvus collection/index profile/BM25 state 建立稳定 fingerprint，并记录生成方式与负责人
- [ ] 1.4 验证评测环境不使用测试替身、合成 trace 或非代表性开发语料；任一缺失项记录为 blocking activation evidence

## 2. 分层 Query Set 与标注

- [ ] 2.1 从可用真实语料建立 precise/comprehensive query set，覆盖 Level 0/1/2/3、filter/boost/none、术语变体和 timeout/degradation
- [ ] 2.2 为每个 case 标注预期 plan、scope、路由 level、覆盖维度、允许回答范围、来源要求及质量判断准则
- [ ] 2.3 评审并冻结 query-set 分层比例、最低规模、人工复核流程与 holdout 划分；记录 dataset/annotation/holdout fingerprint
- [ ] 2.4 核实 query set 与 `rag-intent-routing-activation` 的发布语料和模型身份可比，无法对齐的 case 单独分层且不得混入联合结论

## 3. 真实端到端 Fallback 评测

- [ ] 3.1 用真实发布候选依赖运行完整 Level 0→1→2→3 链路，保存逐 case plan、final evidence、trace、回答、来源和运行身份
- [ ] 3.2 对比 fallback-disabled、仅 Level 1、仅 Level 2 与完整链路，保证除显式开关外 source/config/query/corpus/model 身份一致
- [ ] 3.3 对 comprehensive partial/Y-Y/baseline-only/no-evidence 输出执行来源约束和未覆盖禁止回答检查
- [ ] 3.4 对 filter 不越界、boost→none 披露、none 域内放宽、timeout rollback 与默认关闭兼容路径执行强制正确性检查

## 4. 指标、阈值与 Activation 证据

- [ ] 4.1 计算 Level 0 命中率、Level 0/1/2/3 路由比例、Level 1/2 质量增益和 Level 3 触发合理性
- [ ] 4.2 计算来源/覆盖合规率、P50/P95、embedding/search/rerank/LLM 调用量、CPU/GPU/内存峰值、timeout、budget exhaustion、错误与降级率
- [ ] 4.3 基于首轮可信基线提出数值阈值并记录依据；由评审冻结后使用独立 holdout/发布候选执行最终 gate
- [ ] 4.4 新建 governed activation validation 报告，绑定运行身份、query set/holdout、原始结果位置、阈值与 `passed|partial|failed` 结论
- [ ] 4.5 任一强制正确性边界或冻结阈值未通过时确认默认关闭，记录阻塞项并停止激活工作

## 5. 数据驱动预算调优

- [ ] 5.1 基于真实分层基线的质量、P95、timeout 与 budget-exhaustion 分布提出 total/Level 1/Level 2 budget 候选
- [ ] 5.2 使用独立 gate 数据验证每个候选；不得用同一未隔离结果调参并自证通过
- [ ] 5.3 只有同时满足全部正确性、质量、路由、延迟和可靠性阈值的候选才可修改默认 budget；否则保留实现 change 默认值
- [ ] 5.4 若修改 budget，同步 `.env.example`、runtime default、配置迁移说明、契约测试和 activation 报告

## 6. 协同灰度、默认启用与回滚

- [ ] 6.1 确认 comprehensive 发布候选引用同一身份下有效的 `rag-intent-routing-activation` evidence；两个 gate 分别通过
- [ ] 6.2 灰度前冻结 cohort、阶段、观察窗口、最低样本量、停止条件和回滚动作
- [ ] 6.3 保持代码默认关闭，仅对受控 cohort 显式启用所需 intent、confidence 与 fallback 开关
- [ ] 6.4 每阶段采集冻结的质量、路由、P95、资源、错误/降级与预算指标；任一停止条件触发时恢复关闭配置并记录证据
- [ ] 6.5 全部灰度阶段通过后，才可修改 fallback 默认值；同步环境示例、默认值/回滚测试、activation 报告和 `docs/ARCHITECTURE.md`

## 7. Evidence Disposition Gate

- [ ] New findings classified, or `No new findings` recorded
- [ ] Code, test, review, runtime, or invalidation evidence linked
- [ ] Every confirmed Finding has a durable disposition or evidenced in-place closure
- [ ] Residual risks have durable typed destinations
- [ ] Planned work has an OpenSpec change or issue owner where required
- [ ] ARCHITECTURE impact assessed
- [ ] No undispositioned design ambiguity remains
