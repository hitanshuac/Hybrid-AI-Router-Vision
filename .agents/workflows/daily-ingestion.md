# Daily Data Ingestion Workflow

**Description:** This workflow outlines the sequential steps the agent must follow for routine data ingestion, ensuring that extraction, validation, and loading are handled with maximum fault tolerance.

## Workflow Steps

1. **Initialize Connections & Resources**
   - Boot up the DuckDB connection, strictly enforcing the `duckdb-optimizer` constraints (WAL enabled, memory limits applied).
   - Initialize any necessary HTTP clients for the data source.

2. **Extract Data (Fetch)**
   - Retrieve the raw data from the external API or source system.
   - Employ exponential backoff for transient network errors.

3. **Validate Data (Pydantic)**
   - Pass the raw data through the designated Pydantic schemas.
   - Obey the `data-validation` rule: route any malformed records to a `.parquet` quarantine file in the `data/` directory. Do not halt the pipeline for bad schema matches.

4. **Transform Data**
   - Perform any necessary data cleaning or normalization on the successfully validated records.

5. **Load Data (DuckDB)**
   - Ingest the clean data into DuckDB.
   - Obey the `sql-standards` rule: use idempotent operations (e.g., `INSERT OR REPLACE` or staging tables) to prevent duplicate records upon retries.

6. **Audit & Log**
   - Log the final counts: `total_fetched`, `total_quarantined`, and `total_ingested`.
   - Close the database connection safely to flush the WAL.
