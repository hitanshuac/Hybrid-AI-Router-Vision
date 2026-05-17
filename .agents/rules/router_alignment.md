# Router Alignment: Ephemeral Context Grounding

This rule permanently enforces inline payload mutation for all outbound text-model requests in the Hybrid AI Router cascade.

## 1. Mandatory System Prompt Injection
- Every outbound `messages` payload sent to any cascade tier **must** include a `role: system` message at **index 0**.
- The canonical system message is defined in `src/router.py` as the `SYSTEM_GROUNDING_PROMPT` constant.
- No cascade tier is exempt. If a provider cannot accept `role: system`, the grounding text must be prepended as a prefix to the first `role: user` message instead.

## 2. Ephemeral Injection Only
- The system message is injected **at request time** inside the `ground_messages()` function. It is never persisted to disk, database, or session state.
- The original inbound `messages` array from the client must not be mutated. The router must operate on a **deep copy**.

## 3. Content Governance
- The `SYSTEM_GROUNDING_PROMPT` must identify the system as the "Hybrid AI Router" and instruct the downstream model to respond helpfully and concisely.
- Any modification to the prompt content requires a corresponding entry in `retrospective.md` and a version bump.

## 4. Observability
- Every grounding injection must emit an `INFO`-level log line containing `[CONTEXT GROUNDING]` for SRE traceability.
- The log must include the number of messages in the grounded payload.

## 5. Relationship to Context Compaction
- After grounding is applied, the payload must pass through the **Context Compaction** layer defined in [`context_compaction.md`](./context_compaction.md).
- Execution order: **Grounding (this rule)** → **Compaction** → **Admission Control** → **Cascade**.
- The system message injected by this rule is immune to compaction eviction (see `context_compaction.md` §3).
