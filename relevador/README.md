# Servidor MCP `relevador`

Encuentra rastros de scripts que conviene convertir en herramientas. **Todo es de solo lectura.** Es el primer servidor que conviene instalar, porque es el que encuentra a los demás. Está explicado en `GUIA_FLUJOS_A_MCP.md` §5.

Es un prototipo limpio del servidor `proyectos` de un repo de MCP real, sin rutas ni nombres privados, y agrega la búsqueda en los scratchpads y en el historial de sesiones. Usa solo la biblioteca estándar.

## Funciones

| Función | Qué mira | Qué devuelve |
|---|---|---|
| `sesiones_repetidas(carpeta="", dias=60)` | El historial de Claude Code (`~/.claude/projects/**/*.jsonl`) | Los scripts, comandos, skills y herramientas MCP que más se repiten, con en cuántas **sesiones** y cuántos **proyectos** aparecen. Ignora la navegación (`cd`, `ls`, `mkdir`, `git`…) y las herramientas internas de la app. Un `scratchpad: x.py` corrido en varias sesiones es un script de sesión que ya funciona como herramienta sin serlo. |
| `scratchpads_revisar(carpeta="", dias=90, min_sesiones=2)` | Los scratchpads (`<temporal>/claude/<proyecto>/<sesión>/scratchpad`) | Las familias de scripts que se reescribieron en varias sesiones (`medir.py`, `medir_v2.py` y `medir2.py` son la misma familia), con su `parecido_medio` (0 a 1), si el nombre es genérico, si ya acepta parámetros y la ruta de la versión más reciente. También lista los scripts copiados tal cual entre sesiones. |
| `proyecto_candidatos(ruta, otras_raices=[], repo_mcp="")` | Un proyecto, comparado contra otros proyectos y contra el catálogo del repo de MCP | Un ranking con el nivel propuesto (`mcp`, `ya_existe`, `herramienta_repo`, `script_sesion`), los puntos, las razones, las funciones parecidas del catálogo y los **avisos** (escribe en un servicio externo, borra, llama a un modelo pagado, usa GPU). |
| `proyecto_inventariar(ruta)` | Un proyecto | Una tarjeta por script (qué hace, si es CLI y con qué argumentos, qué escribe, en cuántos documentos se cita, si tiene prueba) y sus skills, agentes, comandos, hooks y servidores MCP declarados. Pagina con `desde` y `max_filas`. |

Las cuatro pueden tardar: lánzalas con `trabajo_lanzar(funcion, args)` y consulta `trabajo_estado(id)`. En un equipo con unas 600 sesiones y 2 800 scratchpads, medido: `sesiones_repetidas` de 7 días tarda unos 13 s, `scratchpads_revisar` de 30 días 1 s y `proyecto_candidatos` de un repo mediano 1 s.

## Variables de entorno (opcionales)

| Variable | Para qué |
|---|---|
| `RELEVADOR_REPO_MCP` | Ruta del repo de servidores MCP, para marcar lo que `ya_existe`. |
| `RELEVADOR_PRODUCCION` | Regex con las rutas o los servicios que cuentan como producción (por ejemplo `D:\\produccion|api\\.miempresa\\.com`). Los scripts que los nombran reciben el aviso de no publicar sin preguntar. |
| `MCP_SALIDAS` | Dónde se guarda el estado de los trabajos largos (por omisión, `~/mcp_salidas/relevador/trabajos`). |

## Cómo puntúa

Ver la tabla del §5.1 de la guía. En resumen: suma lo que indica que algo se repite y es estable (CLI con argumentos, citas en la documentación, uso desde skills, copias en otros proyectos, prueba) y resta lo que indica uso de una sola vez (`tmp_`, `fix_`, viejo y sin citas). Para el nivel `mcp` hace falta que se repita **y** que tenga una interfaz estable.

## Instalar, probar y registrar

```powershell
cd <ruta>\relevador; uv sync; $env:PYTHONIOENCODING='utf-8'; uv run prueba_cliente.py
claude mcp add --scope user relevador -e RELEVADOR_REPO_MCP=<repo-mcp> -- "<ruta>\relevador\.venv\Scripts\python.exe" "<ruta>\relevador\servidor.py"
```

```bash
cd <ruta>/relevador && uv sync && uv run prueba_cliente.py
claude mcp add --scope user relevador -e RELEVADOR_REPO_MCP=<repo-mcp> -- <ruta>/relevador/.venv/bin/python <ruta>/relevador/servidor.py
```

La prueba arma dos proyectos de mentira, un repo de MCP falso, tres scratchpads y un historial, llama las cuatro funciones y comprueba que **no cambió ningún archivo**. Tiene que terminar en `TODO OK`.

Sin MCP: `uv run api.py lista` y `uv run api.py llamar scratchpads_revisar --json "{\"dias\": 30}"`.

## Límites

- Es una heurística estática: no ejecuta nada. Dice dónde mirar, no decide sola. Cada puntaje trae sus razones.
- En los scratchpads, dos scripts con el mismo nombre corto (`chk.py`, `dbg.py`) suelen ser cosas distintas. Por eso salen marcados como `generico`, con `parecido_medio` bajo y al final de la lista. Lo que conviene mirar primero es lo que tiene `parecido_medio` ≥ 0,3 en 3 o más sesiones.
- `scratchpads_revisar` mira hasta dos niveles bajo `scratchpad/` y archivos de hasta 150 KB. Más abajo, o más grande, suele haber código de terceros clonado o extraído.
- Las coincidencias con el catálogo exigen al menos dos palabras en común con el nombre de la función. Se escapan los parecidos con otro vocabulario: la lista es una ayuda, no un reemplazo de leer el catálogo.
- El formato del historial y la carpeta de los scratchpads no son una API pública de Claude Code y pueden cambiar. Si las tablas salen vacías con datos que sí existen, mira una línea del `.jsonl` o busca dónde quedan las carpetas `scratchpad`, y pasa `carpeta`.
