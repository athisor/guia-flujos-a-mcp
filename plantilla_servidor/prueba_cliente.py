r"""Prueba de punta a punta: arranca el servidor por stdio, como lo hace Claude Code, y llama cada función.

    uv run prueba_cliente.py          (desde esta carpeta)

Escribe solo en una carpeta temporal (MCP_SALIDAS apunta ahí). Sale con código 0 si todo pasa.
Copia este archivo a cada servidor nuevo y cambia los pasos: se corre antes de registrar y antes de cada PR.
"""
from __future__ import annotations

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
TMP = Path(tempfile.mkdtemp(prefix="prueba_plantilla_"))
SERVIDOR = StdioServerParameters(command=sys.executable, args=[str(AQUI / "servidor.py")],
                                 env={**os.environ, "MCP_SALIDAS": str(TMP)})
fallas = 0


def paso(nombre: str, ok: bool, detalle="") -> None:
    global fallas
    fallas += not ok
    print(f"[{'OK' if ok else 'FALLA'}] {nombre}  {str(detalle)[:200]}", flush=True)


def datos(r) -> dict:
    """Contenido estructurado (SDK 2.x: structured_content; 1.x: structuredContent) o el texto como JSON."""
    sc = getattr(r, "structured_content", None) or getattr(r, "structuredContent", None)
    if sc is not None:
        return sc.get("result", sc) if isinstance(sc, dict) and set(sc) == {"result"} else sc
    return json.loads(r.content[0].text)


def es_error(r) -> bool:
    return bool(getattr(r, "is_error", None) or getattr(r, "isError", None))


async def main() -> None:
    async with stdio_client(SERVIDOR) as (leer, escribir):
        async with ClientSession(leer, escribir) as s:
            await s.initialize()
            nombres = {t.name for t in (await s.list_tools()).tools}
            esperadas = {"carpeta_resumen", "sesiones_repetidas", "nota_escribir", "trabajo_lanzar", "trabajo_estado"}
            paso("lista de herramientas", esperadas <= nombres, sorted(nombres))

            r = await s.call_tool("carpeta_resumen", {"ruta": str(AQUI)})
            paso("carpeta_resumen", not es_error(r) and datos(r)["archivos"] >= 3, datos(r).get("por_extension"))

            r = await s.call_tool("carpeta_resumen", {"ruta": str(AQUI / "no_existe")})
            msg = r.content[0].text if r.content else ""
            paso("ruta inexistente = error claro (el mensaje llega al agente)", es_error(r) and "no es una carpeta" in msg, msg)

            r = await s.call_tool("nota_escribir", {"nombre": "prueba", "texto": "hola"})
            d = datos(r)
            paso("nota_escribir simula por defecto", d["simulado"] and not Path(d["destino"]).exists(), d)

            r = await s.call_tool("nota_escribir", {"nombre": "prueba", "texto": "hola", "confirmar": True})
            d = datos(r)
            paso("nota_escribir con confirmar escribe dentro de salidas",
                 not d["simulado"] and Path(d["destino"]).read_text(encoding="utf-8") == "hola" and str(TMP) in d["destino"], d)

            r = await s.call_tool("nota_escribir", {"nombre": "prueba", "texto": "otra", "confirmar": True})
            paso("no pisa un archivo existente", es_error(r))

            r = await s.call_tool("nota_escribir", {"nombre": "../fuera", "texto": "x", "confirmar": True})
            paso("no escribe fuera de salidas", es_error(r))

            r = await s.call_tool("trabajo_lanzar", {"funcion": "sesiones_repetidas", "args": {"dias": 2, "max_items": 5, "max_archivos": 30}})
            tid = datos(r)["id"]
            paso("trabajo_lanzar devuelve id", bool(tid), tid)
            estado = {}
            for _ in range(120):
                estado = datos(await s.call_tool("trabajo_estado", {"id": tid}))
                if estado["estado"] != "corriendo":
                    break
                time.sleep(1)
            # Sin historial de Claude Code (instalación nueva) el trabajo termina en error claro: también vale.
            paso("trabajo termina (listo o error claro)", estado["estado"] in ("listo", "error"),
                 {k: estado.get(k) for k in ("estado", "segundos", "error")})
            if estado["estado"] == "listo":
                res = estado["resultado"]
                paso("sesiones_repetidas trae tablas", {"comandos", "skills", "mcp"} <= set(res), res.get("sesiones_leidas"))

    print(f"\n{'TODO OK' if not fallas else f'{fallas} FALLAS'}  (salidas de prueba en {TMP})")


if __name__ == "__main__":
    anyio.run(main)
    sys.exit(1 if fallas else 0)
