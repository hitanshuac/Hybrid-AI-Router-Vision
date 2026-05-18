import os
import time
import asyncio
import logging
import duckdb
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Union
import datetime
import pandas as pd
import json

from src.router import classify_and_route
from src.health import provider_statuses, stats, health_ping_loop
from src.schemas import InvoiceIngress, ExtractedInvoice, DocumentType
from src.vision_client import classify_and_extract_document
from src.anomaly import analyze_document_anomalies

logger = logging.getLogger("server")


# ============================================================
# Egress Formatter — v2.5.1
# ============================================================
def dict_to_markdown_table(data: dict) -> str:
    """Converts a flat dictionary into a GFM Markdown table for spreadsheet pasting.
    Extracts nested list-of-dicts into separate tables appended below."""
    main_lines = ["| Key | Value |", "|---|---|"]
    extra_tables = []
    
    for key, val in data.items():
        formatted_key = key.replace('_', ' ').title()
        
        if isinstance(val, list) and len(val) > 0 and isinstance(val[0], dict):
            # Extract nested list of dicts into its own table
            extra_tables.append(f"\n#### {formatted_key}\n")
            
            # Extract headers from the first item
            headers = list(val[0].keys())
            header_row = "| " + " | ".join(h.replace('_', ' ').title() for h in headers) + " |"
            separator_row = "|" + "|".join("---" for _ in headers) + "|"
            
            extra_tables.append(header_row)
            extra_tables.append(separator_row)
            
            for item in val:
                row = []
                for h in headers:
                    cell_val = item.get(h, "")
                    if not isinstance(cell_val, (str, int, float, bool)):
                        cell_val = str(cell_val).replace("\n", " ")
                    row.append(str(cell_val))
                extra_tables.append("| " + " | ".join(row) + " |")
                
            main_lines.append(f"| **{formatted_key}** | *See {formatted_key} table below* |")
        else:
            if isinstance(val, list):
                v_str = "<br>".join(str(i) for i in val)
            elif not isinstance(val, (str, int, float, bool)):
                v_str = str(val).replace("\n", " ")
            else:
                v_str = str(val)
            main_lines.append(f"| **{formatted_key}** | {v_str} |")
            
    result = "\n".join(main_lines)
    if extra_tables:
        result += "\n" + "\n".join(extra_tables)
    return result


def _should_log_telemetry(messages: list) -> bool:
    """Detects and isolates automated frontend requests (e.g. Open WebUI auto-title) from telemetry."""
    if not messages:
        return True
    last_msg = messages[-1].get("content", "") if isinstance(messages[-1], dict) else ""
    if not isinstance(last_msg, str):
        return True
    last_lower = last_msg.lower()
    title_signatures = [
        "generate a title",
        "summarize this conversation in a few words",
        "create a concise title",
        "generate a concise",
    ]
    for sig in title_signatures:
        if sig in last_lower:
            return False
    return True

app = FastAPI(title="Hybrid AI Router Vision API")

# ============================================================
# DuckDB Telemetry — v2.6.0
# ============================================================
_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(_DB_DIR, exist_ok=True)
_DB_PATH = os.path.join(_DB_DIR, "pipeline_metrics.db")

def _init_metrics_db():
    """Initialize the DuckDB metrics database with WAL mode and memory cap."""
    try:
        con = duckdb.connect(_DB_PATH)
        con.execute("PRAGMA memory_limit='256MB'")
        con.execute("CREATE SEQUENCE IF NOT EXISTS compaction_log_id_seq START 1")
        con.execute("""
            CREATE TABLE IF NOT EXISTS compaction_log (
                id INTEGER PRIMARY KEY DEFAULT(nextval('compaction_log_id_seq')),
                timestamp TEXT NOT NULL,
                raw_tokens INTEGER NOT NULL,
                compact_tokens INTEGER NOT NULL,
                tokens_saved INTEGER NOT NULL,
                savings_pct REAL NOT NULL,
                messages_dropped INTEGER NOT NULL,
                prefixes_stripped INTEGER NOT NULL,
                latency_sec REAL NOT NULL,
                tier TEXT NOT NULL
            )
        """)
        con.execute("DROP TABLE IF EXISTS invoice_ledger")
        con.execute("""
            CREATE TABLE invoice_ledger (
                document_id VARCHAR PRIMARY KEY,
                invoice_number VARCHAR,
                vendor_name VARCHAR,
                grand_total DOUBLE,
                is_anomaly BOOLEAN,
                flags TEXT,
                extracted_json TEXT,
                latency_sec DOUBLE,
                timestamp TIMESTAMP
            )
        """)
        con.close()
        logger.info("[TELEMETRY] DuckDB metrics database initialized at %s", _DB_PATH)
    except Exception as e:
        logger.warning(f"[TELEMETRY] Failed to initialize metrics DB: {e}")

def _record_compaction_metrics(metrics: dict, latency: float, tier: str):
    """Persist one compaction telemetry row. Non-blocking — failures are logged, not raised."""
    try:
        con = duckdb.connect(_DB_PATH)
        con.execute(
            """
            INSERT INTO compaction_log (id, timestamp, raw_tokens, compact_tokens, tokens_saved,
                                        savings_pct, messages_dropped, prefixes_stripped, latency_sec, tier)
            VALUES (nextval('compaction_log_id_seq'), ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                time.strftime("%Y-%m-%dT%H:%M:%S"),
                metrics.get("raw_tokens", 0),
                metrics.get("compact_tokens", 0),
                metrics.get("tokens_saved", 0),
                metrics.get("savings_pct", 0.0),
                metrics.get("messages_dropped", 0),
                metrics.get("prefixes_stripped", 0),
                round(latency, 4),
                tier,
            ],
        )
        con.close()
    except Exception as e:
        logger.warning(f"[TELEMETRY] Failed to record metrics: {e}")

_init_metrics_db()

def _init_unstructured_ledger():
    """Idempotently handles text data schemas using separate analytical ledgers."""
    try:
        with duckdb.connect(_DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS letter_ledger (
                    document_id VARCHAR PRIMARY KEY,
                    sender_entity VARCHAR,
                    recipient_entity VARCHAR,
                    subject_line VARCHAR,
                    semantic_intent VARCHAR,
                    urgency_score INTEGER,
                    latency_sec DOUBLE,
                    timestamp TIMESTAMP
                )
            """)
        logger.info("[TELEMETRY] letter_ledger initialized")
    except Exception as e:
        logger.warning(f"[TELEMETRY] Failed to initialize letter_ledger DB: {e}")

_init_unstructured_ledger()


# --- STARTUP: Launch background health pings ---
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(health_ping_loop())
    logger.info("Background health monitor started.")


# --- PREMIUM DASHBOARD ---
@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
def get_dashboard():
    from src.config import GROQ_API_KEYS, OPENROUTER_API_KEYS, NVIDIA_API_KEYS

    # Fetch initial context compaction telemetry from DuckDB
    tokens_saved = 0
    compaction_ratio = 0.0
    active_tier = "N/A"
    pipeline_latency = 0.0
    try:
        con = duckdb.connect(_DB_PATH, read_only=True)
        row = con.execute("""
            SELECT 
                COALESCE(SUM(tokens_saved), 0) AS total_saved,
                COALESCE(ROUND(AVG(savings_pct), 1), 0.0) AS avg_ratio
            FROM compaction_log
        """).fetchone()
        
        last_tier_row = con.execute("""
            SELECT tier FROM compaction_log ORDER BY id DESC LIMIT 1
        """).fetchone()
        
        try:
            pipeline_row = con.execute("""
                SELECT COALESCE(ROUND(AVG(latency_sec), 2), 0.0) FROM invoice_ledger
            """).fetchone()
            if pipeline_row:
                pipeline_latency = float(pipeline_row[0])
        except duckdb.CatalogException:
            # Handle case where invoice_ledger table schema hasn't updated yet or table doesn't exist
            pass
            
        con.close()
        if row:
            tokens_saved = int(row[0])
            compaction_ratio = float(row[1])
        if last_tier_row:
            active_tier = last_tier_row[0]
    except Exception as e:
        logger.warning(f"[TELEMETRY] Failed to fetch dashboard telemetry: {e}")

    tokens_saved_str = f"{tokens_saved:,}"
    compaction_ratio_str = f"{compaction_ratio:.1f}%"


    # Build provider status cards
    provider_cards = ""
    for pid, ps in provider_statuses.items():
        if ps.status == "up":
            badge_bg = "rgba(34, 197, 94, 0.2)"
            badge_color = "#4ade80"
            icon = "&#x2705;"
            status_text = f"{ps.latency_ms}ms"
        elif ps.status == "down":
            badge_bg = "rgba(239, 68, 68, 0.2)"
            badge_color = "#f87171"
            icon = "&#x274C;"
            status_text = ps.error or "Down"
        else:
            badge_bg = "rgba(234, 179, 8, 0.2)"
            badge_color = "#fbbf24"
            icon = "&#x23F3;"
            status_text = "Checking..."

        ago = ""
        if ps.last_checked > 0:
            secs = int(time.time() - ps.last_checked)
            if secs < 60:
                ago = f"{secs}s ago"
            else:
                ago = f"{secs // 60}m ago"

        provider_cards += f"""
            <div class="provider-card">
                <div class="provider-header">
                    <span class="provider-icon">{icon}</span>
                    <span class="provider-name">{ps.name}</span>
                </div>
                <div class="provider-status" style="background:{badge_bg}; color:{badge_color};">{status_text}</div>
                <div class="provider-ago">{ago}</div>
            </div>
        """

    # Stats
    success_rate = 0
    if stats.total_requests > 0:
        success_rate = round((stats.successful / stats.total_requests) * 100, 1)

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Hybrid AI Router Vision | Dashboard</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
        <style>
            :root {{
                --bg: #0a0e1a;
                --surface: #111827;
                --card: #1e293b;
                --border: rgba(255,255,255,0.08);
                --primary: #38bdf8;
                --accent: #818cf8;
                --success: #4ade80;
                --danger: #f87171;
                --warn: #fbbf24;
                --text: #f1f5f9;
                --text-muted: #94a3b8;
            }}
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                background: var(--bg);
                color: var(--text);
                font-family: 'Inter', -apple-system, sans-serif;
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 2rem;
            }}
            .dashboard {{
                width: 100%;
                max-width: 720px;
            }}
            .header {{
                text-align: center;
                margin-bottom: 2rem;
            }}
            .status-pill {{
                display: inline-flex;
                align-items: center;
                gap: 0.4rem;
                padding: 0.4rem 1rem;
                background: rgba(34, 197, 94, 0.15);
                color: var(--success);
                border-radius: 2rem;
                font-size: 0.8rem;
                font-weight: 600;
                letter-spacing: 0.05em;
                text-transform: uppercase;
                margin-bottom: 1rem;
            }}
            .status-pill .dot {{
                width: 8px;
                height: 8px;
                border-radius: 50%;
                background: var(--success);
                animation: pulse 2s infinite;
            }}
            @keyframes pulse {{
                0%, 100% {{ opacity: 1; }}
                50% {{ opacity: 0.4; }}
            }}
            h1 {{
                font-size: 2rem;
                font-weight: 700;
                background: linear-gradient(135deg, var(--primary), var(--accent));
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
                margin-bottom: 0.25rem;
            }}
            .subtitle {{
                color: var(--text-muted);
                font-size: 0.9rem;
            }}

            /* Stats Row */
            .stats-row {{
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 1rem;
                margin-bottom: 1.5rem;
            }}
            .stat-card {{
                background: var(--card);
                border: 1px solid var(--border);
                border-radius: 1rem;
                padding: 1.25rem;
                text-align: center;
                transition: transform 0.2s, box-shadow 0.2s;
            }}
            .stat-card:hover {{
                transform: translateY(-2px);
                box-shadow: 0 8px 25px rgba(0,0,0,0.3);
            }}
            .stat-val {{
                font-size: 1.75rem;
                font-weight: 700;
                color: var(--primary);
                line-height: 1;
                margin-bottom: 0.35rem;
            }}
            .stat-label {{
                font-size: 0.75rem;
                color: var(--text-muted);
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }}

            /* Section */
            .section-title {{
                font-size: 0.75rem;
                color: var(--text-muted);
                text-transform: uppercase;
                letter-spacing: 0.1em;
                margin-bottom: 0.75rem;
                padding-left: 0.25rem;
            }}

            /* Provider Grid */
            .provider-grid {{
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 0.75rem;
                margin-bottom: 1.5rem;
            }}
            .provider-card {{
                background: var(--card);
                border: 1px solid var(--border);
                border-radius: 0.875rem;
                padding: 1rem;
                transition: transform 0.2s, box-shadow 0.2s;
            }}
            .provider-card:hover {{
                transform: translateY(-2px);
                box-shadow: 0 8px 25px rgba(0,0,0,0.3);
            }}
            .provider-header {{
                display: flex;
                align-items: center;
                gap: 0.5rem;
                margin-bottom: 0.5rem;
            }}
            .provider-icon {{ font-size: 1rem; }}
            .provider-name {{
                font-weight: 600;
                font-size: 0.9rem;
            }}
            .provider-status {{
                display: inline-block;
                padding: 0.2rem 0.6rem;
                border-radius: 1rem;
                font-size: 0.75rem;
                font-weight: 600;
            }}
            .provider-ago {{
                font-size: 0.7rem;
                color: var(--text-muted);
                margin-top: 0.4rem;
            }}

            /* Key Pool */
            .key-grid {{
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 0.75rem;
                margin-bottom: 2rem;
            }}
            .key-card {{
                background: var(--card);
                border: 1px solid var(--border);
                border-radius: 0.875rem;
                padding: 1rem;
                text-align: center;
            }}
            .key-val {{
                font-size: 1.5rem;
                font-weight: 700;
                color: var(--accent);
            }}
            .key-label {{
                font-size: 0.7rem;
                color: var(--text-muted);
                text-transform: uppercase;
                letter-spacing: 0.05em;
                margin-top: 0.2rem;
            }}

            footer {{
                text-align: center;
                color: var(--text-muted);
                font-size: 0.75rem;
                opacity: 0.6;
            }}

            /* Auto-refresh animation */
            .refresh-bar {{
                height: 2px;
                background: linear-gradient(90deg, transparent, var(--primary), transparent);
                border-radius: 1px;
                margin-bottom: 1.5rem;
                animation: sweep 30s linear infinite;
            }}
            @keyframes sweep {{
                0% {{ background-position: -200% center; }}
                100% {{ background-position: 200% center; }}
            }}
        </style>
        <meta http-equiv="refresh" content="30">
    </head>
    <body>
        <div class="dashboard">
            <div class="header">
                <div class="status-pill"><span class="dot"></span> System Active</div>
                <h1>Hybrid AI Router Vision</h1>
                <p class="subtitle">Polymorphic Vision Engine v2.6.0</p>
            </div>

            <div class="refresh-bar"></div>

            <div class="section-title">Request Statistics</div>
            <div class="stats-row">
                <div class="stat-card">
                    <div class="stat-val">{stats.total_requests}</div>
                    <div class="stat-label">Total Requests</div>
                </div>
                <div class="stat-card">
                    <div class="stat-val">{stats.last_latency:.1f}s</div>
                    <div class="stat-label">Router Latency</div>
                </div>
                <div class="stat-card">
                    <div class="stat-val">{pipeline_latency:.1f}s</div>
                    <div class="stat-label">Vision Latency</div>
                </div>
            </div>

            <div class="section-title">Compaction & Telemetry</div>
            <div class="stats-row">
                <div class="stat-card">
                    <div id="metric-tokens-saved" class="stat-val">{tokens_saved_str}</div>
                    <div class="stat-label">Tokens Saved</div>
                </div>
                <div class="stat-card">
                    <div id="metric-compaction-ratio" class="stat-val">{compaction_ratio_str}</div>
                    <div class="stat-label">Compaction Ratio</div>
                </div>
                <div class="stat-card">
                    <div id="metric-active-tier" class="stat-val" style="color: var(--accent);">{active_tier}</div>
                    <div class="stat-label">Active Tier</div>
                </div>
            </div>

            <div class="section-title">Provider Health</div>
            <div class="provider-grid">
                {provider_cards}
            </div>

            <div class="section-title">Key Pool</div>
            <div class="key-grid">
                <div class="key-card">
                    <div class="key-val">{len(GROQ_API_KEYS)}</div>
                    <div class="key-label">Groq Keys</div>
                </div>
                <div class="key-card">
                    <div class="key-val">{len(OPENROUTER_API_KEYS)}</div>
                    <div class="key-label">OpenRouter Keys</div>
                </div>
                <div class="key-card">
                    <div class="key-val">{len(NVIDIA_API_KEYS)}</div>
                    <div class="key-label">NVIDIA Keys</div>
                </div>
            </div>

            <footer>End-to-End Resilience &bull; Port 8001 &bull; Auto-refreshes every 30s</footer>
        </div>
        <script>
            async function updateCompactionMetrics() {{
                try {{
                    const response = await fetch('/api/v1/metrics/efficiency', {{
                        headers: {{ 'Accept': 'application/json' }}
                    }});
                    if (response.ok) {{
                        const data = await response.json();
                        const summary = data.summary;
                        const recent = data.recent;
                        
                        // Format tokens with commas
                        const totalSaved = summary.total_tokens_saved;
                        document.getElementById('metric-tokens-saved').innerText = Number(totalSaved).toLocaleString();
                        
                        // Format compaction ratio
                        const avgRatio = summary.avg_savings_pct;
                        document.getElementById('metric-compaction-ratio').innerText = avgRatio.toFixed(1) + '%';
                        
                        // Set active tier from the most recent record
                        if (recent && recent.length > 0) {{
                            document.getElementById('metric-active-tier').innerText = recent[0].tier;
                        }} else {{
                            document.getElementById('metric-active-tier').innerText = 'N/A';
                        }}
                    }}
                }} catch (err) {{
                    console.error('Failed to fetch metrics:', err);
                }}
            }}
            updateCompactionMetrics();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


class ChatMessage(BaseModel):
    role: str
    content: Union[str, List[Dict[str, Any]]]

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    stream: Optional[bool] = False
    temperature: Optional[float] = None

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest, background_tasks: BackgroundTasks):
    if not request.messages:
        return JSONResponse(status_code=400, content={"error": "No messages provided"})
        
    last_msg = request.messages[-1]
    prompt_text = ""
    image_data = None

    # Handle standard text or multimodal payload
    if isinstance(last_msg.content, str):
        prompt_text = last_msg.content
    elif isinstance(last_msg.content, list):
        for part in last_msg.content:
            if part.get("type") == "text":
                prompt_text += part.get("text", "")
            elif part.get("type") == "image_url":
                # Expecting base64 image data in OpenAI format
                image_url = part.get("image_url", {}).get("url", "")
                if "base64," in image_url:
                    image_data = image_url.split("base64,")[1]
                else:
                    image_data = image_url # Assume raw base64 or URL

    # Validate Input Schema
    if not prompt_text and not image_data:
        return JSONResponse(status_code=422, content={"error": "Malformed request: No text or image found in last message."})

    # PROXY INTERCEPTOR: Route multi-modal payloads directly to Polymorphic Cascade
    if image_data:
        import uuid
        doc_id = f"doc-{uuid.uuid4().hex[:8]}"
        ingress_payload = InvoiceIngress(document_id=doc_id, base64_image=image_data)
        
        # Internally invoke the polymorphic pipeline
        pipeline_response = await ingest_document_payload(ingress_payload, background_tasks)
        
        # Serialize rich JSON to a markdown string for the frontend renderer
        status = pipeline_response.get("status", "ERROR")
        doc_class = pipeline_response.get("document_classification", "UNKNOWN")
        latency = pipeline_response.get("latency_sec", 0.0)
        
        formatted_response = f"### Polymorphic Engine: {status}\n\n"
        formatted_response += f"**Classification:** `{doc_class}`\n"
        formatted_response += f"**Latency:** `{latency}s`\n\n"
        # Update Router Stats
        stats.total_requests += 1
        stats.successful += 1
        stats.last_provider = f"Polymorphic ({doc_class})"
        stats.last_latency = latency

        if status == "PROCESSED":
            extracted = pipeline_response.get("payload", {})
            formatted_response += "#### Extracted Data\n\n"
            formatted_response += dict_to_markdown_table(extracted) + "\n"
        else:
            formatted_response += f"**Reason:** {pipeline_response.get('reason', 'Unknown error')}"
        
        response_json = {
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "polymorphic-router",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": formatted_response,
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        }
        return response_json

    # Serialize messages to plain dicts for downstream consumption
    messages_plain = []
    for msg in request.messages:
        if isinstance(msg.content, str):
            messages_plain.append({"role": msg.role, "content": msg.content})
        else:
            if image_data:
                # Keep multimodal dicts intact for vision cascade
                messages_plain.append({"role": msg.role, "content": msg.content})
            else:
                # Multimodal: flatten to text-only for the cascade
                text_parts = "".join(p.get("text", "") for p in msg.content if p.get("type") == "text")
                messages_plain.append({"role": msg.role, "content": text_parts})

    # Send through our router
    start_time = time.time()
    try:
        response_text, model_label, compaction_metrics = classify_and_route(prompt_text, image_data=image_data, messages=messages_plain)
        elapsed = time.time() - start_time

        # Track stats (Skip auto-title ghosts from immediately overwriting heavy vision logs)
        is_real_request = _should_log_telemetry(messages_plain)
        if is_real_request:
            stats.total_requests += 1
            stats.successful += 1
            stats.last_provider = model_label
            stats.last_latency = elapsed

            # Persist compaction telemetry to DuckDB (only for real requests)
            _record_compaction_metrics(compaction_metrics, elapsed, model_label)
        else:
            logger.info(f"[TELEMETRY BYPASS] Ignored auto-title request ({elapsed:.1f}s).")
    except Exception as e:
        stats.total_requests += 1
        stats.failed += 1
        logger.error(f"Routing logic failure: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal System Error in routing logic."})
    
    # Tag the response so the user knows the source
    if "ERROR" in model_label:
        tag = "[⚠️ Error]"
    else:
        tag = "[🌊 Cascade]"
        
    formatted_response = f"{tag} {response_text}"
    
    # Format as an OpenAI-compatible JSON response
    response_json = {
        "id": f"chatcmpl-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "hybrid-router",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": formatted_response,
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": compaction_metrics.get("compact_tokens", 0),
            "completion_tokens": 0,
            "total_tokens": compaction_metrics.get("compact_tokens", 0)
        }
    }
    
    logger.info(f"API Request completed in {elapsed:.1f}s -> {tag}")
    return response_json

@app.get("/v1/models")
async def get_models():
    return {
        "object": "list",
        "data": [{"id": "hybrid-router", "object": "model", "created": int(time.time()), "owned_by": "antigravity"}]
    }

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/health/providers")
async def health_providers():
    """Detailed provider health status for programmatic consumption."""
    result = {}
    for pid, ps in provider_statuses.items():
        result[pid] = {
            "name": ps.name,
            "status": ps.status,
            "latency_ms": ps.latency_ms,
            "last_checked": ps.last_checked,
            "error": ps.error,
        }
    return result


@app.get("/api/v1/metrics/efficiency")
def get_efficiency_metrics(request: Request):
    """Compaction telemetry — aggregate stats and last 10 records from DuckDB."""
    if "text/html" in request.headers.get("accept", ""):
        return RedirectResponse(url="/dashboard")
    try:
        con = duckdb.connect(_DB_PATH, read_only=True)

        summary = con.execute("""
            SELECT
                COUNT(*)            AS total_requests,
                COALESCE(SUM(tokens_saved), 0)    AS total_tokens_saved,
                COALESCE(ROUND(AVG(savings_pct), 2), 0) AS avg_savings_pct,
                COALESCE(ROUND(AVG(latency_sec), 4), 0) AS avg_latency_sec,
                COALESCE(SUM(messages_dropped), 0) AS total_messages_dropped,
                COALESCE(SUM(prefixes_stripped), 0) AS total_prefixes_stripped
            FROM compaction_log
        """).fetchone()

        recent = con.execute("""
            SELECT timestamp, raw_tokens, compact_tokens, tokens_saved,
                   savings_pct, messages_dropped, prefixes_stripped, latency_sec, tier
            FROM compaction_log
            ORDER BY id DESC
            LIMIT 10
        """).fetchall()

        con.close()

        recent_records = [
            {
                "timestamp": r[0], "raw_tokens": r[1], "compact_tokens": r[2],
                "tokens_saved": r[3], "savings_pct": r[4], "messages_dropped": r[5],
                "prefixes_stripped": r[6], "latency_sec": r[7], "tier": r[8],
            }
            for r in recent
        ]

        return {
            "summary": {
                "total_requests": summary[0],
                "total_tokens_saved": summary[1],
                "avg_savings_pct": summary[2],
                "avg_latency_sec": summary[3],
                "total_messages_dropped": summary[4],
                "total_prefixes_stripped": summary[5],
            },
            "recent": recent_records,
        }
    except Exception as e:
        logger.error(f"[TELEMETRY] Metrics query failed: {e}")
        return JSONResponse(status_code=500, content={"error": f"Metrics unavailable: {e}"})


# ============================================================
# INVOICE ANOMALY PIPELINE — v2.5.0
# ============================================================

def _fetch_invoice_history() -> List[str]:
    """Fetch unique invoice history markers from local DuckDB memory to check duplicates."""
    try:
        con = duckdb.connect(_DB_PATH, read_only=True)
        res = con.execute("SELECT document_id FROM invoice_ledger").fetchall()
        con.close()
        return [str(r[0]) for r in res]
    except Exception as e:
        logger.warning(f"[PIPELINE] Failed to fetch invoice history: {e}")
        return []

def persist_pipeline_telemetry(doc_id: str, data: dict, is_anomaly: bool, flags: list, duration: float):
    """
    Offloads telemetry logs to DuckDB using Starlette background worker pool.
    Enforces rule sql-standards.md: Explicitly use INSERT OR REPLACE for perfect idempotency.
    Uses a fresh DuckDB connection per background task execution to avoid thread lock contention.
    """
    try:
        con = duckdb.connect(_DB_PATH)
        invoice_number = data.get("invoice_number", "UNKNOWN")
        vendor = data.get("vendor_name", "UNKNOWN")
        total = float(data.get("grand_total", 0.0))
        anomaly_notes = json.dumps(flags)
        extracted_json = json.dumps(data)
        
        con.execute(
            """
            INSERT OR REPLACE INTO invoice_ledger 
            (document_id, invoice_number, vendor_name, grand_total, is_anomaly, flags, extracted_json, latency_sec, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [doc_id, invoice_number, vendor, total, is_anomaly, anomaly_notes, extracted_json, duration, datetime.datetime.utcnow()]
        )
        con.close()
        logger.info(f"[METRIC COMPACTION] Logged document {doc_id} in {duration:.2f}s. Anomaly Flag: {is_anomaly}")
    except Exception as e:
        logger.error(f"[TELEMETRY] Failed to persist invoice pipeline metrics: {e}")

def persist_letter_telemetry(doc_id: str, data: dict, duration_sec: float):
    """Fulfills sql-standards.md: Guarantees idempotent writes for semantic records."""
    try:
        with duckdb.connect(_DB_PATH) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO letter_ledger 
                (document_id, sender_entity, recipient_entity, subject_line, semantic_intent, urgency_score, latency_sec, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                doc_id,
                data.get("sender_entity"),
                data.get("recipient_entity"),
                data.get("subject_line"),
                data.get("semantic_intent"),
                data.get("urgency_score"),
                duration_sec,
                datetime.datetime.utcnow()
            ))
        logger.info(f"[METRIC COMPACTION] Logged letter {doc_id} in {duration_sec:.2f}s.")
    except Exception as e:
        logger.error(f"[TELEMETRY] Failed to persist letter pipeline metrics: {e}")

def _handle_quarantine_drop(doc_id: str, error_msg: str):
    logger.error(f"[PIPELINE] Malformed or failed payload. Routing to quarantine. Error: {error_msg}")
    quarantine_file = f"{_DB_DIR}/quarantine_{datetime.date.today().strftime('%Y%m%d')}.parquet"
    error_record = pd.DataFrame([{
        "document_id": doc_id,
        "timestamp": datetime.datetime.utcnow(),
        "error_msg": error_msg
    }])
    try:
        if os.path.exists(quarantine_file):
            existing_df = pd.read_parquet(quarantine_file)
            updated_df = pd.concat([existing_df, error_record], ignore_index=True)
            updated_df.to_parquet(quarantine_file)
        else:
            error_record.to_parquet(quarantine_file)
    except Exception as pq_err:
        logger.error(f"[QUARANTINE] Failed to write quarantine parquet: {pq_err}")

@app.post("/api/v1/pipeline/ingest")
async def ingest_document_payload(payload: InvoiceIngress, background_tasks: BackgroundTasks):
    """
    Polymorphic Ingestion Engine entry point. Intelligently splits the data processing pipeline 
    runtimes based on an upfront structural categorization pass.
    """
    t_start = time.perf_counter()
    from src.config import GEMINI_API_KEYS
    api_key = GEMINI_API_KEYS[0] if GEMINI_API_KEYS else ""
    
    try:
        # Step 1: Classify document pattern profile and extract targeting parameters safely
        doc_type, extracted_data = await classify_and_extract_document(payload.base64_image, api_key)
        
        # Step 2: Adaptive Processing Fork
        if doc_type == DocumentType.INVOICE:
            historical_keys = _fetch_invoice_history()
            is_anomaly, anomaly_reports = analyze_document_anomalies(extracted_data, historical_keys)
            
            total_latency_sec = time.perf_counter() - t_start
            background_tasks.add_task(
                persist_pipeline_telemetry,
                payload.document_id, extracted_data, is_anomaly, anomaly_reports, total_latency_sec
            )
            
            return {
                "status": "PROCESSED",
                "document_classification": doc_type.value,
                "document_id": payload.document_id,
                "is_anomaly": is_anomaly,
                "latency_sec": round(total_latency_sec, 4),
                "payload": extracted_data
            }
            
        elif doc_type == DocumentType.LETTER:
            # Skip the mathematical balance check entirely (letters don't have subtotals)
            total_latency_sec = time.perf_counter() - t_start
            
            background_tasks.add_task(
                persist_letter_telemetry,
                payload.document_id, extracted_data, total_latency_sec
            )
            
            return {
                "status": "PROCESSED",
                "document_classification": doc_type.value,
                "document_id": payload.document_id,
                "latency_sec": round(total_latency_sec, 4),
                "payload": extracted_data
            }
        else:
            raise ValueError(f"Unknown document classification: {doc_type}")
            
    except Exception as cascade_error:
        total_latency_sec = time.perf_counter() - t_start
        _handle_quarantine_drop(payload.document_id, str(cascade_error))
        return {
            "status": "QUARANTINED",
            "document_id": payload.document_id,
            "reason": str(cascade_error),
            "latency_sec": round(total_latency_sec, 4)
        }