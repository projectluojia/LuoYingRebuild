"""OpenAI-compatible embedding proxy that forwards to Ollama's native API.

Run with: python -m uvicorn embed_proxy:app --host 0.0.0.0 --port 8080
"""
from __future__ import annotations

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

app = FastAPI(title="Embedding Proxy")

OLLAMA_BASE = "http://127.0.0.1:11434"
TIMEOUT = 120.0


@app.post("/v1/embeddings")
async def embeddings(request: dict) -> JSONResponse:
    model = request.get("model", "nomic-embed-text")
    inputs: list[str] = request.get("input", [])
    if isinstance(inputs, str):
        inputs = [inputs]

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        vectors: list[dict] = []
        for i, text in enumerate(inputs):
            r = await client.post(
                f"{OLLAMA_BASE}/api/embeddings",
                json={"model": model, "prompt": text},
            )
            if r.status_code != 200:
                raise HTTPException(status_code=502, detail=f"Ollama error: {r.text}")
            data = r.json()
            embedding = data.get("embedding")
            if not embedding:
                raise HTTPException(status_code=502, detail="Ollama returned no embedding")
            vectors.append({"object": "embedding", "embedding": embedding, "index": i})

        return JSONResponse(
            content={
                "object": "list",
                "data": vectors,
                "model": model,
                "usage": {"prompt_tokens": 0, "total_tokens": 0},
            }
        )


@app.get("/health")
async def health() -> dict:
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
