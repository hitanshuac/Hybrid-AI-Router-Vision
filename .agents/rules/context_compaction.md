# Context Compaction: v2.4.0 Specification

This rule enforces strict token conservation on all conversation payloads transiting the Hybrid AI Router cascade. It eliminates wasteful verbosity, caps history depth, and mandates telemetry persistence.

## 1. Processing Pipeline (Mandatory Order)
All operations execute on a **deep copy** of the inbound messages array. The caller's data must never be mutated.

The 5-step sequence within `src/router.py` is:
1. **Deep Copy** — `copy.deepcopy(messages)` at function entry.
2. **Grounding** — System prompt injected at index 0 (`ground_messages()`). See `router_alignment.md` §1.
3. **Prefix Stripping** — Verbose AI filler removed from `role: assistant` messages (`strip_boilerplate()`).
4. **Sliding Window** — Oldest messages beyond the cap are evicted (`apply_sliding_window()`).
5. **Cascade** — Compacted payload forwarded to `query_cloud()`. Admission Control (PRE-FLIGHT BYPASS) runs inside `llm_cloud.py`.

## 2. Prefix Stripping Rules
- Strip verbose AI conversational filler from `role: assistant` messages **only**.
- The following prefix patterns must be removed if they appear at the start of an assistant message:
  - `"Sure! "`, `"Sure, "`, `"Of course! "`, `"Of course, "`
  - `"Great question! "`, `"That's a great question! "`
  - `"Absolutely! "`, `"Certainly! "`
  - `"I'd be happy to help! "`, `"I'd be happy to help you with that! "`
  - `"Let me help you with that. "`
- Stripping is **prefix-only** and **case-sensitive**. The substantive content after the filler must be preserved verbatim.
- If stripping a prefix would result in an empty string, the original message must be kept intact.
- Multiple matching prefixes on the same message: strip only the **first** (longest) match.

## 3. Sliding Window Limit
- Hard cap: **10 messages** in any outbound payload (including the `role: system` message).
- The `role: system` message at index 0 is **pinned** and never evicted.
- When the payload exceeds 10 messages, retain only the system message + the **most recent 9** conversation messages. All older messages are dropped.

## 4. System Message Immunity
- The `role: system` message injected by `router_alignment.md` is **exempt** from both sliding window eviction and boilerplate stripping.
- It must always occupy index 0 of the outbound payload.

## 5. Observability
- Every compaction event must emit an `INFO`-level log line containing `[CONTEXT COMPACTION]`.
- The log must include:
  - The **before** and **after** message counts (e.g., `"Compacted 24 → 10 messages"`).
  - The number of boilerplate prefixes stripped (e.g., `"Stripped 3 filler prefixes"`).
- If no compaction was necessary (payload already within limits and no boilerplate found), no log line is emitted.

## 6. Telemetry Persistence
- Every request must record compaction metrics to `data/pipeline_metrics.db` (DuckDB).
- Required fields: `raw_tokens`, `compact_tokens`, `tokens_saved`, `savings_pct`, `messages_dropped`, `prefixes_stripped`, `latency_sec`, `tier`.
- The DuckDB connection must follow the DuckDB Optimizer skill directives: WAL mode enabled, memory capped at 256MB.
- Telemetry writes must be non-blocking to the request path — a failed write must not crash the cascade.

---
version: 1.0.0 (Vision Core Amendment)
---

### 7. Multi-Modal Vision Payload Bounding Heuristics
- **Base64 Character Insulation**: Raw image strings must be isolated and ignored during standard text character length divisions (`len(text) // 4`) to prevent artifact length poisoning.
- **Vision Token Proxy Penalty**: When an image is identified in the request messages content list, a static weight of **1,024 tokens** must be cleanly added to the calculated text token payload block.
- **Circuit Breaker Integration**: If the combined (text + proxy vision tokens) count exceeds a destination target model limit (e.g., NVIDIA NIM cap at 4,000 tokens), the router must instantly trigger a `[PRE-FLIGHT BYPASS]` block and forward the payload to a high-capacity tier (e.g., Gemini 2.5 Flash).

---
version: 1.1.0 (Polymorphic Cascade Amendment)
---

### 8. Polymorphic Type Tracking
- **Document Type Telemetry**: Explicitly assert the tracking of `document_classification` tags within the analytical metrics.
- **Cascade Variance**: As part of the Polymorphic Ingestion Cascade (v1.1.0), the engine routes unstructured text (letters/memos) and structured tabular layouts (invoices) differently based on a zero-shot Gemini 2.5 Flash classification.
- **Analytical Metrics**: You must track the classification label (`DocumentType`) returned by the Edge Node in the API JSON response to provide accurate telemetry on layout variance distributions.
