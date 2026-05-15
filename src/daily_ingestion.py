import logging
from ingestion.pipeline import IngestionPipeline

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
)

if __name__ == "__main__":
    pipeline = IngestionPipeline()
    pipeline.run()
