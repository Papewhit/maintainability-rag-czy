## 1. 项目级运行身份与数据规则

- [ ] 1.1 指定 intent/FAST、rewrite、answer/judge、embedding、reranker、Milvus/BM25 与本地设备配置
- [ ] 1.2 固定 source/config/model fingerprints 与结果目录
- [ ] 1.3 明确真实文档公开许可、授权或受控执行方式，禁止未授权内容进入仓库/交接包

## 2. 分层 Synthetic Set 与 Real Subset

- [ ] 2.1 构建 synthetic corpus/query/qrels，覆盖 Level 0/1/2/3、filter/boost/none、术语与困难负例
- [ ] 2.2 标注 expected/allowed levels、coverage、allowed answers、forbidden claims、citations 和 fault scenarios
- [ ] 2.3 覆盖 comprehensive partial/Y-Y/baseline-only/no-evidence 与 timeout/degradation
- [ ] 2.4 选定少量真实文档和人工 query/qrels，记录授权、格式、领域与 fingerprint
- [ ] 2.5 划分 development/gate 数据并冻结最终版本

## 3. 真实模型端到端评测

- [ ] 3.1 在 synthetic 与 real-subset 上运行 fallback-disabled、Level 1、Level 2 和完整链路
- [ ] 3.2 保存逐 case plan、trace、final evidence、回答、来源和运行身份
- [ ] 3.3 强制检查 filter、未覆盖禁止回答、scope 披露、来源和关闭兼容路径
- [ ] 3.4 分别计算 Level 分布、改善、来源/覆盖、P50/P95、调用、timeout、budget 与降级指标

## 4. 项目级门槛与 Budget

- [ ] 4.1 基于 development baseline 提出并记录质量、延迟和可靠性门槛
- [ ] 4.2 提出 total/Level 1/Level 2 参考 budget 候选
- [ ] 4.3 冻结 gate 数据和门槛后验证候选；无候选通过则保留原值
- [ ] 4.4 新建 activation validation 报告，声明 `passed|partial|failed`、样本限制和非生产边界

## 5. 协同 Rehearsal 与参考默认值

- [ ] 5.1 确认 comprehensive 运行引用可比身份下的 intent-routing 项目级 passed evidence
- [ ] 5.2 在干净索引显式启用 intent/confidence/fallback，运行固定 synthetic + real smoke rehearsal
- [ ] 5.3 验证 trace、前端 Level 展示、回答边界与显式关闭回滚
- [ ] 5.4 通过后才修改参考开关/budget，并同步 `.env.example`、测试、报告和架构
- [ ] 5.5 运行受影响 unit、integration、E2E、eval 与 documentation validation

## 6. Evidence Disposition Gate

- [ ] New findings classified, or `No new findings` recorded
- [ ] Code, test, review, runtime, or invalidation evidence linked
- [ ] Every confirmed Finding has a durable disposition or evidenced in-place closure
- [ ] Residual risks have durable typed destinations
- [ ] Planned work has an OpenSpec change or issue owner where required
- [ ] ARCHITECTURE impact assessed
- [ ] No undispositioned design ambiguity remains
