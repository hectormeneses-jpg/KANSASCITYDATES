"""API de la plantilla. Ejecuta: .venv/bin/uvicorn backend.main:app --reload"""
from functools import lru_cache

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

app = FastAPI(title="Hackathon NFL UNAM")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@lru_cache(maxsize=1)
def _mapa_touchdown() -> str:
    """Calcula el mapa la primera vez y lo deja en memoria. No escribe archivos: el servidor es efímero."""
    from .mapa_touchdown import construir_datos, generar_html  # pandas se importa solo cuando se pide el mapa

    datos, _ = construir_datos()
    return generar_html(datos)


@app.get("/api/mapa-touchdown", response_class=HTMLResponse)
def mapa_touchdown() -> str:
    """Mapa interactivo de probabilidad de touchdown en las últimas yardas (HTML autocontenido)."""
    try:
        return _mapa_touchdown()
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=f"No se encontraron los datos del mapa: {e}")
