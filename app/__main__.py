"""Permite iniciar o servidor diretamente via `python -m app.main` ou `python -m app`."""

import uvicorn
from app.config import settings


def run_server() -> None:
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False,
    )


if __name__ == "__main__":
    run_server()

