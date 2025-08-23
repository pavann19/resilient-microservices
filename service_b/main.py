from fastapi import FastAPI
import httpx
import os
import logging
from tenacity import retry, stop_after_attempt, wait_exponential

app = FastAPI(title="Service B - Stats")

logging.basicConfig(level=logging.INFO)

# in-memory cache for last-known-good repos
B_CACHE = {"repos": []}
# cooldown end timestamp (epoch seconds) when GitHub rate-limit observed
B_COOLDOWN_UNTIL = 0


@app.get("/health")
def health():
    return {"status": "ok", "service": "B"}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=0.5, max=2.0))
async def fetch_github(url: str, headers: dict):
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(url, headers=headers)
        r.raise_for_status()
        return r.json()


@app.get("/stats")
async def stats(q: str = "stars:>50000"):
    # Use GitHub search API to return top repositories matching query (default: very popular repos)
    url = f"https://api.github.com/search/repositories?q={q}&sort=stars&order=desc&per_page=5"
    headers = {}
    # Optional: honor GITHUB_TOKEN if provided to avoid strict rate limits
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"token {token}"

    try:
        # if we're currently in cooldown due to rate-limiting, return cache
        import time
        global B_COOLDOWN_UNTIL
        if B_COOLDOWN_UNTIL and time.time() < B_COOLDOWN_UNTIL:
            logging.info("In cooldown until %s, returning cached repos", B_COOLDOWN_UNTIL)
            return {"service": "B - GitHub Stats", "usd_rate": None, "repos": B_CACHE.get("repos", [])}

        data = await fetch_github(url, headers)
        items = data.get("items", []) if isinstance(data, dict) else []
        repos = []
        for it in items:
            repos.append({
                "name": it.get("full_name"),
                "stars": it.get("stargazers_count"),
                "url": it.get("html_url")
            })

        # Only update cache when we got non-empty results
        if repos:
            B_CACHE["repos"] = repos

        return {"service": "B - GitHub Stats", "usd_rate": None, "repos": repos}
    except httpx.HTTPStatusError as http_exc:
        status = http_exc.response.status_code if http_exc.response is not None else None
        logging.warning("GitHub HTTP error: %s", http_exc)
        # on rate-limit responses, set a short cooldown
        if status in (403, 429):
            import time
            B_COOLDOWN_UNTIL = time.time() + 30  # 30s cooldown
            logging.info("Setting cooldown until %s due to status %s", B_COOLDOWN_UNTIL, status)
        return {"service": "B - GitHub Stats", "usd_rate": None, "repos": B_CACHE.get("repos", [])}
    except Exception as exc:
        logging.warning("GitHub fetch failed: %s", exc)
        # return cached repos when upstream fails
        return {"service": "B - GitHub Stats", "usd_rate": None, "repos": B_CACHE.get("repos", [])}
