"""ClaimSight HTTP API."""

from fastapi import FastAPI

app = FastAPI(title="ClaimSight", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe used by load balancers, CI smoke tests and monitoring."""
    return {"status": "ok", "service": "claimsight", "version": app.version}
