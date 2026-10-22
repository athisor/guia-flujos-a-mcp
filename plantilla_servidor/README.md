# Servidor MCP `plantilla`

Plantilla mínima y probada para crear un servidor MCP en Python. Está explicada en `GUIA_FLUJOS_A_MCP.md` §6. Para crear uno nuevo, se copia la carpeta, se renombra y se cambian las funciones de `api.py`.

## Funciones

| Función | Larga | Escribe | Qué hace |
|---|---|---|---|
| `carpeta_resumen(ruta, max_items=15)` | no | no | Archivos por extensión, tamaño total y los más grandes. |
| `sesiones_repetidas(carpeta="", dias=60, max_items=25, max_archivos=2000)` | **sí** | no | Lee el historial de Claude Code (`~/.claude/projects/**/*.jsonl`) y cuenta los comandos, skills y herramientas MCP que más se repiten, con en cuántas sesiones y proyectos aparecen. Es la semilla del «relevador». |
| `nota_escribir(nombre, texto, confirmar=false)` | no | **sí**, solo en su carpeta de salidas | Ejemplo del patrón de escritura segura: simula por defecto, nunca pisa archivos, nunca escribe fuera de `MCP_SALIDAS`. |
| `trabajo_lanzar(funcion, args)` / `trabajo_estado(id)` | — | en `MCP_SALIDAS/plantilla/trabajos/` | Corre lo largo en un proceso aparte y devuelve un id al instante. |

Las salidas van a `MCP_SALIDAS/plantilla/`. Si no se define la variable, van a `~/mcp_salidas/plantilla/`.

## Archivos

| Archivo | Para qué |
|---|---|
| `api.py` | **Toda la lógica.** Funciones con tipos y docstring, más una CLI (`lista`, `llamar`). Usa solo la biblioteca estándar. |
| `servidor.py` | Publica las funciones de `api.py` como herramientas MCP y agrega `trabajo_*`. No tiene lógica propia. |
| `prueba_cliente.py` | Prueba de punta a punta: arranca el servidor como lo hace Claude Code y llama cada función. |
| `pyproject.toml` / `uv.lock` | El entorno, que se crea con `uv sync`. |

## Instalar y probar

Windows (PowerShell):

```powershell
cd <ruta>\plantilla_servidor
uv sync
$env:PYTHONIOENCODING='utf-8'; uv run prueba_cliente.py
```

macOS / Linux:

```bash
cd <ruta>/plantilla_servidor
uv sync
uv run prueba_cliente.py
```

Tiene que terminar en `TODO OK`.

## Usar sin MCP (por consola)

```powershell
uv run api.py lista
uv run api.py llamar carpeta_resumen --json-archivo args.json
```

## Registrar en Claude Code (para todos los proyectos)

Windows:

```powershell
claude mcp add --scope user plantilla -- "<ruta>\plantilla_servidor\.venv\Scripts\python.exe" "<ruta>\plantilla_servidor\servidor.py"
```

macOS / Linux:

```bash
claude mcp add --scope user plantilla -- <ruta>/plantilla_servidor/.venv/bin/python <ruta>/plantilla_servidor/servidor.py
```

Para verificarlo, `claude mcp list` debe mostrar `plantilla ... ✓ Connected`. Después se abre una sesión nueva, o se usa `/mcp` en una abierta.

## Límites

- `sesiones_repetidas` es una heurística: agrupa los comandos por el script que corren o por sus dos primeras palabras. Sirve para saber dónde mirar, no para decidir sola.
- El formato del historial de Claude Code no es una API pública y puede cambiar. Si cambia, la función devuelve tablas vacías, no datos falsos.
