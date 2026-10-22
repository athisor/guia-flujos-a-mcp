r"""Funciones del servidor `relevador`: encontrar qué scripts conviene convertir en herramientas. SOLO LECTURA.

La lógica está en `escaner.py`; aquí solo se publica, con respuestas cortas y paginadas.

    python api.py lista
    python api.py llamar proyecto_candidatos --json-archivo args.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import escaner as E  # noqa: E402

NOMBRE = "relevador"

# Este servidor no escribe resultados; solo guarda ahí el estado de sus trabajos largos. Variable MCP_SALIDAS.
SALIDAS = Path(os.environ.get("MCP_SALIDAS", Path.home() / "mcp_salidas")) / NOMBRE

INSTRUCCIONES = (
    "Encuentra scripts que conviene convertir en herramientas. TODO es solo lectura. "
    "Orden: sesiones_repetidas y scratchpads_revisar (qué se repite entre sesiones) -> proyecto_candidatos(ruta) por proyecto "
    "(ranking con nivel mcp / ya_existe / herramienta_repo / script_sesion) -> proyecto_inventariar(ruta) para el detalle. "
    "Las cuatro pueden tardar: trabajo_lanzar + trabajo_estado. Es heurística: muéstrale la tabla al usuario y construye solo con su sí."
)

# Repo de servidores MCP con el que se comparan los candidatos (para marcar 'ya_existe'). Variable RELEVADOR_REPO_MCP.
REPO_MCP = os.environ.get("RELEVADOR_REPO_MCP", "")


class ErrorUso(Exception):
    """Error del que llama: se devuelve como mensaje claro, sin traza."""


def _carpeta(ruta: str) -> Path:
    p = Path(ruta).expanduser()
    if not p.is_dir():
        raise ErrorUso(f"no es una carpeta: {p}")
    return p


def proyecto_inventariar(ruta: str, profundidad: int = 4, filtro: str = "", solo_cli: bool = False,
                         desde: int = 0, max_filas: int = 40) -> dict:
    """Inventario de UN proyecto: tarjeta de cada script (qué hace, CLI y argumentos, qué escribe, citas, prueba) y skills, agentes, comandos, hooks y MCP."""
    inv = E.inventariar(_carpeta(ruta), profundidad)
    filas = [s for s in inv["scripts"] if (not filtro or filtro.lower() in s["ruta"].lower() or filtro.lower() in s["doc"].lower())
             and (not solo_cli or s["cli"])]
    filas.sort(key=lambda s: s["ruta"])
    pagina = [{k: v for k, v in s.items() if k not in ("imports", "hash")} for s in filas[desde:desde + max_filas]]
    el = inv["elementos"]
    return {
        "raiz": inv["raiz"], "scripts_total": len(inv["scripts"]), "filtrados": len(filas), "documentos": inv["documentos"],
        "scripts": pagina, "siguiente": desde + max_filas if desde + max_filas < len(filas) else None,
        "elementos": {k: (v if k in ("guias", "hooks", "mcp_declarados") else [{"nombre": x["nombre"], "descripcion": x.get("descripcion", "")[:120]} for x in v])
                      for k, v in el.items()},
        "omitidos": inv["omitidos"][:20],
    }


def proyecto_candidatos(ruta: str, otras_raices: list[str] | None = None, repo_mcp: str = "", profundidad: int = 4,
                        niveles: list[str] | None = None, max_filas: int = 30) -> dict:
    """Ranking de lo que conviene subir de nivel en un proyecto (mcp, ya_existe, herramienta_repo, script_sesion), con razones y avisos.

    `otras_raices`: otros proyectos (o carpetas que los contienen) para detectar copias y variantes del mismo script.
    `repo_mcp`: el repo de servidores MCP, para marcar lo que ya existe (def. variable RELEVADOR_REPO_MCP).
    """
    rm = repo_mcp or REPO_MCP
    r = E.evaluar(_carpeta(ruta), otras_raices or [], Path(rm).expanduser() if rm else None, profundidad)
    items = r["items"]
    conteo = {n: sum(1 for i in items if i["nivel"] == n) for n in E.ORDEN_NIVEL}
    niveles = niveles or ["mcp", "ya_existe", "herramienta_repo"]
    filas = [i for i in items if i["nivel"] in niveles]
    return {"raiz": str(Path(ruta).expanduser()), "por_nivel": conteo, "catalogo_funciones": r["catalogo_funciones"],
            "candidatos": filas[:max_filas], "recortado": len(filas) > max_filas,
            "aviso": "Heurística estática: revisar cada fila antes de construir y pedir el sí del usuario."}


def scratchpads_revisar(carpeta: str = "", dias: int = 90, min_sesiones: int = 2, max_items: int = 25) -> dict:
    """Scripts de los scratchpads de Claude Code que se reescribieron en varias sesiones (misma familia de nombre o mismo contenido).

    Por omisión busca en <temporal>/claude/<proyecto>/<sesión>/scratchpad. `carpeta` fuerza otra raíz.
    """
    if carpeta:
        _carpeta(carpeta)
    r = E.revisar_scratchpads(carpeta, dias, max_items, min_sesiones)
    if not r["scratchpads"]:
        r["aviso"] = "No se encontraron scratchpads. Si Claude Code los guarda en otra carpeta, pásala en `carpeta`."
    return r


def sesiones_repetidas(carpeta: str = "", dias: int = 60, max_items: int = 25, max_archivos: int = 2000) -> dict:
    """Historial de Claude Code (~/.claude/projects): comandos, scripts, skills y herramientas MCP que más se repiten, por sesiones y proyectos."""
    try:
        return E.sesiones_repetidas(carpeta, dias, max_items, max_archivos)
    except FileNotFoundError as e:
        raise ErrorUso(str(e)) from None


# nombre -> (función, es_larga)
FUNCIONES = {
    "proyecto_inventariar": (proyecto_inventariar, True),
    "proyecto_candidatos": (proyecto_candidatos, True),
    "scratchpads_revisar": (scratchpads_revisar, True),
    "sesiones_repetidas": (sesiones_repetidas, True),
}


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="api.py", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="orden", required=True)
    sub.add_parser("lista", help="funciones disponibles")
    ll = sub.add_parser("llamar", help="llama una función con argumentos JSON")
    ll.add_argument("funcion")
    g = ll.add_mutually_exclusive_group()
    g.add_argument("--json", default="{}", help="argumentos como texto JSON")
    g.add_argument("--json-archivo", help="argumentos en un archivo JSON")
    ll.add_argument("--salida", help="además de stdout, guarda la respuesta en este archivo (lo usa trabajo_lanzar)")
    a = ap.parse_args(argv)
    if a.orden == "lista":
        for n, (f, larga) in FUNCIONES.items():
            print(f"{n}{'  [LARGA]' if larga else ''}: {(f.__doc__ or '').strip().splitlines()[0]}")
        return 0
    try:
        args = json.loads(Path(a.json_archivo).read_text(encoding="utf-8-sig") if a.json_archivo else a.json)
        if a.funcion not in FUNCIONES:
            raise ErrorUso(f"función desconocida '{a.funcion}'. Hay: {', '.join(FUNCIONES)}")
        resp, rc = {"ok": True, "resultado": FUNCIONES[a.funcion][0](**args)}, 0
    except (ErrorUso, TypeError, json.JSONDecodeError) as e:
        resp, rc = {"ok": False, "error": str(e)}, 2
    except Exception as e:  # noqa: BLE001
        resp, rc = {"ok": False, "error": f"{type(e).__name__}: {e}"}, 1
    txt = json.dumps(resp, ensure_ascii=False, indent=1)
    if a.salida:
        Path(a.salida).write_text(txt, encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(txt)
    return rc


if __name__ == "__main__":
    raise SystemExit(_main())
