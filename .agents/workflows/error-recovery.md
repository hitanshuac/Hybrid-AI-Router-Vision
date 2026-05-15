# Circuit Breaker: Error Recovery Workflow

**Description:** This workflow defines the emergency "Circuit Breaker" protocol for handling severe API rate limiting or upstream outages, preventing endless retry loops and guaranteeing data state consistency.

## Workflow Steps

1. **Monitor API Responses**
   - Track HTTP status codes during the Extract (Fetch) phase.
   - Specifically watch for `429 Too Many Requests` or `503 Service Unavailable`.

2. **Trigger the Circuit Breaker**
   - If the system encounters three (3) consecutive `429` or `503` errors, immediately trip the circuit breaker.
   - Halt all further outbound API requests for the current execution cycle.

3. **Secure the Database State**
   - Trigger an immediate `duckdb-checkpoint` to flush the Write-Ahead Log (WAL) to disk.
   - This ensures that any data ingested prior to the failure is permanently saved and will not be lost.

4. **Graceful Exit**
   - Do not attempt endless retries.
   - Log a critical SRE alert detailing the rate limit failure.
   - Exit the pipeline gracefully with a non-zero status code, leaving the database ready for an idempotent retry once the upstream system recovers.
