r"""Funciones del servidor `plantilla`: una sola fuente para la CLI y para el MCP.

Regla de la plantilla: TODA la lógica vive aquí, como funciones normales de Python con tipos y docstring.
- `servidor.py` las publica como herramientas MCP (no repite lógica).
- Esta misma API se usa por consola, sin MCP:

    python api.py lista
    python api.py llamar carpeta_resumen --json '{"ruta": "."}'
    python api.py llamar carpeta_resumen --json-archivo args.json     # en PowerShell, más cómodo que escapar comillas

La respuesta de `llamar` es UN JSON en stdout: {"ok": true, "resultado": ...} o {"ok": false, "error": ...}.
Los mensajes de diagnóstico van a stderr. Solo biblioteca estándar: el servidor se mantiene liviano.

Para tu propio servidor: borra las funciones de ejemplo, escribe las tuyas y agrégalas a FUNCIONES (abajo).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

NOMBRE = "plantilla"

# Lo que el agente lee SIEMPRE al conectar: reglas cortas (qué llamar primero, qué es LARGO, qué pide confirmar).
INSTRUCCIONES = (
    "Plantilla de servidor MCP. carpeta_resumen y nota_escribir responden al instante; sesiones_repetidas es LARGA: "
    "usa trabajo_lanzar('sesiones_repetidas', {...}) y trabajo_estado(id) cada 20-60 s. "
    "nota_escribir SIMULA por defecto: confirmar=true solo con un sí explícito del usuario en el chat."
)

# Dónde PUEDE escribir este servidor. Nada fuera de aquí. Se cambia con la variable de entorno MCP_SALIDAS.
SALIDAS = Path(os.environ.get("MCP_SALIDAS", Path.home() / "mcp_salidas")) / NOMBRE


class ErrorUso(Exception):
    """Error del que llama (argumento malo, ruta que no existe). Se devuelve como mensaje claro, sin traza."""


# --------------------------------------------------------------------------- utilidades

def _dentro_de(ruta: Path, raiz: Path) -> bool:
    try:
        ruta.resolve().relative_to(raiz.resolve())
        return True
    except ValueError:
        return False


def _recortar(lista: list, n: int) -> tuple[list, bool]:
    return lista[:n], len(lista) > n


# --------------------------------------------------------------------------- funciones publicadas

def carpeta_resumen(ruta: str, max_items: int = 15) -> dict:
    """Resume una carpeta: archivos por extensión, tamaño total y los más grandes. Solo lectura.

    Ignora .git, .venv, node_modules y __pycache__. Respuesta corta: cifras y rutas, nunca el contenido.
    """
    raiz = Path(ruta).expanduser()
    if not raiz.is_dir():
        raise ErrorUso(f"no es una carpeta: {raiz}")
    ignorar = {".git", ".venv", "venv", "node_modules", "__pycache__"}
    por_ext: Counter = Counter()
    bytes_ext: Counter = Counter()
    grandes: list[tuple[int, str]] = []
    n = 0
    for dirpath, dirnames, filenames in os.walk(raiz):
        dirnames[:] = [d for d in dirnames if d not in ignorar]
        for f in filenames:
            p = Path(dirpath) / f
            try:
                t = p.stat().st_size
            except OSError:
                continue
            ext = p.suffix.lower() or "(sin extensión)"
            por_ext[ext] += 1
            bytes_ext[ext] += t
            grandes.append((t, str(p.relative_to(raiz))))
            n += 1
    grandes.sort(reverse=True)
    return {
        "ruta": str(raiz.resolve()),
        "archivos": n,
        "mb_total": round(sum(bytes_ext.values()) / 1e6, 2),
        "por_extension": [{"ext": e, "archivos": c, "mb": round(bytes_ext[e] / 1e6, 2)} for e, c in por_ext.most_common(max_items)],
        "mas_grandes": [{"ruta": r, "mb": round(t / 1e6, 2)} for t, r in grandes[:max_items]],
    }


_SCRIPT = re.compile(r"([\w.\-/\\:~]+\.(?:py|ps1|sh|bat|cmd|js|mjs|ts))\b", re.I)


def _clave_comando(cmd: str) -> str:
    """Normaliza un comando para contar repeticiones: el script que corre, o las dos primeras palabras."""
    m = _SCRIPT.search(cmd)
    if m:
        return "script: " + re.split(r"[\\/]", m.group(1))[-1]
    primera = re.split(r"\s*(?:\|\||&&|;|\|)\s*", cmd.strip(), maxsplit=1)[0]
    partes = primera.split()
    return "cmd: " + " ".join(partes[:2]) if partes else ""


def sesiones_repetidas(carpeta: str = "", dias: int = 60, max_items: int = 25, max_archivos: int = 2000) -> dict:
    """Lee el historial de Claude Code (~/.claude/projects/*.jsonl) y cuenta lo que más se repite. Solo lectura.

    Cuenta comandos de consola (normalizados: el script que corren o sus dos primeras palabras), skills y
    herramientas MCP usadas, con cuántas sesiones y cuántos proyectos distintos. Es el punto de partida
    para decidir qué convertir en herramienta: lo que aparece en muchas sesiones o en varios proyectos.
    `dias` limita a las sesiones modificadas en ese período (0 = todas).
    """
    base = Path(carpeta).expanduser() if carpeta else Path.home() / ".claude" / "projects"
    if not base.is_dir():
        raise ErrorUso(f"no hay historial en {base}")
    limite = time.time() - dias * 86400 if dias > 0 else 0
    archivos = sorted((p for p in base.rglob("*.jsonl") if p.stat().st_mtime >= limite),
                      key=lambda p: p.stat().st_mtime, reverse=True)
    archivos, recortado = _recortar(archivos, max_archivos)

    usos: dict[str, dict[str, Counter]] = {"comandos": defaultdict(Counter), "skills": defaultdict(Counter),
                                            "mcp": defaultdict(Counter)}
    sesiones: dict[str, dict[str, set]] = {k: defaultdict(set) for k in usos}
    proyectos: dict[str, dict[str, set]] = {k: defaultdict(set) for k in usos}
    lineas_malas = 0
    for f in archivos:
        sesion = f.stem
        try:
            texto = f.open(encoding="utf-8", errors="replace")
        except OSError:
            continue
        with texto:
            for linea in texto:
                if '"tool_use"' not in linea:
                    continue
                try:
                    d = json.loads(linea)
                except json.JSONDecodeError:
                    lineas_malas += 1
                    continue
                proyecto = d.get("cwd") or f.parent.name
                for c in (d.get("message") or {}).get("content") or []:
                    if not isinstance(c, dict) or c.get("type") != "tool_use":
                        continue
                    nombre, entrada = c.get("name", ""), c.get("input") or {}
                    if nombre in ("Bash", "PowerShell") and isinstance(entrada.get("command"), str):
                        tipo, clave = "comandos", _clave_comando(entrada["command"])
                    elif nombre == "Skill":
                        tipo, clave = "skills", str(entrada.get("skill", "?"))
                    elif nombre.startswith("mcp__"):
                        tipo, clave = "mcp", nombre
                    else:
                        continue
                    if not clave:
                        continue
                    usos[tipo][clave]["veces"] += 1
                    sesiones[tipo][clave].add(sesion)
                    proyectos[tipo][clave].add(proyecto)

    def tabla(tipo: str) -> list[dict]:
        filas = [{"que": k, "veces": v["veces"], "sesiones": len(sesiones[tipo][k]), "proyectos": len(proyectos[tipo][k])}
                 for k, v in usos[tipo].items()]
        # Lo que se repite en más sesiones y proyectos pesa más que lo que se llamó mil veces en una sola.
        filas.sort(key=lambda r: (r["proyectos"], r["sesiones"], r["veces"]), reverse=True)
        return filas[:max_items]

    return {
        "historial": str(base),
        "sesiones_leidas": len(archivos),
        "recortado": recortado,
        "lineas_ilegibles": lineas_malas,
        "comandos": tabla("comandos"),
        "skills": tabla("skills"),
        "mcp": tabla("mcp"),
        "pista": "Candidato a herramienta: aparece en >=3 sesiones o en >=2 proyectos. Revisar antes de construir.",
    }


def nota_escribir(nombre: str, texto: str, confirmar: bool = False) -> dict:
    """Escribe una nota .md en la carpeta de salidas del servidor. SIMULA por defecto.

    Ejemplo del patrón para funciones que escriben: sin confirmar=true devuelve el plan y no toca nada;
    nunca escribe fuera de SALIDAS; nunca pisa un archivo existente.
    """
    if not re.fullmatch(r"[\w\-]{1,80}", nombre):
        raise ErrorUso("nombre: solo letras, números, '_' o '-' (sin extensión ni carpetas)")
    destino = SALIDAS / "notas" / f"{nombre}.md"
    if not _dentro_de(destino, SALIDAS):
        raise ErrorUso("destino fuera de la carpeta de salidas")
    if destino.exists():
        raise ErrorUso(f"ya existe {destino}; elige otro nombre (este servidor no pisa archivos)")
    plan = {"destino": str(destino), "bytes": len(texto.encode("utf-8"))}
    if not confirmar:
        return {"simulado": True, **plan, "aviso": "No se escribió nada. Repite con confirmar=true si el usuario dijo que sí."}
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    return {"simulado": False, **plan}


# Registro: nombre -> (función, es_larga). Las LARGAS se publican también por trabajo_lanzar.
FUNCIONES = {
    "carpeta_resumen": (carpeta_resumen, False),
    "sesiones_repetidas": (sesiones_repetidas, True),
    "nota_escribir": (nota_escribir, False),
}


# --------------------------------------------------------------------------- CLI

def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="api.py", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="orden", required=True)
    sub.add_parser("lista", help="funciones disponibles")
    ll = sub.add_parser("llamar", help="llama una función con argumentos JSON")
    ll.add_argument("funcion")
    g = ll.add_mutually_exclusive_group()
    g.add_argument("--json", default="{}", help="argumentos como texto JSON")
    g.add_argument("--json-archivo", help="argumentos en un archivo JSON (evita escapar comillas)")
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
        resp = {"ok": True, "resultado": FUNCIONES[a.funcion][0](**args)}
        rc = 0
    except (ErrorUso, TypeError, json.JSONDecodeError) as e:
        resp, rc = {"ok": False, "error": str(e)}, 2
    except Exception as e:  # noqa: BLE001 — la CLI siempre contesta JSON
        resp, rc = {"ok": False, "error": f"{type(e).__name__}: {e}"}, 1
    txt = json.dumps(resp, ensure_ascii=False, indent=1)
    if a.salida:
        Path(a.salida).write_text(txt, encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(txt)
    return rc


if __name__ == "__main__":
    raise SystemExit(_main())
