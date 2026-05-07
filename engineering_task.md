# Post-Eval Optimization Roadmap

- [x] **1. VRAM Management (Quantization)**
  - [x] Update `src/llm_local.py` and `src/config.py` to use `gemma2:9b` (Q4 quant) or equivalent.
  - [x] Pull the quantized model via Ollama.
- [x] **2. Traffic Shaping (Rate Limits)**
  - [x] Implement Token Bucket rate limiter in `src/llm_cloud.py`.
  - [x] Add exponential backoff configuration logic.
- [x] **3. Dynamic Calibration (Routing Accuracy)**
  - [x] Create `evals/calibrate.py` to calculate optimal thresholds from `dataset.json`.
  - [x] Update `src/router.py` to load dynamic thresholds from config/registry.
- [x] **4. Semantic Chunking (RAG)**
  - [x] Update `src/rag_pipeline.py` to use recursive text splitting instead of fixed char length.
- [x] **5. Final Verification**
  - [x] Run `eval_runner.py` to verify improvements in latency, accuracy, and rate-limiting.
- [x] **6. Deployment & Version Control**
  - [x] Update `README.md` with System Constraints & Governance.
  - [x] Initialize/Commit changes to Git with structured messages.
  - [x] Tag production release `v1.0.0-enterprise`.
