r"""Servidor MCP `plantilla` (stdio). Publica como herramientas las funciones de `api.py` y añade trabajos largos con id.

No contiene lógica propia: todo lo que hace está en `api.py`, que también sirve por consola. Este archivo se copia TAL CUAL
a cada servidor nuevo: el nombre, las instrucciones y las funciones salen de `api.py` (NOMBRE, INSTRUCCIONES, FUNCIONES).
Reglas que cumple (y que tu servidor debe cumplir):
- Nada a stdout salvo el protocolo MCP: los logs van a stderr.
- Respuestas cortas (cifras y rutas en JSON).
- Lo LARGO no bloquea: trabajo_lanzar devuelve un id al instante y trabajo_estado se consulta cada 20-60 s.
  El trabajo corre en un proceso aparte, así que sobrevive si se cierra la sesión.

Se arranca así (lo hace Claude Code al registrarlo):  uv run --directory <esta carpeta> servidor.py
"""
from __future__ import annotations

import functools
import json
import logging
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

try:  # SDK `mcp` 2.x: FastMCP pasó a llamarse MCPServer
    from mcp.server.mcpserver import MCPServer as _Servidor
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # SDK `mcp` 1.x
    from mcp.server.fastmcp import FastMCP as _Servidor
    from mcp.server.fastmcp.exceptions import ToolError

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import api  # noqa: E402

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(api.NOMBRE)

TRABAJOS = api.SALIDAS / "trabajos"

servidor = _Servidor(api.NOMBRE, instructions=api.INSTRUCCIONES)


def _publicar(funcion):
    """Registra una función de api.py. Un ErrorUso llega al agente como mensaje claro (ToolError);
    cualquier otra excepción el SDK la reporta como fallo genérico y deja la traza en stderr."""
    @functools.wraps(funcion)  # conserva nombre, firma y docstring: de ahí salen el esquema y la descripción
    def envuelta(*a, **k):
        try:
            return funcion(*a, **k)
        except api.ErrorUso as e:
            raise ToolError(str(e)) from None
    return envuelta


for _nombre, (_funcion, _larga) in api.FUNCIONES.items():
    servidor.tool(name=_nombre)(_publicar(_funcion))


# --------------------------------------------------------------------------- trabajos largos

def _vivo(pid: int) -> bool:
    if os.name == "nt":
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        codigo = ctypes.c_ulong()
        k32.GetExitCodeProcess(h, ctypes.byref(codigo))
        k32.CloseHandle(h)
        return codigo.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _lanzar_desacoplado(cmd: list[str], log_archivo: Path) -> int:
    salida = log_archivo.open("w", encoding="utf-8")
    if os.name == "nt":
        base = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
        try:  # Claude Code mata los hijos de la sesión al cerrar; BREAKAWAY los saca de ese grupo si se puede
            p = subprocess.Popen(cmd, stdout=salida, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                 creationflags=base | subprocess.CREATE_BREAKAWAY_FROM_JOB)
        except OSError:
            p = subprocess.Popen(cmd, stdout=salida, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, creationflags=base)
    else:
        p = subprocess.Popen(cmd, stdout=salida, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    return p.pid


@servidor.tool()
def trabajo_lanzar(funcion: str, args: dict | None = None) -> dict:
    """Lanza una función LARGA en segundo plano y devuelve su id al instante. Luego: trabajo_estado(id)."""
    if funcion not in api.FUNCIONES:
        raise ToolError(f"función desconocida '{funcion}'. Hay: {', '.join(api.FUNCIONES)}")
    tid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    d = TRABAJOS / tid
    d.mkdir(parents=True)
    (d / "peticion.json").write_text(json.dumps(args or {}, ensure_ascii=False), encoding="utf-8")
    cmd = [sys.executable, str(AQUI / "api.py"), "llamar", funcion,
           "--json-archivo", str(d / "peticion.json"), "--salida", str(d / "resultado.json")]
    pid = _lanzar_desacoplado(cmd, d / "log.txt")
    (d / "estado.json").write_text(json.dumps({"funcion": funcion, "pid": pid, "inicio": time.time()}), encoding="utf-8")
    log.info("trabajo %s: %s pid=%s", tid, funcion, pid)
    return {"id": tid, "funcion": funcion, "consultar": "trabajo_estado(id) cada 20-60 s"}


@servidor.tool()
def trabajo_estado(id: str) -> dict:
    """Estado de un trabajo: corriendo, listo (con el resultado) o error (con el final del log)."""
    d = TRABAJOS / id
    if not (d / "estado.json").exists():
        raise ToolError(f"no existe el trabajo {id}")
    est = json.loads((d / "estado.json").read_text(encoding="utf-8"))
    seg = round(time.time() - est["inicio"], 1)
    if (d / "resultado.json").exists():
        r = json.loads((d / "resultado.json").read_text(encoding="utf-8"))
        if r.get("ok"):
            return {"estado": "listo", "segundos": seg, "resultado": r["resultado"]}
        return {"estado": "error", "segundos": seg, "error": r.get("error")}
    if _vivo(est["pid"]):
        return {"estado": "corriendo", "segundos": seg}
    cola = (d / "log.txt").read_text(encoding="utf-8", errors="replace")[-1500:] if (d / "log.txt").exists() else ""
    return {"estado": "error", "segundos": seg, "error": "el proceso terminó sin resultado", "log": cola}


if __name__ == "__main__":
    log.info("arrancando servidor %s (salidas en %s)", api.NOMBRE, api.SALIDAS)
    servidor.run()  # stdio por omisión
