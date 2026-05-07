import os
import logging
import chromadb
from chromadb.config import Settings
from src.observability import trace_span

logger = logging.getLogger("vector_store")

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "chroma_db_v2")

# Initialize ChromaDB
try:
    chroma_client = chromadb.PersistentClient(path=DB_DIR, settings=Settings(anonymized_telemetry=False))
    
    # Collections
    cache_collection = chroma_client.get_or_create_collection(name="semantic_cache")
    rag_collection = chroma_client.get_or_create_collection(name="rag_docs")
    logic_collection = chroma_client.get_or_create_collection(name="logic_library")
    
    logger.info(f"ChromaDB initialized at {DB_DIR}")
except Exception as e:
    logger.error(f"Failed to initialize ChromaDB: {e}")
    cache_collection = None
    rag_collection = None
    logic_collection = None

@trace_span("check_cache")
def check_cache(query_embedding):
    if not cache_collection: return None
    try:
        results = cache_collection.query(
            query_embeddings=[query_embedding.tolist() if hasattr(query_embedding, 'tolist') else query_embedding],
            n_results=1
        )
        if results['distances'] and len(results['distances'][0]) > 0:
            # 0.05 distance = 0.95 similarity
            if results['distances'][0][0] < 0.05:
                return results['metadatas'][0][0]['response'], results['metadatas'][0][0]['model']
    except Exception as e:
        logger.error(f"Cache lookup failed: {e}")
    return None

def add_to_cache(query, response, model, embedding):
    if not cache_collection: return
    try:
        cache_collection.add(
            ids=[str(hash(query))],
            embeddings=[embedding.tolist() if hasattr(embedding, 'tolist') else embedding],
            metadatas=[{"response": response, "model": model}],
            documents=[query]
        )
    except Exception as e:
        logger.error(f"Cache storage failed: {e}")

@trace_span("search_rag")
def search_rag(embedding, top_k=2):
    if not rag_collection: return []
    try:
        results = rag_collection.query(
            query_embeddings=[embedding.tolist() if hasattr(embedding, 'tolist') else embedding],
            n_results=top_k
        )
        if results['documents'] and len(results['documents'][0]) > 0:
            return results['documents'][0]
    except Exception as e:
        logger.error(f"RAG search failed: {e}")
    return []

# --- Logic Library (Distillation) ---
def add_logic_trace(query, reasoning, response, embedding):
    if not logic_collection: return
    try:
        logic_collection.add(
            ids=[str(hash(query))],
            embeddings=[embedding.tolist() if hasattr(embedding, 'tolist') else embedding],
            metadatas=[{"reasoning": reasoning, "response": response}],
            documents=[query]
        )
    except Exception as e:
        logger.error(f"Logic storage failed: {e}")

def get_logic_trace(embedding, n_results=1):
    if not logic_collection: return None
    try:
        results = logic_collection.query(
            query_embeddings=[embedding.tolist() if hasattr(embedding, 'tolist') else embedding], 
            n_results=n_results
        )
        if results and results["metadatas"] and len(results["metadatas"][0]) > 0:
            return results["metadatas"][0][0]
    except Exception as e:
        logger.error(f"Logic lookup failed: {e}")
    return None