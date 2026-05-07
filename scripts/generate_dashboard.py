import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "traces.db")
REPORT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports", "BAD_ANSWERS.md")

def generate():
    if not os.path.exists(DB_PATH):
        print("Traces DB not found.")
        return
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Query flagged or low score traces
    cursor.execute('''
        SELECT trace_id, query, response, model_used, total_latency, faithfulness_score, flagged 
        FROM traces 
        ORDER BY timestamp DESC LIMIT 20
    ''')
    rows = cursor.fetchall()
    
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("# 🚩 Observability Dashboard: Bad Answers & Traces\n\n")
        f.write("| Status | Query | Model | Latency | Faithfulness | Trace ID |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- | :--- |\n")
        
        for row in rows:
            tid, q, resp, model, lat, score, flagged = row
            status = "🔴 FLAG" if flagged else "🟢 OK"
            q_short = (q[:50] + "...") if q and len(q) > 50 else q
            f.write(f"| {status} | {q_short} | {model} | {lat or 0:.1f}s | {score or 0}/5 | {tid} |\n")
            
        f.write("\n\n## 🔍 Trace Deep Dive (Last 5 Traces)\n")
        for row in rows[:5]:
            tid, q, resp, model, lat, score, flagged = row
            f.write(f"\n### Trace: {tid}\n")
            f.write(f"- **Query**: {q}\n")
            f.write(f"- **Response**: {(resp[:300] if resp else '')}...\n")
            f.write("- **Spans**:\n")
            
            cursor.execute("SELECT name, latency, output_data FROM spans WHERE trace_id=? ORDER BY start_time", (tid,))
            spans = cursor.fetchall()
            for s in spans:
                name, slat, out = s
                f.write(f"  - {name} ({slat:.2f}s): {str(out)[:100]}...\n")
                
    conn.close()
    print(f"✅ Dashboard generated at {REPORT_PATH}")

if __name__ == "__main__":
    generate()