from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import httpx

app = FastAPI()

@app.get("/", response_class=HTMLResponse)
async def dashboard():
  try:
    async with httpx.AsyncClient() as client:
      # Gateway is exposed on host port 8080 (docker maps 8080:8000)
      resp = await client.get("http://localhost:8080/aggregate", timeout=2.0)
      data = resp.json()
  except Exception as e:
    data = {"error": str(e)}

    html = f"""
    <html>
      <head>
        <title>Resilient Microservices Dashboard</title>
        <style>
          body {{ font-family: Arial; margin: 20px; }}
          .healthy {{ color: green; }}
          .failed {{ color: red; }}
        </style>
      </head>
      <body>
        <h2>Resilient Microservices Demo</h2>
        <p><b>Service A:</b> <span class="healthy">OK</span></p>
        <p><b>Service B:</b> {"<span class='failed'>Fallback Active</span>" if "fallback" in str(data) else "<span class='healthy'>OK</span>"}</p>
        <h3>Latest Aggregate Response:</h3>
        <pre>{data}</pre>
      </body>
    </html>
    """
    return html
