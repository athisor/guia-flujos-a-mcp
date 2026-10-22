r"""Lógica del relevador: encontrar rastros de scripts que convendría convertir en herramientas. Solo lectura, solo biblioteca estándar.

Tres fuentes, que se complementan:
1. Proyectos (análisis estático): una tarjeta por script (qué hace, si es CLI, qué lee y escribe, si tiene prueba, dónde se cita),
   más skills, agentes, comandos, hooks y servidores MCP declarados. Después, un puntaje y un nivel por candidato.
2. Scratchpads de Claude Code: scripts de sesión que se reescribieron en varias sesiones (mismo nombre o mismo contenido).
   Es la señal más directa de "esto se repite y todavía no es herramienta".
3. Historial de sesiones (~/.claude/projects/**/*.jsonl): qué comandos, scripts, skills y herramientas MCP se usan en
   más sesiones y en más proyectos.

Prototipo: nace del servidor `proyectos` de un repo de MCP real, limpiado de rutas y nombres privados. Es heurístico: dice dónde
mirar, no decide solo. Cada puntaje trae sus razones.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

# --------------------------------------------------------------------------- qué se ignora

SISTEMA = {".git", ".hg", ".svn", "$RECYCLE.BIN", "System Volume Information"}
ENTORNOS = {"node_modules", ".venv", "venv", "env", "site-packages", ".conda", "virtualenv", ".tox", ".nox"}
CACHES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".cache", ".next", ".parcel-cache", ".gradle"}
CONSTRUCCION = {"dist", "build", "out", "target", "_build", "coverage"}
ARCHIVADOS = {"_respaldo", "_archivo", "archive", "_old", "old", "old_scripts", "legacy", "deprecated", "obsoleto", "_trash", "attic"}
WORKTREES = {"worktrees", ".worktrees"}
IGNORAR = SISTEMA | ENTORNOS | CACHES | CONSTRUCCION | WORKTREES

EXT_SCRIPT = {".py": "python", ".ps1": "powershell", ".psm1": "powershell", ".sh": "shell", ".bash": "shell", ".bat": "batch",
              ".cmd": "batch", ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript", ".ts": "typescript"}
EXT_DOC = {".md", ".mdc", ".txt", ".rst"}
UMBRAL_DATOS = 150          # carpeta con más archivos directos que esto y sin scripts = carpeta de datos
MAX_LEER = 400_000          # bytes máximos que se leen de un archivo

GPU_MODS = {"torch", "torchvision", "torchaudio", "tensorflow", "jax", "cupy", "onnxruntime", "diffusers", "transformers", "ultralytics"}
GENERICOS = {"__init__", "__main__", "main", "setup", "conftest", "config", "utils", "util", "helpers", "common", "run", "test", "script",
             "tmp", "temp", "prueba", "probar", "check", "chk", "debug", "dbg", "index", "gen", "build", "ver", "verif", "verify", "inv",
             "scan", "fix", "go", "do", "app", "tool", "check_all", "inspect", "analyze", "analisis", "medir", "mide"}

RE_CITA = re.compile(r"(?<![\w.])([\w\-]+\.(?:py|ps1|psm1|sh|bat|cmd|js|mjs|cjs|ts))\b", re.I)
RE_UNA_VEZ = re.compile(r"(^|[_\-.])(fix\d*|tmp|temp|old|debug|scratch|hotfix|once|oneoff|una_?vez|borrar|viejo|copia|backup|parche)($|[_\-.\d])", re.I)
RE_PRUEBA = re.compile(r"(^test_|_test$|^prueba_|\.test$|\.spec$)", re.I)
RE_ESCRIBE = re.compile(r"\.write_text\(|\.write_bytes\(|open\([^)]*['\"][wa]b?\+?['\"]|\.to_csv\(|json\.dump\(|shutil\.(copy|move)|"
                        r"Set-Content|Out-File|Add-Content|writeFileSync|fs\.writeFile|>\s*[\w$\"']")
RE_BORRA = re.compile(r"os\.remove\(|\.unlink\(|shutil\.rmtree\(|os\.rmdir\(|Remove-Item|\brm\s+-r?f|\bdel\s+/|unlinkSync|rmSync")
RE_RED_ESCRIBE = re.compile(r"\.(post|put|patch|delete)\(|method\s*[=:]\s*['\"](POST|PUT|PATCH|DELETE)|Invoke-RestMethod[^\n]*-Method\s+(Post|Put|Patch|Delete)", re.I)
RE_SQL_ESCRIBE = re.compile(r"\b(INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|DROP\s+TABLE|ALTER\s+TABLE)\b", re.I)
RE_LLM = re.compile(r"api\.openai\.com|anthropic|openrouter|chat/completions|generativelanguage|ollama|lmstudio", re.I)


def _patrones_produccion() -> re.Pattern | None:
    """Rutas o servicios que el usuario considera producción (variable RELEVADOR_PRODUCCION, regex). Sin ella, no se marca nada por nombre."""
    p = os.environ.get("RELEVADOR_PRODUCCION", "").strip()
    return re.compile(p, re.I) if p else None


# --------------------------------------------------------------------------- utilidades

def leer(p: Path, maximo: int = MAX_LEER) -> str:
    try:
        with open(p, "rb") as f:
            b = f.read(maximo)
    except OSError:
        return ""
    for cod in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return b.decode(cod)
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", "replace")


def hash_norm(p: Path) -> str:
    """Hash del contenido con fines de línea y BOM normalizados: el mismo script copiado entre Windows y Unix da el mismo hash."""
    try:
        b = p.read_bytes()
    except OSError:
        return "?"
    b = b.replace(b"\r\n", b"\n").removeprefix(b"\xef\xbb\xbf")
    return hashlib.sha1(b).hexdigest()[:12]


def definiciones(texto: str) -> set[str]:
    """Nombres de funciones, clases y argumentos: sirven para decir si dos scripts distintos son variantes del mismo."""
    return (set(re.findall(r"^\s*(?:def|class|function|async def)\s+(\w+)", texto, re.M))
            | set(re.findall(r"add_argument\(\s*['\"]([^'\"]+)", texto))
            | set(re.findall(r"^\s*\[(?:Parameter[^\]]*)?\]\s*\[?\w*\]?\s*\$(\w+)", texto, re.M)))


def _vocabulario(texto: str) -> set[str]:
    return {w.lower() for w in re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", texto)}


def parecido(a: str, b: str) -> float:
    """0..1: definiciones en común si ambos tienen; si no (scripts cortos), vocabulario del código en común."""
    da, db = definiciones(a), definiciones(b)
    if not (da and db):
        da, db = _vocabulario(a), _vocabulario(b)
    return round(len(da & db) / len(da | db), 2) if da and db else 0.0


def sin_tildes(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


VACIAS = set("""a al ante con de del desde en entre hacia hasta para por sin sobre el la los las lo un una y o que se su sus es
the of to in for on and or with from by is it this that an as at be py js ts ps1 sh""".split())


def fichas(texto: str) -> set[str]:
    """Palabras útiles de un nombre o una descripción, en minúsculas y sin tildes. 'extraer_texto_pdf.py' -> {extraer, texto, pdf}."""
    t = sin_tildes(re.sub(r"([a-z])([A-Z])", r"\1 \2", texto)).lower()
    return {w for w in re.split(r"[^a-z0-9]+", t) if len(w) >= 3 and w not in VACIAS}


def familia(stem: str) -> str:
    """Nombre base de un script para agrupar variantes: 'medir_v2', 'medir2', 'medir_new' y 'medir' son la misma familia."""
    s = stem.lower()
    s = re.sub(r"([_\-.]?(v\d+|new|nuevo|old|viejo|final|bis|copia|copy|tmp|fix))+$", "", s)
    s = re.sub(r"[_\-.]?\d+$", "", s)
    return s or stem.lower()


# --------------------------------------------------------------------------- recorrido de un proyecto

def es_worktree(d: Path) -> bool:
    return (d / ".git").is_file()  # un worktree de git tiene un ARCHIVO .git, no una carpeta


def recorrer(raiz: Path, profundidad: int = 4, incluir_archivados: bool = False, tope_s: float = 30.0) -> dict:
    """Scripts y documentos de un proyecto, con lo que se omitió y por qué."""
    scripts, docs, omitidos = [], [], []
    t0 = time.time()
    pila = [(raiz, 0)]
    while pila:
        d, nivel = pila.pop()
        if time.time() - t0 > tope_s:
            omitidos.append({"ruta": str(d), "motivo": f"tope de {tope_s} s"})
            break
        try:
            entradas = list(os.scandir(d))
        except OSError:
            continue
        archivos = [e for e in entradas if e.is_file(follow_symlinks=False)]
        if d != raiz and len(archivos) > UMBRAL_DATOS and not any(Path(e.name).suffix.lower() in EXT_SCRIPT for e in archivos):
            omitidos.append({"ruta": str(d.relative_to(raiz)), "motivo": f"carpeta de datos ({len(archivos)} archivos, ningún script)"})
            continue
        for e in archivos:
            ext = Path(e.name).suffix.lower()
            if ext in EXT_SCRIPT:
                scripts.append(Path(e.path))
            elif ext in EXT_DOC or e.name.lower() in ("claude.md", "agents.md"):
                docs.append(Path(e.path))
        if nivel >= profundidad:
            continue
        for e in entradas:
            if not e.is_dir(follow_symlinks=False):
                continue
            n, p = e.name, Path(e.path)
            if n in IGNORAR or (n.startswith(".") and n not in (".claude", ".github", ".agents", ".cursor")) or (p / "pyvenv.cfg").exists():
                continue
            if es_worktree(p):
                omitidos.append({"ruta": str(p.relative_to(raiz)), "motivo": "worktree de git (copia de otra rama)"})
                continue
            if (p / ".git").is_dir():
                omitidos.append({"ruta": str(p.relative_to(raiz)), "motivo": "repo anidado: relevarlo como proyecto aparte"})
                continue
            if n.lower() in ARCHIVADOS and not incluir_archivados:
                omitidos.append({"ruta": str(p.relative_to(raiz)), "motivo": "archivado"})
                continue
            pila.append((p, nivel + 1))
    return {"scripts": scripts, "docs": docs, "omitidos": omitidos}


# --------------------------------------------------------------------------- tarjeta de un script

def _doc(texto: str, lenguaje: str) -> str:
    if lenguaje == "python":
        try:
            d = ast.get_docstring(ast.parse(texto))
            if d:
                return d.strip().splitlines()[0][:200]
        except (SyntaxError, ValueError):
            pass
    m = re.search(r"\.SYNOPSIS\s*\n\s*(.+)", texto)
    if m:
        return m.group(1).strip()[:200]
    for linea in texto.splitlines()[:15]:
        l = linea.strip()
        if l.startswith(("#!", "# -*-", "#requires", "'use strict'", '"use strict"')) or not l:
            continue
        if l.startswith(("#", "//", "::", "REM ", "rem ")):
            l = l.lstrip("#/:").removeprefix("REM").removeprefix("rem").strip()
            if len(l) > 8:
                return l[:200]
        break
    return ""


def _cli(texto: str, lenguaje: str) -> tuple[str | None, list[str], list[str]]:
    """(tipo de CLI, argumentos, imports raíz)."""
    args, imports = [], []
    if lenguaje == "python":
        try:
            for n in ast.walk(ast.parse(texto)):
                if isinstance(n, ast.Import):
                    imports += [a.name.split(".")[0] for a in n.names]
                elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
                    imports.append(n.module.split(".")[0])
                elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ("add_argument", "option", "argument"):
                    if n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                        args.append(n.args[0].value)
        except (SyntaxError, ValueError):
            imports = re.findall(r"^\s*(?:from|import)\s+(\w+)", texto, re.M)
            args = re.findall(r"add_argument\(\s*['\"]([^'\"]+)", texto)
        imports = list(dict.fromkeys(imports))
        for lib in ("argparse", "click", "typer", "fire"):
            if lib in imports:
                return lib, args, imports
        return ("sys.argv" if re.search(r"\bsys\.argv\b", texto) else None), args, imports
    if lenguaje == "powershell":
        m = re.search(r"^\s*param\s*\(", texto, re.M | re.I)
        args = re.findall(r"\$(\w+)\s*(?:=|,|\))", texto[m.end():m.end() + 3000]) if m else []
        return ("param()" if m else ("$args" if "$args" in texto else None)), args[:30], []
    if lenguaje in ("javascript", "typescript"):
        imports = re.findall(r"(?:require\(|from\s+)['\"]([@\w][\w\-/]*)", texto)
        for lib in ("commander", "yargs", "minimist", "meow"):
            if any(i.startswith(lib) for i in imports):
                return lib, re.findall(r"\.option\(\s*['\"]([^'\"]+)", texto), imports
        return ("process.argv" if "process.argv" in texto else None), [], imports
    if lenguaje == "shell":
        return ("getopts" if "getopts" in texto else ("$1" if re.search(r"\$\{?[1-9@]", texto) else None)), [], []
    return ("%1" if re.search(r"%[1-9*]", texto) else None), [], []


def tarjeta(p: Path, raiz: Path) -> dict:
    texto = leer(p)
    lenguaje = EXT_SCRIPT[p.suffix.lower()]
    cli, args, imports = _cli(texto, lenguaje)
    escribe = []
    if RE_ESCRIBE.search(texto):
        escribe.append("archivos")
    if RE_BORRA.search(texto):
        escribe.append("borra")
    if RE_RED_ESCRIBE.search(texto):
        escribe.append("red")
    if RE_SQL_ESCRIBE.search(texto):
        escribe.append("sql")
    prod = _patrones_produccion()
    try:
        mtime = p.stat().st_mtime
    except OSError:
        mtime = time.time()
    return {
        "nombre": p.name, "ruta": str(p.relative_to(raiz)), "lenguaje": lenguaje, "lineas": texto.count("\n") + 1,
        "dias": int((time.time() - mtime) / 86400), "doc": _doc(texto, lenguaje), "cli": cli, "argumentos": args[:20],
        "imports": imports[:30], "gpu": sorted(set(imports) & GPU_MODS), "llm": bool(RE_LLM.search(texto)), "escribe": escribe,
        "produccion": bool(prod and prod.search(texto)), "prueba": bool(RE_PRUEBA.search(p.stem)) or "tests" in p.parts or "test" in p.parts,
        "mcp_propio": bool(re.search(r"FastMCP|MCPServer|from mcp(\.server)?\b|@modelcontextprotocol/sdk", texto)),
        "hash": hash_norm(p),
    }


# --------------------------------------------------------------------------- skills, agentes, comandos, hooks, MCP declarados

def _desc_md(p: Path) -> str:
    t = leer(p, 20_000)
    m = re.search(r"^description:\s*(.+)$", t, re.M)
    if m:
        return m.group(1).strip().strip("\"'")[:200]
    for l in t.splitlines():
        if l.strip() and not l.startswith(("---", "#", "name:")):
            return l.strip()[:200]
    return ""


def _mcp_de(d: dict, archivo: str) -> list[dict]:
    srv = d.get("mcpServers") or d.get("servers") or {}
    out = []
    if isinstance(srv, dict):
        for k, v in srv.items():
            cmd = v.get("url") or " ".join([str(v.get("command", ""))] + [str(a) for a in v.get("args") or []]) if isinstance(v, dict) else ""
            out.append({"nombre": k, "archivo": archivo, "comando": str(cmd)[:200]})
    return out


def elementos_agente(raiz: Path) -> dict:
    r: dict = {"skills": [], "agentes": [], "comandos": [], "hooks": [], "mcp_declarados": [], "guias": []}
    for base in (".claude/skills", ".agents/skills", ".cursor/skills", "skills"):
        d = raiz / base
        if d.is_dir():
            for e in d.iterdir():
                if (e / "SKILL.md").exists():
                    n_scripts = sum(1 for x in e.rglob("*") if x.suffix.lower() in EXT_SCRIPT)
                    r["skills"].append({"nombre": e.name, "donde": base, "descripcion": _desc_md(e / "SKILL.md"), "scripts": n_scripts,
                                        "hash": hash_norm(e / "SKILL.md")})
    for base, clave in ((".claude/agents", "agentes"), (".cursor/agents", "agentes"), (".claude/commands", "comandos"), (".cursor/commands", "comandos")):
        d = raiz / base
        if d.is_dir():
            for e in d.glob("*.md"):
                r[clave].append({"nombre": e.stem, "donde": base, "descripcion": _desc_md(e), "hash": hash_norm(e)})
    for f in (".claude/settings.json", ".claude/settings.local.json", ".mcp.json", ".cursor/mcp.json", ".vscode/mcp.json"):
        p = raiz / f
        if not p.exists():
            continue
        try:
            d = json.loads(leer(p, 200_000))
        except ValueError:
            continue
        if isinstance(d, dict):
            if d.get("hooks"):
                r["hooks"].append({"archivo": f, "eventos": list(d["hooks"]) if isinstance(d["hooks"], dict) else ["?"]})
            r["mcp_declarados"] += _mcp_de(d, f)
    r["guias"] = [g for g in ("CLAUDE.md", "AGENTS.md", ".claude/CLAUDE.md", "README.md") if (raiz / g).exists()]
    return r


# --------------------------------------------------------------------------- inventario

def inventariar(raiz: Path, profundidad: int = 4, incluir_archivados: bool = False) -> dict:
    rec = recorrer(raiz, profundidad, incluir_archivados)
    tarjetas = [tarjeta(p, raiz) for p in rec["scripts"][:3000]]
    # Citas: en cuántos documentos se nombra cada script, y si lo nombra una skill, un agente o un comando.
    citas, citas_agente, en_tarjeta = Counter(), Counter(), Counter()
    for d in rec["docs"]:
        nombres = {m.lower() for m in RE_CITA.findall(leer(d, 200_000))}
        rel = str(d.relative_to(raiz)).replace("\\", "/").lower()
        for n in nombres:
            citas[n] += 1
            if rel.startswith((".claude/", ".cursor/", ".agents/", "skills/")) or Path(rel).name in ("claude.md", "agents.md"):
                citas_agente[n] += 1
            if re.search(r"herramientas|tools|procesos|playbook|runbook", Path(rel).stem):
                en_tarjeta[n] += 1
    # Bibliotecas: módulos del proyecto que otros scripts importan.
    stems = {Path(t["nombre"]).stem for t in tarjetas if t["lenguaje"] == "python"}
    importado = Counter(i for t in tarjetas for i in set(t["imports"]) if i in stems)
    probados = {re.sub(r"^(test_|prueba_)|_test$", "", Path(t["nombre"]).stem) for t in tarjetas if t["prueba"]}
    for t in tarjetas:
        n = t["nombre"].lower()
        t["citas"], t["citas_agente"], t["en_tarjeta"] = citas[n], citas_agente[n], en_tarjeta[n]
        t["importado_por"] = importado[Path(t["nombre"]).stem]
        t["con_prueba"] = Path(t["nombre"]).stem in probados
    return {"raiz": str(raiz), "scripts": tarjetas, "documentos": len(rec["docs"]), "elementos": elementos_agente(raiz),
            "omitidos": rec["omitidos"]}


# --------------------------------------------------------------------------- catálogo del repo de MCP

def catalogo(repo_mcp: Path | None) -> list[dict]:
    """Funciones que ya publican los servidores del repo de MCP (leídas con ast, sin arrancarlos): nombre, servidor y docstring."""
    if not repo_mcp or not repo_mcp.is_dir():
        return []
    out = []
    for srv in sorted(p for p in repo_mcp.iterdir() if p.is_dir() and not p.name.startswith((".", "_")) and p.name != "comun"):
        for archivo in ("api.py", "servidor.py"):
            f = srv / archivo
            if not f.exists():
                continue
            try:
                arbol = ast.parse(leer(f))
            except (SyntaxError, ValueError):
                continue
            for n in arbol.body:
                if isinstance(n, ast.FunctionDef) and not n.name.startswith("_") and n.name not in ("main", "trabajo_lanzar", "trabajo_estado"):
                    doc = (ast.get_docstring(n) or "").strip().splitlines()
                    out.append({"servidor": srv.name, "funcion": n.name, "doc": doc[0][:160] if doc else ""})
    return out


def coincidencias(nombre: str, doc: str, cat: list[dict], maximo: int = 2) -> list[dict]:
    """Funciones del catálogo que se parecen a un script: palabras del nombre de la función contenidas en el nombre y la doc del script."""
    f_script = fichas(Path(nombre).stem) | fichas(doc)
    res = []
    for c in cat:
        f_fun = fichas(c["funcion"])
        if not f_fun:
            continue
        comun = f_fun & f_script
        if len(comun) < 2 and f_fun != comun:   # una sola palabra en común ('escena') es casualidad, salvo que sea el nombre entero
            continue
        p = len(comun) / len(f_fun)
        if p >= 0.5:
            res.append({**c, "puntaje": round(p, 2), "nivel": "fuerte" if p >= 0.99 and len(comun) >= 2 else "posible", "palabras": sorted(comun)})
    return sorted(res, key=lambda r: -r["puntaje"])[:maximo]


# --------------------------------------------------------------------------- otros proyectos (copias y variantes)

def indice_otros(raices: list[Path], excluir: Path, profundidad: int = 4) -> tuple[dict, dict]:
    """(nombre de script -> [(proyecto, ruta)], 'skill:x'/'agente:x' -> [proyectos]) de los otros proyectos."""
    nombres: dict[str, list[tuple[str, Path]]] = defaultdict(list)
    elem: dict[str, list[str]] = defaultdict(list)
    for r in raices:
        if not r.is_dir() or r.resolve() == excluir.resolve():
            continue
        for p in recorrer(r, profundidad, tope_s=15)["scripts"]:
            nombres[p.name.lower()].append((r.name, p))
        el = elementos_agente(r)
        for s in el["skills"]:
            elem["skill:" + s["nombre"]].append(r.name)
        for a in el["agentes"]:
            elem["agente:" + a["nombre"]].append(r.name)
    return nombres, elem


def expandir_raices(raices: list[str]) -> list[Path]:
    """Cada raíz es un proyecto o una carpeta que contiene proyectos (se toma cada subcarpeta)."""
    out = []
    for r in raices:
        p = Path(r).expanduser()
        if not p.is_dir():
            continue
        es_proyecto = any((p / m).exists() for m in (".git", "CLAUDE.md", "AGENTS.md", "pyproject.toml", "package.json", ".claude"))
        if es_proyecto:
            out.append(p)
        else:
            out += [d for d in p.iterdir() if d.is_dir() and d.name not in IGNORAR and not d.name.startswith(".")]
    return out


# --------------------------------------------------------------------------- puntaje y nivel

ORDEN_NIVEL = {"mcp": 0, "ya_existe": 1, "herramienta_repo": 2, "ya_publicado": 3, "script_sesion": 4}


def evaluar(raiz: Path, otras_raices: list[str], repo_mcp: Path | None, profundidad: int = 4) -> dict:
    inv = inventariar(raiz, profundidad)
    cat = catalogo(repo_mcp)
    nombres_otros, elem_otros = indice_otros(expandir_raices(otras_raices), raiz) if otras_raices else ({}, {})
    items = []
    for s in inv["scripts"]:
        if s["prueba"] or Path(s["nombre"]).stem.lower() in ("__init__", "conftest", "setup"):
            continue
        pts, raz = 0, []
        cli_firme = s["cli"] in ("argparse", "click", "typer", "fire", "param()", "commander", "yargs", "getopts")
        if cli_firme:
            pts += 3
            raz.append(f"CLI ({s['cli']}) con {len(s['argumentos'])} argumentos" if s["argumentos"] else f"CLI ({s['cli']})")
        elif s["cli"]:
            pts += 1
            raz.append(f"recibe argumentos por {s['cli']}")
        if s["doc"]:
            pts += 1
            raz.append("documentado")
        if s["citas"]:
            pts += min(s["citas"], 4)
            raz.append(f"citado en {s['citas']} documentos")
        if s["citas_agente"]:
            pts += 2
            raz.append(f"lo nombran skills, agentes o el CLAUDE.md ({s['citas_agente']})")
        if s["en_tarjeta"]:
            pts += 2
            raz.append("aparece en una tarjeta de herramientas")
        if s["importado_por"]:
            pts += min(s["importado_por"], 3)
            raz.append(f"biblioteca: la importan {s['importado_por']} scripts")
        otros = []
        texto = None
        for proy, ruta in nombres_otros.get(s["nombre"].lower(), [])[:12]:
            if hash_norm(ruta) == s["hash"]:
                otros.append(f"{proy} (idéntico)")
                continue
            texto = texto if texto is not None else leer(raiz / s["ruta"])
            sim = parecido(texto, leer(ruta))
            if sim >= 0.3:
                otros.append(f"{proy} (variante {sim:.0%})")
        if otros:
            pts += 4
            raz.append(f"también en otros proyectos: {', '.join(otros[:4])}")
        if s["con_prueba"]:
            pts += 1
            raz.append("tiene prueba")
        una_vez = bool(RE_UNA_VEZ.search(Path(s["nombre"]).stem))
        if una_vez:
            pts -= 3
            raz.append("nombre de script de una vez")
        if s["dias"] > 365 and not s["citas"]:
            pts -= 1
            raz.append(f"sin cambios hace {s['dias']} días y sin citas")
        coinc = coincidencias(s["nombre"], s["doc"], cat)
        repetido = bool(otros) or s["citas"] >= 5 or s["citas_agente"] >= 2
        estable = cli_firme or s["importado_por"] >= 2
        if s["mcp_propio"]:
            pts += 6
            raz.append("es un servidor MCP propio, fuera del repo de MCP")
            nivel, accion = "mcp", "llevarlo al repo de MCP (un servidor por carpeta, con su prueba y su fila en el catálogo)"
        elif coinc and coinc[0]["nivel"] == "fuerte" and pts >= 2:
            c = coinc[0]
            nivel, accion = "ya_existe", f"parece hacer lo que {c['servidor']}.{c['funcion']}: usar el MCP; si falta un matiz, extender esa función"
        elif pts >= 8 and repetido and estable and not una_vez:
            nivel = "mcp"
            accion = (f"revisar antes {coinc[0]['servidor']}.{coinc[0]['funcion']}: si hace lo mismo, extenderla; si no, función nueva"
                      if coinc else "envolver en un servidor MCP (o en uno existente del mismo tema)")
        elif pts >= 4 and not una_vez:
            nivel, accion = "herramienta_repo", "dejarla como herramienta del repo (CLI, prueba y documentación); subir a MCP si la usa otro proyecto o se repite en 3 sesiones"
        else:
            nivel, accion = "script_sesion", "no subir"
        avisos = []
        if s["produccion"]:
            avisos.append("toca rutas o servicios de producción (RELEVADOR_PRODUCCION): no publicar en MCP sin preguntar")
        if "red" in s["escribe"]:
            avisos.append("escribe en un servicio externo (POST/PUT/DELETE): no publicar en MCP sin preguntar")
        if "borra" in s["escribe"]:
            avisos.append("borra archivos: si se publica, que simule por defecto y mande a papelera")
        if s["llm"]:
            avisos.append("llama a un modelo por API: gasto; ponerle tope")
        if s["gpu"]:
            avisos.append(f"usa GPU ({', '.join(s['gpu'])}): correrla como subproceso con el entorno de su proyecto")
        items.append({"tipo": "script", "nombre": s["nombre"], "ruta": s["ruta"], "puntos": pts, "nivel": nivel, "accion": accion,
                      "razones": raz, "catalogo": coinc, "avisos": avisos, "doc": s["doc"][:160]})
    el = inv["elementos"]
    for sk in el["skills"]:
        otros = elem_otros.get("skill:" + sk["nombre"], [])
        pts = 2 + (4 if otros else 0) + (2 if sk["scripts"] else 0)
        raz = ["skill"] + ([f"también en: {', '.join(otros[:4])}"] if otros else []) + ([f"trae {sk['scripts']} scripts"] if sk["scripts"] else [])
        if otros and sk["scripts"]:
            nivel, accion = "mcp", "sus scripts, a MCP; la skill queda como guía que llama a las funciones"
        elif otros:
            nivel, accion = "herramienta_repo", "skill repetida entre proyectos: unificar las versiones en una sola fuente (skill global)"
        else:
            nivel, accion = ("herramienta_repo", "skill con scripts: candidata si otro proyecto la necesita") if sk["scripts"] else ("script_sesion", "skill local: es guía, no código")
        items.append({"tipo": "skill", "nombre": sk["nombre"], "ruta": f"{sk['donde']}/{sk['nombre']}", "puntos": pts, "nivel": nivel,
                      "accion": accion, "razones": raz, "catalogo": [], "avisos": [], "doc": sk["descripcion"]})
    for ag in el["agentes"]:
        otros = elem_otros.get("agente:" + ag["nombre"], [])
        items.append({"tipo": "agente", "nombre": ag["nombre"], "ruta": f"{ag['donde']}/{ag['nombre']}.md", "puntos": 1 + (3 if otros else 0),
                      "nivel": "herramienta_repo" if otros else "script_sesion",
                      "accion": "agente repetido entre proyectos: unificar como agente global" if otros else "agente local",
                      "razones": ["agente"] + ([f"también en: {', '.join(otros[:4])}"] if otros else []), "catalogo": [], "avisos": [], "doc": ag["descripcion"]})
    for m in el["mcp_declarados"]:
        if repo_mcp and str(repo_mcp).lower() in m["comando"].lower():
            continue
        items.append({"tipo": "mcp_declarado", "nombre": m["nombre"], "ruta": m["archivo"], "puntos": 5, "nivel": "mcp",
                      "accion": "servidor declarado en el proyecto y fuera del repo de MCP: ¿llevarlo al repo, o registrarlo a nivel de usuario?",
                      "razones": [m["comando"][:120]], "catalogo": [], "avisos": [], "doc": ""})
    items.sort(key=lambda x: (ORDEN_NIVEL[x["nivel"]], -x["puntos"], x["nombre"]))
    return {"inventario": inv, "items": items, "catalogo_funciones": len(cat)}


# --------------------------------------------------------------------------- scratchpads

def carpetas_scratchpad(base: str = "") -> list[Path]:
    """Dónde deja Claude Code los scratchpads: <temporal>/claude/<proyecto>/<sesión>/scratchpad. `base` fuerza otra raíz."""
    if base:
        bases = [Path(base).expanduser()]
    else:
        tmp = Path(tempfile.gettempdir())
        bases = [tmp / "claude", Path("/tmp/claude")] + list(Path("/tmp").glob("claude-*")) if os.name != "nt" else [tmp / "claude"]
    vistas, out = set(), []
    for b in bases:
        if not b.is_dir():
            continue
        candidatas = list(b.glob("*/*/scratchpad")) or [p for p in b.rglob("scratchpad") if p.is_dir()]
        for p in candidatas:
            k = os.path.normcase(str(p.resolve()))
            if k not in vistas:
                vistas.add(k)
                out.append(p)
    return out


MAX_SCRIPT_PAD = 150_000   # un script que escribe un agente es chico; lo más grande suele ser código de terceros copiado o extraído
NIVELES_PAD = 2            # scratchpad/x.py y scratchpad/<sub>/x.py; más abajo suelen ser repos clonados o archivos extraídos


def _scripts_de_pad(pad: Path):
    pila = [(pad, 0)]
    while pila:
        d, nivel = pila.pop()
        try:
            entradas = list(os.scandir(d))
        except OSError:
            continue
        for e in entradas:
            if e.is_file(follow_symlinks=False) and Path(e.name).suffix.lower() in EXT_SCRIPT:
                yield Path(e.path)
            elif e.is_dir(follow_symlinks=False) and nivel + 1 < NIVELES_PAD and e.name not in IGNORAR and not e.name.startswith("."):
                pila.append((Path(e.path), nivel + 1))


def revisar_scratchpads(base: str = "", dias: int = 90, max_items: int = 25, min_sesiones: int = 2) -> dict:
    """Scripts de scratchpad agrupados por familia de nombre y por contenido, con en cuántas sesiones y proyectos aparecen."""
    limite = time.time() - dias * 86400 if dias > 0 else 0
    pads = carpetas_scratchpad(base)
    grupos: dict[str, list[dict]] = defaultdict(list)
    por_hash: dict[str, list[dict]] = defaultdict(list)
    total = 0
    for pad in pads:
        sesion, proyecto = pad.parent.name, pad.parent.parent.name
        for p in _scripts_de_pad(pad):
            try:
                st = p.stat()
            except OSError:
                continue
            if st.st_mtime < limite or st.st_size > MAX_SCRIPT_PAD:
                continue
            mt = st.st_mtime
            total += 1
            f = {"ruta": p, "sesion": sesion, "proyecto": proyecto, "mtime": mt, "hash": hash_norm(p)}
            grupos[familia(p.stem)].append(f)
            por_hash[f["hash"]].append(f)
    filas = []
    for fam, lista in grupos.items():
        sesiones = {f["sesion"] for f in lista}
        if len(sesiones) < min_sesiones:
            continue
        lista.sort(key=lambda f: -f["mtime"])
        reciente = leer(lista[0]["ruta"])
        # En nombres genéricos (test.py, run.py) la coincidencia puede ser casual: se mide cuánto se parecen de verdad.
        otros = [leer(f["ruta"]) for f in lista[1:6] if f["hash"] != lista[0]["hash"]]
        sim = round(sum(parecido(reciente, t) for t in otros) / len(otros), 2) if otros else 1.0
        cli, args, _ = _cli(reciente, EXT_SCRIPT[lista[0]["ruta"].suffix.lower()])
        filas.append({
            "familia": fam, "sesiones": len(sesiones), "proyectos": len({f["proyecto"] for f in lista}), "archivos": len(lista),
            "versiones_distintas": len({f["hash"] for f in lista}), "parecido_medio": sim, "generico": fam in GENERICOS or len(fam) < 3,
            "con_parametros": bool(cli and args) or cli in ("param()",), "doc": _doc(reciente, EXT_SCRIPT[lista[0]["ruta"].suffix.lower()]),
            "mas_reciente": str(lista[0]["ruta"]), "ultima_vez": time.strftime("%Y-%m-%d", time.localtime(lista[0]["mtime"])),
            "proyectos_nombres": sorted({f["proyecto"] for f in lista})[:4],
        })
    # Lo que se reescribió en más sesiones y proyectos primero; lo genérico y poco parecido, al final.
    filas.sort(key=lambda r: (r["parecido_medio"] >= 0.3, not r["generico"], r["proyectos"], r["sesiones"]), reverse=True)
    copiados = []
    for h, lista in por_hash.items():
        if h != "?" and len({f["sesion"] for f in lista}) >= 2 and len({f["ruta"].name for f in lista}) >= 1:
            copiados.append({"nombres": sorted({f["ruta"].name for f in lista})[:4], "sesiones": len({f["sesion"] for f in lista}),
                             "ejemplo": str(lista[0]["ruta"])})
    copiados.sort(key=lambda r: -r["sesiones"])
    return {"scratchpads": len(pads), "scripts": total, "familias_repetidas": len(filas), "repetidos": filas[:max_items],
            "copiados_tal_cual": copiados[:max_items // 2],
            "pista": ("Una familia en >=3 sesiones o >=2 proyectos, con parecido_medio >=0.3, es candidata a herramienta del repo: "
                      "juntar las versiones en una CLI con parámetros. 'generico' = nombre como test.py o run.py: mirar antes de creerle.")}


# --------------------------------------------------------------------------- historial de sesiones

RE_SCRIPT_CMD = re.compile(r"([\w.\-/\\:~]+\.(?:py|ps1|sh|bat|cmd|js|mjs|ts))\b", re.I)


# Comandos que no son candidatos a herramienta por sí mismos (navegar, mirar, mover): no se cuentan.
TRIVIALES = {"cd", "set-location", "ls", "dir", "get-childitem", "gci", "mkdir", "new-item", "cat", "type", "get-content", "echo",
             "write-output", "write-host", "pwd", "head", "tail", "wc", "grep", "rg", "find", "select-string", "cp", "mv", "rm",
             "copy-item", "move-item", "remove-item", "which", "where", "get-command", "sleep", "start-sleep", "test-path", "export",
             "set", "true", "false", "clear", "cls", "git", "sed", "awk", "sort", "uniq", "tr", "cut", "du", "df", "touch", "file"}


def clave_comando(cmd: str) -> str:
    """El script que corre el comando, o sus dos primeras palabras útiles. '' si solo navega o mira."""
    m = RE_SCRIPT_CMD.search(cmd)
    if m:
        ruta = m.group(1)
        return ("scratchpad: " if "scratchpad" in ruta.lower() else "script: ") + re.split(r"[\\/]", ruta)[-1]
    for tramo in re.split(r"\s*(?:\|\||&&|;|\||\n)\s*", cmd.strip()):
        partes = tramo.split()
        if not partes or partes[0].lower() in TRIVIALES or partes[0].startswith(("$", "#")) or "=" in partes[0]:
            continue
        return "cmd: " + " ".join(partes[:2])
    return ""


def _proyecto_y_sesion(f: Path, base: Path) -> tuple[str, str]:
    """Proyecto = la carpeta del historial (sin el sufijo de worktree); sesión = el .jsonl, o la carpeta de sesión si es de un subagente."""
    partes = f.relative_to(base).parts
    proyecto = re.sub(r"--claude-worktrees-.*$", "", partes[0]) if len(partes) > 1 else base.name
    sesion = partes[1] if len(partes) > 2 else f.stem
    return proyecto, sesion


APP_INTERNAS = ("mcp__ccd_", "mcp__Claude_")  # herramientas de la propia app de escritorio, no del usuario


def sesiones_repetidas(carpeta: str = "", dias: int = 60, max_items: int = 25, max_archivos: int = 2000) -> dict:
    base = Path(carpeta).expanduser() if carpeta else Path.home() / ".claude" / "projects"
    if not base.is_dir():
        raise FileNotFoundError(f"no hay historial en {base}")
    limite = time.time() - dias * 86400 if dias > 0 else 0
    archivos = sorted((p for p in base.rglob("*.jsonl") if p.stat().st_mtime >= limite), key=lambda p: -p.stat().st_mtime)
    recortado = len(archivos) > max_archivos
    archivos = archivos[:max_archivos]
    veces: dict[str, Counter] = {k: Counter() for k in ("comandos", "skills", "mcp")}
    ses: dict[str, dict[str, set]] = {k: defaultdict(set) for k in veces}
    proy: dict[str, dict[str, set]] = {k: defaultdict(set) for k in veces}
    for f in archivos:
        proyecto, sesion = _proyecto_y_sesion(f, base)
        try:
            fh = f.open(encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for linea in fh:
                if '"tool_use"' not in linea:
                    continue
                try:
                    d = json.loads(linea)
                except json.JSONDecodeError:
                    continue
                for c in (d.get("message") or {}).get("content") or []:
                    if not isinstance(c, dict) or c.get("type") != "tool_use":
                        continue
                    nombre, entrada = c.get("name", ""), c.get("input") or {}
                    if nombre in ("Bash", "PowerShell") and isinstance(entrada.get("command"), str):
                        tipo, clave = "comandos", clave_comando(entrada["command"])
                    elif nombre == "Skill":
                        tipo, clave = "skills", str(entrada.get("skill", "?"))
                    elif nombre.startswith("mcp__") and not nombre.startswith(APP_INTERNAS):
                        tipo, clave = "mcp", nombre
                    else:
                        continue
                    if clave:
                        veces[tipo][clave] += 1
                        ses[tipo][clave].add(sesion)
                        proy[tipo][clave].add(proyecto)

    def tabla(tipo: str) -> list[dict]:
        filas = [{"que": k, "veces": v, "sesiones": len(ses[tipo][k]), "proyectos": len(proy[tipo][k])} for k, v in veces[tipo].items()]
        filas.sort(key=lambda r: (r["proyectos"], r["sesiones"], r["veces"]), reverse=True)
        return filas[:max_items]

    return {"historial": str(base), "sesiones_leidas": len(archivos), "recortado": recortado,
            "comandos": tabla("comandos"), "skills": tabla("skills"), "mcp": tabla("mcp"),
            "pista": ("'scratchpad: x.py' corrido en varias sesiones = script de sesión que ya se volvió herramienta sin serlo. "
                      "'script: x.py' en varios proyectos = candidato a MCP. Un 'cmd:' largo y repetido = candidato a CLI.")}


if __name__ == "__main__":
    print("Usar api.py (lista / llamar).", file=sys.stderr)
