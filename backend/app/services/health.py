from typing import Any

import httpx

from app.config import settings
from app.db.session import check_database_reachable


async def get_health_status() -> dict[str, Any]:
    db_ok = check_database_reachable()

    ollama_ok = False
    llm_installed = False
    embedding_installed = False

    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            if resp.status_code == 200:
                ollama_ok = True
                data = resp.json()
                model_names = [m.get("name", "") for m in data.get("models", [])]

                # Match e.g. qwen3.5:4b and nomic-embed-text (or nomic-embed-text:latest)
                for name in model_names:
                    clean_name = name.split(":")[0]
                    if (
                        name == settings.model_name
                        or clean_name == settings.model_name.split(":")[0]
                    ):
                        llm_installed = True
                    if (
                        name == settings.embedding_model
                        or clean_name == settings.embedding_model.split(":")[0]
                    ):
                        embedding_installed = True
    except Exception:
        ollama_ok = False

    both_models_installed = llm_installed and embedding_installed
    is_healthy = db_ok and ollama_ok and both_models_installed

    return {
        "status": "healthy" if is_healthy else "degraded",
        "database_reachable": db_ok,
        "ollama_reachable": ollama_ok,
        "models": {
            "llm": settings.model_name,
            "llm_installed": llm_installed,
            "embedding": settings.embedding_model,
            "embedding_installed": embedding_installed,
            "installed": both_models_installed,
        },
        "api_key_configured": settings.api_key_configured,
        "scheduler_running": False,
        "next_brief_at": None,
        "interrupted_runs_count": 0,
    }
