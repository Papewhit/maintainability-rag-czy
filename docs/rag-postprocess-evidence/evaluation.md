# RAG 后处理证据链评测报告

## 可复核来源

评测时间为 2026-07-11（Asia/Hong_Kong）。修复前基线使用独立 detached worktree
`06faa1c2a74599656dffcf0b67102f532ba951a3`；当前结果在功能提交 rebase 到最新目标分支后重新生成。
结果同时记录 revision 与三个核心源文件的 versioned canonical SHA-256 指纹，防止基线推进后误用旧产物。
v2 指纹对文件路径和内容做长度分隔，并在 hash 前将 CRLF/CR 规范化为 LF；因此同一源码在
Windows/Linux checkout 中保持稳定，同时仍能覆盖未提交的评测候选代码。

同一冻结入口：

```powershell
.venv\Scripts\python.exe tests\eval\rag\run_postprocess_revision_evaluation.py `
  --repo <baseline-or-current-worktree> --label <label> --pool-size <10|15|20> `
  --output <result.json>
```

| 代码 | revision | source SHA-256 |
| --- | --- | --- |
| baseline | `06faa1c2a74599656dffcf0b67102f532ba951a3` | `d3326768…ca9ea0` |
| current | `8babe339cda636936c6c0af3c95a99e7c77c2f19` | `faf0e2b0…37e6c1` |

机器可读证据为 `baseline-results.json`、`current-pool-{10,15,20}-results.json`；每份都包含
完整 top_k、逐样本质量、revision、指纹版本/规范化/文件清单、源指纹、配置和延迟。基线与当前回归测试原始记录分别为
`baseline-regression.xml` 和 `current-regression.xml`，两边运行相同的实际测试路径：

```powershell
python -m pytest tests/unit/backend/rag/pipeline/test_rag_pipeline.py `
  tests/unit/backend/rag/retrieval/test_rag_utils.py -q --junitxml=<result.xml>
```

两边均为 `33 passed`。OpenSpec 任务中的旧路径 `tests/test_rag_pipeline.py` 在当前测试分类中对应
上述 `tests/unit/backend/rag/pipeline/test_rag_pipeline.py`。

## 冻结维修 gold fixture

冻结集包含 8 个维修查询（seal、pump、bearing、valve、filter、shaft、gasket、impeller），每个
查询有 20 个固定顺序候选、两个同 parent 的维修 leaf、parent 中间步骤和两个相邻 parent。
输入与边界依赖完全相同；评测入口调用各 revision 自己真实的 `_finish_retrieval_pipeline()`，
只替换 CrossEncoder、parent store 和 Milvus 三个外部依赖。它没有手写旧阶段顺序，也没有 mock
auto-merge、step-chain 或 structure-rerank 的输出。

回答质量指标是“证据可回答性”：最终 top_k 覆盖 gold 事实 `prepare / inspect / install` 的比例。
这是答案生成前的确定性代理，不冒充生产答案模型评分。

## 修复前后：相同输入、真实 revision

默认 20 与 baseline 的对照：

| 指标 | baseline | current pool=20 |
| --- | ---: | ---: |
| 平均证据可回答性 | 0.1250 | 0.9167 |
| 完整步骤组 | 0/8 | 6/8 |
| 完整管线 P50 | 0.264 ms | 0.532 ms |
| 完整管线 P95 | 0.384 ms | 0.773 ms |

逐查询 top_k 在两份 JSON 的 `cases[].top_k` 中保存。例如 `seal-basic` 从
`leaf-1, leaf-2, background-3` 变为 `parent-first, parent-last, parent-middle`，质量从 1/3
变为 3/3。当前管线增加 auto-merge 与两跳 step-chain 后，本冻结集 P50/P95 分别增加 0.268 ms
和 0.389 ms；这是模型无关、本机、80 次完整后处理调用的相对开销。

## 10 vs 15 vs 20 paired 结果

三个档位在同一 8 查询冻结集上各运行 10 次（共 80 次完整管线调用）：

| candidate pool | 平均可回答性 | 完整步骤组 | P50 | P95 |
| ---: | ---: | ---: | ---: | ---: |
| 10 | 0.2917 | 2/8 | 0.372 ms | 0.640 ms |
| 15 | 0.5417 | 4/8 | 0.554 ms | 0.829 ms |
| 20 | 0.9167 | 6/8 | 0.532 ms | 0.773 ms |

逐查询 paired win/loss/tie：

- 20 vs 15：`4 / 0 / 4`
- 20 vs 10：`6 / 0 / 2`
- 15 vs 10：`2 / 0 / 6`

此外，真实 chunker 的单组算法评测仍验证从初始 1/3 parent 覆盖补齐到 3/3，completion ratio
为 1.0；多查询端到端冻结集的最终 top_k 完整率以本节的 2/8、4/8、6/8 为准。

## 默认值决定与限制

保留 `RERANK_CANDIDATE_POOL_SIZE=20`：在 paired 冻结集中，相对 15 有 4 胜、0 负、4 平，
完整步骤组增加 2 个；相对 10 有 6 胜、0 负、2 平。该本机微基准存在噪声，因此默认值主要
由 paired 质量收益支撑，延迟只作为风险信号。模型输入成本仍由
`RERANK_INPUT_K_CPU/GPU` 独立限制。

该决定适合作为本 change 的安全默认值，不等同于生产容量结论。冻结集是可重复的维修场景，
但规模只有 8 个且 CrossEncoder/存储为确定性替身；上线前仍需在生产 gold dataset、模型、
Milvus 和答案生成器上复跑 File+Page@5、Chunk@5、Root@5、人工/模型答案质量与端到端 P95。
