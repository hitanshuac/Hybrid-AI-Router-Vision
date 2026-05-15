# Pydantic Data Validation Standards

This rule governs the data validation layer using Pydantic, focusing on fault tolerance and isolating bad records without halting the entire pipeline.

## 1. Non-Blocking Validation
- If incoming data violates the defined Pydantic schema, it must **NOT** crash the pipeline or raise an uncaught `ValidationError`.
- The pipeline must continue processing healthy records while safely isolating the malformed data.

## 2. Quarantine Protocol
- Any record that fails Pydantic validation must be caught and routed to a quarantine file.
- Save the bad records in a `.parquet` file located within the `data/` directory (e.g., `data/quarantine_YYYYMMDD.parquet`).
- Include the original payload and the specific validation error message in the quarantine record for manual review.

## 3. Graceful Degradation
- Allow partial batch successes. If a batch contains 90% valid data and 10% invalid data, the 90% must be ingested into DuckDB while the 10% is quarantined.
- Log a warning for SRE teams to review the quarantine file, but do not exit the pipeline with a non-zero status code solely due to validation failures.
