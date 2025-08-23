from fastapi import FastAPI
import httpx
import os
import logging
from tenacity import retry, stop_after_attempt, wait_exponential

app = FastAPI(title="Service C - Lineage")

logging.basicConfig(level=logging.INFO)

# in-memory cache for last-known-good lineage
C_CACHE = {"repos": []}
# cooldown end timestamp (epoch seconds) when GitHub rate-limit observed
C_COOLDOWN_UNTIL = 0


@app.get("/health")
def health():
    return {"status": "ok", "service": "C"}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=0.5, max=2.0))
async def fetch_github(url: str, headers: dict):
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(url, headers=headers)
        r.raise_for_status()
        return r.json()


@app.get("/lineage")
async def lineage():
    # Use GitHub search API to get recently popular repositories (by stars)
    url = "https://api.github.com/search/repositories?q=created:>2024-01-01&sort=stars&order=desc&per_page=5"
    headers = {}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"token {token}"

    try:
        # if we're currently in cooldown due to rate-limiting, return cache
        import time
        global C_COOLDOWN_UNTIL
        if C_COOLDOWN_UNTIL and time.time() < C_COOLDOWN_UNTIL:
            logging.info("In GitHub cooldown for service C until %s, returning cached repos", C_COOLDOWN_UNTIL)
            return {"service": "C - Lineage Service", "repos": C_CACHE.get("repos", [])}

        data = await fetch_github(url, headers)
        items = data.get("items", []) if isinstance(data, dict) else []
        repos = [{"name": it.get("full_name"), "url": it.get("html_url"), "stars": it.get("stargazers_count")} for it in items]

        # only update cache if we got results
        if repos:
            C_CACHE["repos"] = repos

        return {"service": "C - Lineage Service", "repos": repos}
    except httpx.HTTPStatusError as http_exc:
        status = http_exc.response.status_code if http_exc.response is not None else None
        logging.warning("GitHub HTTP error for service C: %s", http_exc)
        if status in (403, 429):
            import time
            C_COOLDOWN_UNTIL = time.time() + 30  # 30s cooldown
            logging.info("Setting cooldown for service C until %s due to status %s", C_COOLDOWN_UNTIL, status)
        return {"service": "C - Lineage Service", "repos": C_CACHE.get("repos", [])}
    except Exception as exc:
        logging.warning("Lineage fetch failed: %s", exc)
        return {"service": "C - Lineage Service", "repos": C_CACHE.get("repos", [])}
