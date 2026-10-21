from fastapi import FastAPI

app = FastAPI(
    title="Praxis API",
    description="Shared API for the Praxis CLI and web application.",
    version="0.1.0",
)


@app.get("/health", tags=["operations"])
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "praxis-api"}
