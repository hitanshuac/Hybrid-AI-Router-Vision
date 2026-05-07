import os
import logging
import chromadb
from chromadb.config import Settings

logger = logging.getLogger("vector_store")

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "chroma_db")

# Initialize ChromaDB
try:
    chroma_client = chromadb.PersistentClient(path=DB_DIR, settings=Settings(anonymized_telemetry=False))
    
    # Collection for Semantic Caching (Routing)
    cache_collection = chroma_client.get_or_create_collection(
        name="semantic_cache",
        metadata={"hnsw:space": "cosine"}
    )
    
    # Collection for RAG Documents
    rag_collection = chroma_client.get_or_create_collection(
        name="rag_docs",
        metadata={"hnsw:space": "cosine"}
    )
    
    logger.info(f"ChromaDB initialized at {DB_DIR}")
except Exception as e:
    logger.error(f"Failed to initialize ChromaDB: {e}")
    cache_collection = None
    rag_collection = None

def add_to_cache(prompt, response, model_label, embedding):
    if not cache_collection: return
    # Use prompt hash as ID
    safe_id = str(hash(prompt))
    try:
        # ChromaDB might throw if ID already exists, so we use upsert or just ignore
        cache_collection.upsert(
            ids=[safe_id],
            embeddings=[embedding],
            documents=[prompt],
            metadatas=[{"response": response, "model": model_label}]
        )
    except Exception as e:
        logger.error(f"Failed to add to cache: {e}")

def check_cache(embedding, threshold=0.95):
    if not cache_collection: return None
    try:
        results = cache_collection.query(
            query_embeddings=[embedding],
            n_results=1
        )
        if results['distances'] and len(results['distances'][0]) > 0:
            # ChromaDB cosine distance: 0 is identical, 1 is orthogonal
            # Similarity = 1 - distance
            distance = results['distances'][0][0]
            similarity = 1.0 - distance
            if similarity >= threshold:
                meta = results['metadatas'][0][0]
                return meta['response'], meta['model'] + " (Chroma Cached)"
    except Exception as e:
        logger.error(f"Failed to check cache: {e}")
    return None

def add_rag_chunks(chunks, embeddings, metadatas, ids):
    if not rag_collection: return
    try:
        rag_collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadatas
        )
        logger.info(f"Added {len(chunks)} chunks to RAG collection.")
    except Exception as e:
        logger.error(f"Failed to add RAG chunks: {e}")

def search_rag(embedding, top_k=2):
    if not rag_collection: return []
    try:
        results = rag_collection.query(
            query_embeddings=[embedding],
            n_results=top_k
        )
        if results['documents'] and len(results['documents'][0]) > 0:
            return results['documents'][0]
    except Exception as e:
        logger.error(f"Failed to search RAG: {e}")
    return []
