# De scripts sueltos a herramientas MCP

Una metodología para trabajar con Claude Code: detectar lo que se repite, subirlo de **script de sesión** a **herramienta del repo** (CLI con parámetros, prueba y documentación) y de ahí a **servidor MCP**, y dejar escrito el criterio para que cada agente nuevo lo siga.

La idea de fondo: gastar tokens para crear lo que no existe y usar lo que ya existe para no volver a gastarlos. Un agente que conversa con un MCP recibe funciones con tipos y descripciones, no lee scripts. Así gasta menos y obtiene resultados más predecibles.

## Qué hay aquí

| Carpeta o archivo | Qué es |
|---|---|
| [`GUIA_FLUJOS_A_MCP.md`](GUIA_FLUJOS_A_MCP.md) | **El documento principal.** Instrucción de arranque para un agente de Claude Code recién instalado: el prompt para pegar, las fases con su criterio de «listo», las decisiones de diseño y su porqué, plantillas de `CLAUDE.md` y el checklist de seguridad. |
| [`plantilla_servidor/`](plantilla_servidor/) | Molde mínimo de un servidor MCP en Python (FastMCP/MCPServer + `uv`): lógica en `api.py`, `servidor.py` genérico, trabajos largos con id, escritura que simula por defecto. Con su prueba de punta a punta. |
| [`relevador/`](relevador/) | El primer servidor útil: busca en las carpetas de los proyectos, en el historial de sesiones de Claude Code y en los scratchpads los rastros de scripts que conviene convertir en herramientas. Solo lectura y con su prueba. |

## Cómo se usa

1. Clona el repo o copia la carpeta en tu equipo.
2. Abre Claude Code en esa carpeta.
3. Pega el prompt del §1 de [`GUIA_FLUJOS_A_MCP.md`](GUIA_FLUJOS_A_MCP.md).

El agente releva tus proyectos, propone qué convertir y en qué nivel, y construye solo lo que tú apruebes.

Requisitos: [Claude Code](https://claude.com/claude-code), git y [uv](https://docs.astral.sh/uv/). Python lo instala `uv`. Funciona en Windows, macOS y Linux.

## Probar los servidores

```bash
cd plantilla_servidor && uv sync && uv run prueba_cliente.py
cd ../relevador && uv sync && uv run prueba_cliente.py
```

Los dos deben terminar en `TODO OK`.
