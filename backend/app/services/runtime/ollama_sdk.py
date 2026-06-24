"""Ollama runtime adapter (local or remote LLM via HTTP).

Set OLLAMA_URL in .env to point at a remote Ollama instance:
    OLLAMA_URL=http://192.168.1.100:11434
"""

from app.core.config import settings


def _url() -> str:
    return (settings.OLLAMA_URL or "http://localhost:11434").rstrip("/")


async def run_agent(
    *,
    prompt: str,
    system_prompt: str = "",
    model: str = "",
    max_tokens: int = 2048,
    temperature: float = 0.7,
    base_url: str | None = None,
    format: str | None = None,
    num_ctx: int = 8192,
) -> tuple[str, dict]:
    """Call an Ollama server's chat endpoint.

    ``base_url`` is injected by ``run_with_fallback`` from the DB-stored value so
    that the URL set in Admin → Settings takes effect without a container restart.
    ``format`` may be set to ``"json"`` to request structured JSON output from
    Ollama (supported by Ollama 0.1.20+).
    ``num_ctx`` sets the Ollama context window size (default 8192). Without this,
    Ollama uses the model's compiled default (~4096 for gemma3:12b), which can be
    fully consumed by the input prompt, leaving no tokens for output.
    """
    import httpx

    base = (base_url or _url()).rstrip("/")
    resolved_model = model or "llama3.2"
    request_body: dict = {
        "model": resolved_model,
        "messages": [
            {"role": "system", "content": system_prompt or "You are a helpful assistant."},
            {"role": "user", "content": prompt},
        ],
        "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": num_ctx},
        "stream": False,
    }
    if format:
        request_body["format"] = format
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{base}/api/chat",
            json=request_body,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data.get("message", {}).get("content", "")
        tokens = None
        prompt_eval = data.get("prompt_eval_count")
        eval_count = data.get("eval_count")
        if prompt_eval is not None or eval_count is not None:
            tokens = (prompt_eval or 0) + (eval_count or 0)
        return text, {"runtime": "ollama", "model": resolved_model, "tokens_used": tokens}


def healthcheck() -> dict:
    """Check whether the Ollama server responds."""
    base = _url()
    detail = ""
    available = False
    try:
        import httpx

        resp = httpx.get(f"{base}/api/tags", timeout=2.0)
        available = resp.status_code == 200
        if not available:
            detail = f"ollama returned HTTP {resp.status_code}"
        else:
            detail = f"connected to {base}"
    except Exception as exc:
        detail = f"ollama not reachable at {base}: {exc}"
    return {"kind": "ollama", "available": available, "detail": detail}
