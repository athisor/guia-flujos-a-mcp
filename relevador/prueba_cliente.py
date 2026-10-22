r"""Prueba de punta a punta del relevador: arranca el servidor por stdio y llama sus funciones sobre un proyecto de mentira.

    uv run prueba_cliente.py          (desde esta carpeta)

Arma en una carpeta temporal: dos proyectos (con un script repetido entre ambos, una skill, una CLI citada en la documentación),
un repo de MCP falso con una función, scratchpads de dos sesiones con el mismo script y un historial .jsonl. Todo es solo lectura:
al final comprueba que ningún archivo de la carpeta de prueba cambió.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

AQUI = Path(__file__).resolve().parent
TMP = Path(tempfile.mkdtemp(prefix="prueba_relevador_"))
fallas = 0

CLI = '''"""Convierte una planilla CSV en un informe Markdown."""
import argparse
def convertir(entrada, salida):
    pass
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada"); ap.add_argument("--salida")
    a = ap.parse_args(); convertir(a.entrada, a.salida)
'''
SUBE = '''"""Sube resultados al servidor."""
import argparse, requests
ap = argparse.ArgumentParser(); ap.add_argument("--url")
requests.post(ap.parse_args().url, json={})
'''


def armar() -> dict:
    a, b = TMP / "proyectos" / "alfa", TMP / "proyectos" / "beta"
    for p in (a, b):
        (p / "scripts").mkdir(parents=True)
        (p / "CLAUDE.md").write_text("Usar scripts/planilla_informe.py para los informes.\n", encoding="utf-8")
        (p / "scripts" / "planilla_informe.py").write_text(CLI, encoding="utf-8")
    (a / "scripts" / "subir.py").write_text(SUBE, encoding="utf-8")
    (a / "scripts" / "tmp_fix.py").write_text("print(1)\n", encoding="utf-8")
    (a / "README.md").write_text("planilla_informe.py, planilla_informe.py\n", encoding="utf-8")
    (a / ".claude" / "skills" / "informes").mkdir(parents=True)
    (a / ".claude" / "skills" / "informes" / "SKILL.md").write_text("---\nname: informes\ndescription: Arma informes\n---\n", encoding="utf-8")
    (b / ".claude" / "skills" / "informes").mkdir(parents=True)
    (b / ".claude" / "skills" / "informes" / "SKILL.md").write_text("---\nname: informes\ndescription: Arma informes\n---\n", encoding="utf-8")
    mcp = TMP / "repo_mcp" / "documentos"
    mcp.mkdir(parents=True)
    (mcp / "api.py").write_text('def pdf_texto(ruta: str) -> dict:\n    """Texto de un PDF."""\n', encoding="utf-8")
    for s in ("s1", "s2", "s3"):
        pad = TMP / "pads" / "proy-alfa" / s / "scratchpad"
        pad.mkdir(parents=True)
        (pad / f"medir_tamanos{'_v2' if s == 's2' else ''}.py").write_text(
            "import os, sys\nfor raiz, dirs, archivos in os.walk(sys.argv[1]):\n    print(raiz, sum(os.path.getsize(os.path.join(raiz, f)) for f in archivos))\n",
            encoding="utf-8")
    hist = TMP / "historial" / "C--proyectos-alfa"
    hist.mkdir(parents=True)
    for s in ("s1", "s2"):
        lineas = [{"type": "assistant", "cwd": str(a), "message": {"content": [
            {"type": "tool_use", "name": "Bash", "input": {"command": "cd x && python scripts/planilla_informe.py --entrada a.csv"}},
            {"type": "tool_use", "name": "Bash", "input": {"command": "ls -la"}},
            {"type": "tool_use", "name": "Skill", "input": {"skill": "informes"}},
            {"type": "tool_use", "name": "mcp__documentos__pdf_texto", "input": {}}]}}]
        (hist / f"{s}.jsonl").write_text("\n".join(json.dumps(l) for l in lineas) + "\n", encoding="utf-8")
    return {"alfa": a, "beta": b, "mcp": TMP / "repo_mcp", "pads": TMP / "pads", "hist": TMP / "historial"}


def huella() -> str:
    h = hashlib.sha1()
    for p in sorted(TMP.rglob("*")):
        if p.is_file():
            h.update(str(p).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def paso(nombre: str, ok: bool, detalle="") -> None:
    global fallas
    fallas += not ok
    print(f"[{'OK' if ok else 'FALLA'}] {nombre}  {str(detalle)[:220]}", flush=True)


def datos(r) -> dict:
    sc = getattr(r, "structured_content", None) or getattr(r, "structuredContent", None)
    if sc is not None:
        return sc.get("result", sc) if isinstance(sc, dict) and set(sc) == {"result"} else sc
    return json.loads(r.content[0].text)


async def main() -> None:
    rutas = armar()
    antes = huella()
    salidas = Path(tempfile.mkdtemp(prefix="prueba_relevador_salidas_"))
    srv = StdioServerParameters(command=sys.executable, args=[str(AQUI / "servidor.py")], env={**os.environ, "MCP_SALIDAS": str(salidas)})
    async with stdio_client(srv) as (leer, escribir):
        async with ClientSession(leer, escribir) as s:
            await s.initialize()
            nombres = {t.name for t in (await s.list_tools()).tools}
            paso("herramientas", {"proyecto_inventariar", "proyecto_candidatos", "scratchpads_revisar", "sesiones_repetidas",
                                  "trabajo_lanzar", "trabajo_estado"} <= nombres, sorted(nombres))

            d = datos(await s.call_tool("proyecto_inventariar", {"ruta": str(rutas["alfa"])}))
            cli = {x["nombre"]: x for x in d["scripts"]}
            paso("inventario: tarjeta con CLI, argumentos y citas", cli["planilla_informe.py"]["cli"] == "argparse"
                 and "--entrada" in cli["planilla_informe.py"]["argumentos"] and cli["planilla_informe.py"]["citas"] >= 2, cli["planilla_informe.py"])
            paso("inventario: skills", [x["nombre"] for x in d["elementos"]["skills"]] == ["informes"], d["elementos"]["skills"])

            d = datos(await s.call_tool("proyecto_candidatos", {"ruta": str(rutas["alfa"]), "otras_raices": [str(TMP / "proyectos")],
                                                                "repo_mcp": str(rutas["mcp"]), "niveles": list(("mcp", "ya_existe", "herramienta_repo", "script_sesion"))}))
            por = {c["nombre"]: c for c in d["candidatos"]}
            paso("candidatos: el script repetido en otro proyecto sube a mcp", por["planilla_informe.py"]["nivel"] == "mcp", por["planilla_informe.py"]["razones"])
            paso("candidatos: lo que escribe afuera trae aviso", any("servicio externo" in a for a in por["subir.py"]["avisos"]), por["subir.py"]["avisos"])
            paso("candidatos: el script de una vez no sube", por["tmp_fix.py"]["nivel"] == "script_sesion", por["tmp_fix.py"]["razones"])
            paso("candidatos: skill repetida entre proyectos", por["informes"]["nivel"] == "herramienta_repo", por["informes"]["razones"])

            d = datos(await s.call_tool("scratchpads_revisar", {"carpeta": str(rutas["pads"]), "dias": 0}))
            rep = {r["familia"]: r for r in d["repetidos"]}
            paso("scratchpads: misma familia en 3 sesiones (con _v2)", rep.get("medir_tamanos", {}).get("sesiones") == 3, d["repetidos"][:1])

            t = datos(await s.call_tool("trabajo_lanzar", {"funcion": "sesiones_repetidas", "args": {"carpeta": str(rutas["hist"]), "dias": 0}}))
            est = {}
            for _ in range(60):
                est = datos(await s.call_tool("trabajo_estado", {"id": t["id"]}))
                if est["estado"] != "corriendo":
                    break
                time.sleep(1)
            res = est.get("resultado", {})
            coms = {c["que"]: c for c in res.get("comandos", [])}
            paso("sesiones (como trabajo): script contado en 2 sesiones, 'cd' y 'ls' ignorados",
                 est["estado"] == "listo" and coms.get("script: planilla_informe.py", {}).get("sesiones") == 2 and not any("ls" in k for k in coms),
                 list(coms))
            paso("sesiones: skills y MCP", res.get("skills", [{}])[0].get("que") == "informes" and res.get("mcp", [{}])[0].get("que") == "mcp__documentos__pdf_texto")

            r = await s.call_tool("proyecto_candidatos", {"ruta": str(TMP / "no_existe")})
            paso("ruta inexistente = error claro", bool(getattr(r, "is_error", None) or getattr(r, "isError", None))
                 and "no es una carpeta" in r.content[0].text, r.content[0].text)

    paso("solo lectura: nada cambió en la carpeta de prueba", huella() == antes)
    print(f"\n{'TODO OK' if not fallas else f'{fallas} FALLAS'}  (datos de prueba en {TMP})")


if __name__ == "__main__":
    anyio.run(main)
    sys.exit(1 if fallas else 0)
