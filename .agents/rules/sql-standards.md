# DuckDB SQL Standards

This rule strictly governs all DuckDB operations to guarantee idempotent data ingestion and prevent data duplication during pipeline failures or retries.

## 1. Idempotency is Mandatory
- **Never** use raw `INSERT INTO` statements without conflict resolution.
- All ingestion logic MUST be idempotent. A partial failure and subsequent retry must result in the exact same database state as a single successful run.

## 2. Conflict Resolution
- Use `INSERT OR REPLACE` when the primary keys are strictly defined and replacing the entire row is acceptable.
- For more complex logic, use Staging Tables:
  - Load incoming data into a temporary `staging_table`.
  - Use `INSERT ... ON CONFLICT (id) DO UPDATE SET ...` to merge the staging data into the production table.

## 3. Transactions
- Wrap batch operations in explicit `BEGIN TRANSACTION` and `COMMIT` blocks to ensure atomic writes.

## 4. No Duplicates
- Pipeline retries must never result in duplicate rows under any circumstances.
