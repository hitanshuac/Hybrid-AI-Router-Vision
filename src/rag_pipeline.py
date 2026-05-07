import os
import glob
import logging

# Setup basic logging for standalone run
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
logger = logging.getLogger("rag_pipeline")

from src.llm_local import get_embedding
from src.vector_store import add_rag_chunks

DOCS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs")

def chunk_text(text, chunk_size=1000, overlap=200):
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks

def ingest_documents():
    logger.info("Starting RAG ingestion process...")
    files = glob.glob(os.path.join(DOCS_DIR, "*.txt")) + glob.glob(os.path.join(DOCS_DIR, "*.md"))
    
    if not files:
        logger.info(f"No documents found in {DOCS_DIR}. Drop some .txt or .md files there!")
        return

    all_chunks = []
    all_embeddings = []
    all_metadatas = []
    all_ids = []

    doc_counter = 0

    for file_path in files:
        filename = os.path.basename(file_path)
        logger.info(f"Processing {filename}...")
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
            
            chunks = chunk_text(text)
            
            for i, chunk in enumerate(chunks):
                emb = get_embedding(chunk)
                if emb:
                    all_chunks.append(chunk)
                    all_embeddings.append(emb)
                    all_metadatas.append({"source": filename, "chunk_index": i})
                    all_ids.append(f"{filename}_chunk_{i}")
            
            doc_counter += 1
        except Exception as e:
            logger.error(f"Failed to process {filename}: {e}")

    if all_chunks:
        add_rag_chunks(all_chunks, all_embeddings, all_metadatas, all_ids)
        logger.info(f"Successfully ingested {doc_counter} documents ({len(all_chunks)} chunks) into ChromaDB.")
    else:
        logger.info("No chunks were created/embedded.")

if __name__ == "__main__":
    ingest_documents()
