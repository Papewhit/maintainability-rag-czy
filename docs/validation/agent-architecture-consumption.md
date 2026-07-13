---
document_type: validation_report
validation_id: VAL-AGENT-ARCH-001
status: passed
scope: documentation.agents
source_commit: 4db940cad6afe6ab8ef7ed5ec567c29d0f1fc928
source_fingerprint: sha256:c0a0a7b547534ae01a45ecafccd03a2bf2652cc0219cc1a8d945e10006ac14b0
executed_at: 2026-07-13T17:19:49+08:00
source_findings: [AGENT-ARCH-F001]
supersedes: []
---

# Agent Architecture Consumption Validation

## Scope

This validation tests whether independent repository agents can discover and
apply architecture and evidence-governance instructions without access to the
design discussion. It covers task routing, workflow selection, documentation
destination, handoff judgments, and treatment of observed evidence.

## Method

Three clean detached Git worktrees were created at source commit
`4db940cad6afe6ab8ef7ed5ec567c29d0f1fc928`. Three agents were launched with
no inherited conversation turns and were instructed to work only in their
assigned worktrees. Prompts described business situations but did not name the
expected governance workflow or destination.

One agent handled two read-only routing scenarios. Two agents handled four
operation scenarios and were allowed to make disposable documentation edits.
No validation agent committed or pushed. Responses and worktree diffs were
captured before all three worktrees were removed through Git worktree
commands.

Each scenario received one point for each rubric dimension:

1. correct authority routing;
2. correct workflow selection;
3. correct artifact destination and document granularity;
4. correct `Architecture impact` and `New Finding` handoff;
5. correct evidence and current/planned status boundary.

The source fingerprint binds the six scenario identifiers/descriptions and
the five rubric dimensions.

## Inputs

| ID | Business scenario | Mode |
| --- | --- | --- |
| A1 | Rename private rerank helpers while preserving signatures, stage order, defaults, trace, and behavior. | Read-only |
| A2 | Prepare an OpenSpec proposal for an unimplemented GPU rerank failure fallback. | Read-only |
| B1 | Assess one uncorroborated report of stale BM25 counts after document deletion outside OpenSpec. | Disposable edits |
| B2 | Add another reproduction path to the existing legacy DOC ingestion limitation. | Disposable edits |
| C1 | Document a confirmed non-OpenSpec parent-cache invalidation defect with no existing governed artifact. | Disposable edits |
| C2 | Handle an equal-date Finding Inbox ordering ambiguity discovered during this OpenSpec change. | Disposable edits |

## Results

| ID | Score | Observed behavior |
| --- | --- | --- |
| A1 | 5/5 | Consulted relevant architecture and code, preserved the documented contract, created no documentation, and reported both handoff judgments as `no`. |
| A2 | 5/5 | Used the OpenSpec workflow, kept the active flow unchanged, represented the feature as planned, and assessed architecture impact as `yes` for the planned boundary. |
| B1 | 5/5 | Created one global `observed + pending` evidence-gap Finding without asserting a defect or work item. |
| B2 | 5/5 | Added reproduction evidence to `KI-RAG-0005` without creating a duplicate Finding or known issue. |
| C1 | 5/5 | Created one typed known issue directly for confirmed, independently resolvable knowledge and skipped the intermediate global Finding. |
| C2 | 5/5 | Created a change-local Finding, updated design/spec/tasks, retained current architecture, and selected ascending Finding ID as the equal-date tie-break. |

Total: **30/30**. All operation agents independently ran the documentation
validator and documentation unit suite successfully in their disposable
worktrees. Inbox output contained only the expected global `observed + pending`
record.

Human-readable behavior was also satisfactory: agents cited the authority or
destination path, explained why documentation was or was not created, and
included the exact handoff labels without treating the generated catalog as an
authority.

## Limitations

- Agent behavior is model-dependent; the bound prompts and rubric make this
  run reproducible as evidence, not deterministic proof for every future
  model.
- C1 used supplied confirmed facts for a disposable scenario rather than a
  production defect claim; its known-issue file was discarded with the
  worktree.
- The validation tested repository-level guidance and documentation choices,
  not application runtime behavior.

## Findings

`AGENT-ARCH-F001` identified that equal verification dates lacked an explicit
tie-break even though output was required to be deterministic. The change now
specifies ascending Finding ID after ascending `last_verified_date`, matching
the implemented selector and new unit coverage.
