from fastapi import FastAPI
import httpx
import logging
from tenacity import retry, stop_after_attempt, wait_exponential

app = FastAPI()

# Simple in-memory cache to survive transient upstream failures.
# This keeps the last-known-good values while the container runs.
CACHE = {"datasets": ["bitcoin: -", "ethereum: -"]}
logging.basicConfig(level=logging.INFO)

# cooldown end timestamp (epoch seconds) when CoinGecko rate-limit observed
A_COOLDOWN_UNTIL = 0

@app.get("/datasets")
async def datasets():
    # Use CoinGecko simple price API to return crypto prices for dashboard
    url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=0.5, max=2.0))
    async def fetch():
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(url)
            r.raise_for_status()
            return r.json()

    try:
        # if we're currently in cooldown due to rate-limiting, return cache
        import time
        global A_COOLDOWN_UNTIL
        if A_COOLDOWN_UNTIL and time.time() < A_COOLDOWN_UNTIL:
            logging.info("In CoinGecko cooldown until %s, returning cached datasets", A_COOLDOWN_UNTIL)
            datasets = CACHE.get("datasets", ["bitcoin: -", "ethereum: -"])
            return {
                "service": "Metadata Service A (crypto)",
                "datasets": datasets
            }

        data = await fetch()
        datasets = []
        if isinstance(data, dict):
            for k in ("bitcoin", "ethereum"):
                v = data.get(k, {}).get("usd")
                if v is not None:
                    datasets.append(f"{k}: ${v}")

        # update cache with fresh values if we got any
        if datasets:
            CACHE["datasets"] = datasets

    except httpx.HTTPStatusError as http_exc:
        status = http_exc.response.status_code if http_exc.response is not None else None
        logging.warning("CoinGecko HTTP error: %s", http_exc)
        # on rate-limit responses (429), set a cooldown so we don't hammer the API
        if status == 429:
            import time
            A_COOLDOWN_UNTIL = time.time() + 60  # 60s cooldown
            logging.info("Setting CoinGecko cooldown until %s due to status %s", A_COOLDOWN_UNTIL, status)
        datasets = CACHE.get("datasets", ["bitcoin: -", "ethereum: -"])
    except Exception as exc:
        logging.warning("Failed to fetch CoinGecko prices, using cached values: %s", exc)
        datasets = CACHE.get("datasets", ["bitcoin: -", "ethereum: -"])

    return {
        "service": "Metadata Service A (crypto)",
        "datasets": datasets
    }

@app.get("/health")
def health():
    return {"status": "ok", "service": "A"}
