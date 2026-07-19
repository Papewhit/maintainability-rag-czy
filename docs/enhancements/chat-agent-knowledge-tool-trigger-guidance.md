---
document_type: enhancement
enhancement_id: ENH-RAG-0007
status: candidate
scope: rag.tool_invocation
motivation: Improve knowledge-tool recall for short domain-specific questions by correcting the chat agent's overly strict tool-use guidance before considering control-flow changes.
last_verified_commit: 5e49a4669f78dbaddf00ee97f1f76c7960bba419
last_verified_date: 2026-07-19
source_findings: []
related_issues: []
---

# Chat-agent knowledge-tool trigger guidance

## Opportunity

Evaluate a narrower correction to the Chat Agent system prompt and
`search_knowledge_base` tool description so short, domain-specific terms are
more likely to trigger one knowledge lookup when their meaning is plausibly
private or project-specific.

The current agent was designed as a general chat assistant that can also use a
knowledge base. Its system prompt repeatedly limits search to questions that
"明显依赖" private material and instructs the model not to search when a
question appears answerable as general knowledge. A short term such as
`统一源图是什么？` therefore has no explicit document marker and can be treated
as ordinary knowledge even when the term belongs to the indexed project
document.

Prompt and tool-call guidance are the priority evaluation surface for this
symptom. A deterministic admission router or forced control-flow redesign is
not the first remedy supported by the current evidence.

## Expected Value

- Improve knowledge-tool recall for ambiguous internal terminology without
  forcing RAG for ordinary chat, writing, translation, or general questions.
- Preserve the product's chat-assistant role and existing one-call tool guard.
- Make tool-use failures testable through a small contrast set of internal
  terms, explicit document questions, and genuine general-knowledge queries.

## Non-Goals

This candidate does not introduce an admission router, change
`RagExecutionPolicy`, force all questions through retrieval, add a new runtime
flag, or redefine the multilevel fallback contract. It does not authorize
prompt changes without real-model tool-call evidence.

## Dependencies

- A real-model contrast set containing short internal nouns such as
  `统一源图`, explicit knowledge-base questions, and general terms that should
  remain tool-free.
- Baseline and revised-prompt measurements for tool-call recall, unnecessary
  search rate, answer quality, and latency.
- LangSmith traces that distinguish agent planning, knowledge-tool invocation,
  retrieval, and final answer generation.

## Planning Status

Candidate only. Validate the prompt/tool-description direction before any
control-flow or architecture proposal.
