"""Mapa interactivo de probabilidad de touchdown en las últimas yardas del campo.

Lee los CSV de data/ con pandas, detecta los touchdowns ofensivos de cada jugada de pase y
escribe un único HTML autocontenido (sin internet ni librerías externas).

Uso, desde la raíz del proyecto:
    .venv/bin/python -m backend.mapa_touchdown
    .venv/bin/python -m backend.mapa_touchdown --yardas 25 --salida otra_ruta.html
"""
import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
CARPETA_DATOS = RAIZ / "data"
PLANTILLA = Path(__file__).with_name("mapa_touchdown.plantilla.html")
SALIDA = RAIZ / "mapa_touchdown.html"

SUFIJOS = {"jr", "sr", "ii", "iii", "iv", "v"}
CARRILES = {"left": "izq", "middle": "cen", "right": "der"}
# Texto que sigue al receptor en la descripción: "pass short right to C.Godwin for 6 yards"
RX_DESTINO = re.compile(
    r"(?:pass (?:incomplete )?(?:(?:short|deep) )?(?:(?:left|middle|right) )?to|intended for) (.+)"
)


def _ruta_csv(nombre: str) -> Path:
    """data/<nombre>.csv; acepta también copias descargadas como '<nombre> (1).csv'."""
    exacto = CARPETA_DATOS / f"{nombre}.csv"
    if exacto.exists():
        return exacto
    copias = sorted(CARPETA_DATOS.glob(f"{nombre} (*).csv"))
    if copias:
        return copias[0]
    raise FileNotFoundError(f"No encuentro {nombre}.csv en {CARPETA_DATOS}")


def cargar_datos() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Devuelve (plays, games, players, pff) tal como vienen en data/."""
    plays = pd.read_csv(_ruta_csv("plays"))
    games = pd.read_csv(_ruta_csv("games"), usecols=["gameId", "season", "week"])
    players = pd.read_csv(_ruta_csv("players"), usecols=["nflId", "displayName", "officialPosition"])
    pff = pd.read_csv(_ruta_csv("pffScoutingData"), usecols=["gameId", "playId", "nflId", "pff_role"])
    return plays, games, players, pff


def _carril(texto: str) -> str | None:
    """Carril del pase o del scramble visto desde la ofensiva: izq, cen o der."""
    m = re.search(r"pass (?:incomplete )?(?:(?:short|deep) )?(left|middle|right)\b", texto)
    if m:
        return CARRILES[m.group(1)]
    if "scrambles up the middle" in texto:
        return "cen"
    m = re.search(r"scrambles (left|right)\b", texto)
    return CARRILES[m.group(1)] if m else None


def _partes_nombre(nombre: str) -> tuple[str, str]:
    """'Odell Beckham Jr.' -> ('Odell', 'Beckham'). Descarta sufijos como Jr., Sr., II o III."""
    t = nombre.replace(",", " ").split()
    while len(t) > 1 and t[-1].lower().strip(".") in SUFIJOS:
        t.pop()
    return t[0], " ".join(t[1:])


def _coincide(resto: str, nombre: str, apellido: str) -> bool:
    """¿'resto' empieza con el nombre abreviado del jugador? Ej.: 'C.Godwin', 'Aa.Rodgers'."""
    if not apellido:
        return False
    letras = re.sub(r"[^A-Za-z]", "", nombre)
    for k in (1, 2, 3):  # la NFL usa 1 a 3 letras del nombre para distinguir homónimos
        if len(letras) < k:
            break
        abreviado = f"{letras[0].upper()}{letras[1:k].lower()}.{apellido}"
        if re.match(re.escape(abreviado) + r"(?![A-Za-z'\-])", resto):
            return True
    return False


def _asignar_objetivo(base: pd.DataFrame, pff: pd.DataFrame, players: pd.DataFrame) -> pd.DataFrame:
    """Devuelve (gameId, playId, objetivo) con el nflId del receptor al que iba el pase.

    La descripción solo trae el nombre abreviado. Se compara con los jugadores ofensivos de esa
    misma jugada según PFF (rutas y bloqueo), así que casi nunca hay homónimos. Si no hay
    coincidencia única, la jugada queda sin objetivo.
    """
    nombres = players[["nflId", "displayName"]].copy()
    nombres[["nombre", "apellido"]] = [_partes_nombre(n) for n in nombres.displayName.fillna("?")]
    destinos = base[["gameId", "playId"]].assign(resto=base.texto.str.extract(RX_DESTINO)[0]).dropna()
    candidatos = (
        pff[pff.pff_role.isin(["Pass Route", "Pass Block"])][["gameId", "playId", "nflId"]]
        .merge(nombres[["nflId", "nombre", "apellido"]], on="nflId")
        .merge(destinos, on=["gameId", "playId"])
    )
    acierta = [_coincide(r, n, a) for r, n, a in zip(candidatos.resto, candidatos.nombre, candidatos.apellido)]
    unicos = candidatos[acierta].drop_duplicates(["gameId", "playId"], keep=False)
    return unicos[["gameId", "playId", "nflId"]].rename(columns={"nflId": "objetivo"})


def preparar_jugadas(
    plays: pd.DataFrame, games: pd.DataFrame, pff: pd.DataFrame, players: pd.DataFrame, yardas: int
) -> tuple[pd.DataFrame, dict]:
    """Jugadas de pase que arrancan dentro de las últimas `yardas`, listas para graficar.

    Devuelve (base, conteos). `base` ya excluye los intentos de 2 puntos y las jugadas anuladas.
    """
    j = plays.merge(games[["gameId", "week"]], on="gameId", how="left")

    # Si el replay revirtió la jugada, el resultado válido es el texto que sigue a "REVERSED."
    j["texto"] = j.playDescription.fillna("").str.rsplit("REVERSED.", n=1).str[-1].str.strip()

    # Yardas que faltan para la zona de anotación rival. La yarda 50 viene sin yardlineSide.
    campo_propio = j.yardlineSide == j.possessionTeam
    j["yardas"] = np.where(campo_propio, 100 - j.yardlineNumber, j.yardlineNumber)
    zona = j[j.yardas <= yardas].copy()

    # TD ofensivo: el texto lo dice, no fue anulado por penalización y el pase o scramble avanzó
    # justo hasta la goal line. La última condición descarta los TD de la defensa (intercepciones
    # y fumbles devueltos), que también dicen "TOUCHDOWN" pero no llegan a esa yarda.
    zona["td"] = (
        zona.texto.str.contains("TOUCHDOWN", regex=False)
        & ~zona.texto.str.contains("NULLIFIED", regex=False)
        & zona.passResult.isin(["C", "R"])
        & (zona.prePenaltyPlayResult == zona.yardas)
    )
    # C completo, R scramble, I incompleto, IN intercepción, S sack
    zona["res"] = np.where(zona.td, "TD", zona.passResult)

    es_2pt = zona.texto.str.contains("TWO-POINT", regex=False)
    anulada = zona.texto.str.contains("No Play", case=False, regex=False)
    conteos = {
        "en_zona": len(zona),
        "excluidas_2pt": int(es_2pt.sum()),
        "excluidas_anuladas": int((~es_2pt & anulada).sum()),
    }
    base = zona[~es_2pt & ~anulada].copy()

    base["carril"] = [_carril(t) for t in base.texto]
    qb = (
        pff[pff.pff_role == "Pass"][["gameId", "playId", "nflId"]]
        .drop_duplicates(["gameId", "playId"])
        .rename(columns={"nflId": "qb"})
    )
    base = base.merge(qb, on=["gameId", "playId"], how="left")
    base = base.merge(_asignar_objetivo(base, pff, players), on=["gameId", "playId"], how="left")
    conteos["analizadas"] = len(base)
    conteos["td"] = int(base.td.sum())
    return base, conteos


def _tabla_jugadores(base: pd.DataFrame, players: pd.DataFrame) -> dict:
    """Ficha (nombre, posición, equipo) de cada quarterback y receptor que aparece en `base`."""
    largo = pd.concat(
        [
            base[["qb", "possessionTeam"]].rename(columns={"qb": "id"}),
            base[["objetivo", "possessionTeam"]].rename(columns={"objetivo": "id"}),
        ]
    ).dropna(subset=["id"])
    largo["id"] = largo["id"].astype(int)
    equipo = largo.groupby("id").possessionTeam.agg(lambda s: s.mode().iat[0])
    fichas = players.set_index("nflId")
    return {
        int(i): {
            "n": str(fichas.at[i, "displayName"]),
            "pos": str(fichas.at[i, "officialPosition"]),
            "eq": eq,
        }
        for i, eq in equipo.items()
        if i in fichas.index
    }


def _entero(x) -> int | None:
    return int(x) if pd.notna(x) else None


def construir_datos(yardas: int = 20) -> tuple[dict, pd.DataFrame]:
    """Devuelve (datos para el HTML, base de jugadas en pandas)."""
    plays, games, players, pff = cargar_datos()
    base, conteos = preparar_jugadas(plays, games, pff, players, yardas)
    jugadas = [
        {
            "y": int(r.yardas),
            "c": r.carril if isinstance(r.carril, str) else None,
            "d": int(r.down),
            "r": r.res,
            "cob": r.pff_passCoverageType if isinstance(r.pff_passCoverageType, str) else "Other",
            "eq": r.possessionTeam,
            "rv": r.defensiveTeam,
            "sem": int(r.week),
            "q": int(r.quarter),
            "qb": _entero(r.qb),
            "ob": _entero(r.objetivo),
            "txt": r.texto,
        }
        for r in base.itertuples()
    ]
    datos = {
        "meta": {
            "temporada": int(games.season.iloc[0]),
            "semanas": [int(games.week.min()), int(games.week.max())],
            "juegos": int(games.gameId.nunique()),
            "pases_total": len(plays),
            "yardas": yardas,
            **conteos,
        },
        "jugadores": _tabla_jugadores(base, players),
        "jugadas": jugadas,
    }
    return datos, base


def generar_html(datos: dict) -> str:
    """Inserta los datos en la plantilla. Escribe '<' como \\u003c para que ningún texto cierre el <script>."""
    cargado = json.dumps(datos, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return PLANTILLA.read_text(encoding="utf-8").replace("__DATOS__", cargado)


def _resumen(base: pd.DataFrame, conteos: dict, yardas: int) -> str:
    def tasa(df: pd.DataFrame) -> str:
        return f"{df.td.mean():.1%} ({int(df.td.sum())} TD en {len(df)})"

    lineas = [
        f"Jugadas de pase en las últimas {yardas} yardas: {conteos['en_zona']:,}",
        f"  excluidas: {conteos['excluidas_2pt']} intentos de 2 puntos y {conteos['excluidas_anuladas']} jugadas anuladas",
        f"  analizadas: {conteos['analizadas']:,}, con {conteos['td']} touchdowns ofensivos",
        f"Probabilidad de TD: yardas 1-5 {tasa(base[base.yardas <= 5])}",
    ]
    if yardas > 5:
        lineas.append(f"                    yardas 6-10 {tasa(base[(base.yardas > 5) & (base.yardas <= 10)])}")
    if yardas > 10:
        lineas.append(f"                    yardas 11-{yardas} {tasa(base[base.yardas > 10])}")
    return "\n".join(lineas)


def main() -> None:
    ap = argparse.ArgumentParser(description="Genera el mapa interactivo de probabilidad de touchdown.")
    ap.add_argument("--yardas", type=int, default=20, help="yardas finales a mostrar, de 5 a 30 (por defecto 20)")
    ap.add_argument("--salida", type=Path, default=SALIDA, help="archivo HTML de salida")
    args = ap.parse_args()
    if not 5 <= args.yardas <= 30:
        ap.error("--yardas debe estar entre 5 y 30")

    datos, base = construir_datos(args.yardas)
    args.salida.write_text(generar_html(datos), encoding="utf-8")
    print(_resumen(base, datos["meta"], args.yardas))
    print(f"Archivo: {args.salida} ({args.salida.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
