"""Demo local en una sola dirección http: la app (dashboard/dist) y la API en el mismo puerto, como en el hosting.

Uso, desde la raíz del proyecto:
    .venv/bin/python -m backend.demo                       # abre http://localhost:8000
    .venv/bin/python -m backend.demo --puerto 8001 --sin-navegador

Solo escucha en esta computadora (127.0.0.1). El hosting de AWS no usa este archivo: arranca backend.main:app.
"""
import argparse
import shutil
import socket
import subprocess
import threading
import webbrowser
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles

from .main import _mapa_touchdown, app as api

RAIZ = Path(__file__).resolve().parent.parent
DASH = RAIZ / "dashboard"
DIST = DASH / "dist"
RUTAS_API = ("/api/", "/health", "/docs", "/openapi.json")


def _build_desactualizado() -> bool:
    """¿Falta dashboard/dist o hay código del dashboard más nuevo que el último build?"""
    indice = DIST / "index.html"
    if not indice.exists():
        return True
    fuentes = [DASH / "index.html", DASH / "vite.config.ts", *(DASH / "src").rglob("*")]
    return max(f.stat().st_mtime for f in fuentes if f.is_file()) > indice.stat().st_mtime


def _node() -> str | None:
    for candidato in (RAIZ / ".hackathon/.tools/node/bin/node", RAIZ / ".hackathon/.tools/node/node.exe"):
        if candidato.exists():
            return str(candidato)
    return shutil.which("node")


def compilar_dashboard() -> None:
    node, vite = _node(), DASH / "node_modules/vite/bin/vite.js"
    if not node or not vite.exists():
        raise SystemExit("No encuentro Node o Vite para compilar el dashboard. Corre  sh .hackathon/setup.sh  y vuelve a intentar.")
    print("Compilando el dashboard (vite build)...", flush=True)
    if subprocess.run([node, str(vite), "build"], cwd=DASH).returncode != 0:
        raise SystemExit("El dashboard no compiló. Revisa el error de arriba.")


def crear_app():
    """Envía /api/..., /health y la documentación al backend; todo lo demás es el dashboard compilado."""
    # Dentro de una app de Starlette para que una ruta inexistente responda 404 y no 500
    estatico = Starlette(routes=[Mount("/", app=StaticFiles(directory=DIST, html=True))])

    async def demo(scope, receive, send):
        if scope["type"] == "http" and not scope["path"].startswith(RUTAS_API):
            await estatico(scope, receive, send)
        else:
            await api(scope, receive, send)

    return demo


def _puerto_libre(puerto: int) -> bool:
    """Libre si nadie responde en ese puerto (un socket recién cerrado no cuenta como ocupado)."""
    try:
        with socket.create_connection(("127.0.0.1", puerto), timeout=0.5):
            return False
    except OSError:
        return True


def main() -> None:
    ap = argparse.ArgumentParser(description="Demo local de la app en una sola dirección http.")
    ap.add_argument("--puerto", type=int, default=8000, help="puerto local (por defecto 8000)")
    ap.add_argument("--sin-navegador", action="store_true", help="no abrir el navegador al arrancar")
    args = ap.parse_args()

    if not _puerto_libre(args.puerto):
        raise SystemExit(f"El puerto {args.puerto} está ocupado (¿ya corre el demo o uvicorn?). Usa otro: --puerto {args.puerto + 1}")
    if _build_desactualizado():
        compilar_dashboard()
    print("Calculando el mapa y la simulación de las jugadas...", flush=True)
    _mapa_touchdown()   # la primera visita ya no espera

    url = f"http://localhost:{args.puerto}"
    print(f"\nDemo lista en {url}")
    print(f"Cada jugada tiene su dirección, por ejemplo {url}/#jugada=2021091900-145")
    print("Para detenerla: Ctrl+C\n", flush=True)
    if not args.sin_navegador:
        threading.Timer(1.0, webbrowser.open, [url]).start()
    uvicorn.run(crear_app(), host="127.0.0.1", port=args.puerto, log_level="warning")


if __name__ == "__main__":
    main()
