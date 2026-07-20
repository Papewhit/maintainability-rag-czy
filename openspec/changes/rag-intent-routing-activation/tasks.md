## 1. 项目级运行身份与数据规则

- [ ] 1.1 指定 FAST_MODEL、answer/judge、embedding、reranker、Milvus/BM25 与本地运行设备配置
- [ ] 1.2 固定 source/config/model fingerprints 与结果目录
- [ ] 1.3 明确真实文档的公开许可、授权或受控执行方式，禁止未授权内容进入仓库/交接包

## 2. 合成集与真实子集

- [ ] 2.1 建设版本化 synthetic corpus、filename registry、query、qrels、困难负例和反事实孪生
- [ ] 2.2 覆盖 70/30 intent 基线、filter/boost/none、四类 granularity 与四类 analysis type
- [ ] 2.3 选定少量真实文档与人工 query/qrels，记录格式、领域、授权和 corpus fingerprint
- [ ] 2.4 划分 development/gate 数据并冻结最终数据版本

## 3. 真实模型 Intent 与 Paired A/B

- [ ] 3.1 用真实 FAST_MODEL 在 synthetic 与 real-subset 上运行 intent evaluator
- [ ] 3.2 计算 intent accuracy、plan validity、sub-query quality，并保留失败/降级明细
- [ ] 3.3 在相同身份下运行 `quality_first_v1` 与 `eval_no_crossencoder_v1`
- [ ] 3.4 验证 paired identity 拒绝逻辑，分别汇总 synthetic/real 指标

## 4. 项目级 Gate 与 Rehearsal

- [ ] 4.1 基于 development baseline 提出并记录质量、P95 与可靠性门槛
- [ ] 4.2 冻结 gate set、真实子集和门槛后执行最终运行
- [ ] 4.3 新建 governed activation validation 报告，声明 `passed|partial|failed` 与非生产边界
- [ ] 4.4 在干净索引执行显式开启/关闭 rehearsal，验证 trace 和回滚

## 5. 参考默认值与文档

- [ ] 5.1 仅在混合 gate 与 rehearsal 通过后修改 intent classifier 参考默认值
- [ ] 5.2 更新 `.env.example`、默认值测试与关闭回滚测试
- [ ] 5.3 更新 `docs/ARCHITECTURE.md` 的项目定位、feature status 和证据链接
- [ ] 5.4 运行受影响 unit、integration、E2E、eval 与 documentation validation

## 6. Evidence Disposition Gate

- [ ] New findings classified, or `No new findings` recorded
- [ ] Code, test, review, runtime, or invalidation evidence linked
- [ ] Every confirmed Finding has a durable disposition or evidenced in-place closure
- [ ] Residual risks have durable typed destinations
- [ ] Planned work has an OpenSpec change or issue owner where required
- [ ] ARCHITECTURE impact assessed
- [ ] No undispositioned design ambiguity remains
