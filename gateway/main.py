from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import os, httpx
from tenacity import retry, stop_after_attempt, wait_exponential
import logging

app = FastAPI(title="Gateway")

logging.basicConfig(level=logging.INFO)

# Simple in-memory cache for last-known-good service responses
CACHE = {
  "a": {"service": "Metadata Service A (crypto)", "datasets": ["bitcoin: -", "ethereum: -"]},
  "b": {"service": "B - GitHub Stats", "usd_rate": None, "repos": []},
  "c": {"service": "C - Lineage Service", "repos": []}
}

# Environment service URLs
SERVICE_A_URL = os.getenv("SERVICE_A_URL", "http://service_a:8000")
SERVICE_B_URL = os.getenv("SERVICE_B_URL", "http://service_b:8000")
SERVICE_C_URL = os.getenv("SERVICE_C_URL", "http://service_c:8000")
FALLBACK_URL  = os.getenv("FALLBACK_URL",  "http://fallback:8000")

@app.get("/health")
def health():
    return {"status": "ok", "service": "gateway"}

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.2, min=0.2, max=1.0))
async def call(url: str):
  # increase timeout to be more tolerant of intermittent slowness
  async with httpx.AsyncClient(timeout=5.0) as client:
    r = await client.get(url)
    r.raise_for_status()
    return r.json()

@app.get("/aggregate")
async def aggregate():
  # Fetch A (crypto) with resilience: on failure use cache
  try:
    a = await call(f"{SERVICE_A_URL}/datasets")
    # update cache when successful and shape looks right
    if isinstance(a, dict) and "datasets" in a:
      CACHE["a"] = a
    status_a = "UP"
  except Exception as exc:
    logging.warning("Service A fetch failed: %s", exc)
    a = CACHE.get("a")
    status_a = "DOWN"

  # Fetch B (stats) with fallback; if both fail use cache
  try:
    b = await call(f"{SERVICE_B_URL}/stats")
    status_b = "UP"
    if isinstance(b, dict):
      CACHE["b"] = b
  except Exception as exc:
    logging.warning("Service B primary failed: %s", exc)
    try:
      b = await call(f"{FALLBACK_URL}/default")
      status_b = "FALLBACK"
      if isinstance(b, dict):
        CACHE["b"] = b
    except Exception as exc2:
      logging.warning("Fallback for B failed: %s", exc2)
      b = CACHE.get("b")
      status_b = "DOWN"

  # Fetch C (lineage) with resilience
  try:
    c = await call(f"{SERVICE_C_URL}/lineage")
    status_c = "UP"
    if isinstance(c, dict):
      CACHE["c"] = c
  except Exception as exc:
    logging.warning("Service C fetch failed: %s", exc)
    c = CACHE.get("c")
    status_c = "DOWN"

  return {"gateway": "UP", "a": a, "a_status": status_a, "b": b, "b_status": status_b, "c": c, "c_status": status_c}

# Dashboard UI
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return """
    <html>
      <head>
        <title>Resilient Microservices Dashboard</title>
        <style>
          body { font-family: Arial, sans-serif; margin: 30px; background: #f7f9fc; }
          h1 { color: #2c3e50; text-align: center; }
          .grid { display: flex; gap: 20px; margin-top: 30px; justify-content:center; flex-wrap:wrap; }
          .card {
            background: white; padding: 20px; border-radius: 12px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1); width: 280px; text-align:center;
          }
          .status-up { color: green; font-weight: bold; }
          .status-down { color: red; font-weight: bold; }
          .status-fallback { color: orange; font-weight: bold; }
        </style>
        <script>
          async function fetchData() {
            // Set default/loading statuses early to avoid blank UI during partial failures
            document.getElementById("g-status").innerHTML = "Loading...";
            document.getElementById("a-status").innerHTML = "Loading...";
            document.getElementById("b-status").innerHTML = "Loading...";
            document.getElementById("c-status").innerHTML = "Loading...";

            try {
              let resp = await fetch("/aggregate");
              if (!resp.ok) throw new Error('aggregate endpoint returned ' + resp.status);
              let data = await resp.json();

              // Service A (defensive)
              if (data && data.a && Array.isArray(data.a.datasets)) {
                document.getElementById("a-status").innerHTML = "✅ UP";
                document.getElementById("a-message").innerHTML = data.a.datasets.length ? data.a.datasets.join("<br>") : "(no datasets)";
              } else {
                document.getElementById("a-status").innerHTML = "❌ DOWN";
                document.getElementById("a-message").innerHTML = "-";
              }

              // Service B (defensive)
              if (data && data.b_status === "UP") {
                document.getElementById("b-status").innerHTML = "✅ UP";
              } else if (data && data.b_status === "FALLBACK") {
                document.getElementById("b-status").innerHTML = "⚠️ FALLBACK";
              } else {
                document.getElementById("b-status").innerHTML = "❌ DOWN";
              }
              // render top repo list for B (owner/repo names with stars)
              if (data && data.b && Array.isArray(data.b.repos) && data.b.repos.length) {
                let brepos = data.b.repos.map(r => `<a href="${r.url}" target="_blank">${r.name}</a> ⭐ ${r.stars || '-'}`).join("<br>");
                document.getElementById("b-result").innerHTML = brepos;
              } else {
                document.getElementById("b-result").innerHTML = "-";
              }

              // Service C (defensive)
              if (data && data.c && Array.isArray(data.c.repos)) {
                document.getElementById("c-status").innerHTML = "✅ UP";
                let repos = data.c.repos.map(r => `<a href="${r.url}" target="_blank">${r.name}</a>`).join("<br>");
                document.getElementById("c-repos").innerHTML = repos || "-";
              } else {
                document.getElementById("c-status").innerHTML = "❌ DOWN";
                document.getElementById("c-repos").innerHTML = "-";
              }

              // Gateway
              document.getElementById("g-status").innerHTML = "✅ UP";
            } catch (e) {
              // On any failure, mark gateway down and leave other fields as-is (they may have specific status)
              document.getElementById("g-status").innerHTML = "❌ DOWN";
              console.error('fetchData error', e);
            }
          }
          // Poll less frequently to avoid hammering upstream APIs
          setInterval(fetchData, 10000);
          window.onload = fetchData;
        </script>
      </head>
      <body>
        <h1>🚀 Resilient Microservices Deployment Platform</h1>
        <div class="grid">
          <div class="card">
            <h2>Service A (Datasets)</h2>
            <p>Status: <span id="a-status">Loading...</span></p>
            <p>Top Datasets:<br><span id="a-message">-</span></p>
          </div>
          <div class="card">
            <h2>Service B (Stats)</h2>
            <p>Status: <span id="b-status">Loading...</span></p>
            <p><span id="b-result">-</span></p>
          </div>
          <div class="card">
            <h2>Service C (Lineage)</h2>
            <p>Status: <span id="c-status">Loading...</span></p>
            <p><span id="c-repos">-</span></p>
          </div>
          <div class="card">
            <h2>Gateway</h2>
            <p>Status: <span id="g-status">Loading...</span></p>
          </div>
        </div>
      </body>
    </html>
    """
