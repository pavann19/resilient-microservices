from fastapi import FastAPI

app = FastAPI(title="Fallback Service")

@app.get("/health")
def health():
    return {"status": "ok", "service": "fallback"}

@app.get("/default")
def default():
    return {
        "service": "fallback",
        "message": "using fallback service"
    }
