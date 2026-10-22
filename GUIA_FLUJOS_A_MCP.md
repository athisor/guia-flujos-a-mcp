# De scripts sueltos a herramientas: guía de arranque para tu agente de Claude Code

> **Para la persona:** pásale este archivo a tu agente de Claude Code. Copia la carpeta entera a tu equipo, abre Claude Code en esa carpeta y pega el prompt del §1. La carpeta trae `GUIA_FLUJOS_A_MCP.md`, `plantilla_servidor/` (el molde de un servidor) y `relevador/` (el primer servidor útil, el que encuentra qué convertir en herramienta); los dos están probados. El agente hace el resto, pero **te pregunta antes de construir, instalar o escribir fuera de su carpeta**. Tú decides qué se convierte en herramienta.
>
> **Para el agente:** este documento es tu instrucción de arranque. Es autocontenido: no supone nada de tu usuario, y todo lo que hay que saber del método está aquí. Las rutas de ejemplo (`<repo-mcp>`, `<proyecto>`) se las preguntas al usuario o las propones tú. No las inventes en silencio.

---

## Índice

1. [Prompt de arranque](#1-prompt-de-arranque)
2. [La idea en una página](#2-la-idea-en-una-página)
3. [Por qué lo hacemos así: las decisiones de diseño](#3-por-qué-lo-hacemos-así-las-decisiones-de-diseño)
4. [Las fases, con su criterio de «listo»](#4-las-fases-con-su-criterio-de-listo)
5. [El relevador: cómo detectar qué conviene convertir](#5-el-relevador-cómo-detectar-qué-conviene-convertir)
6. [Plantilla de servidor MCP (Python + FastMCP + uv)](#6-plantilla-de-servidor-mcp-python--fastmcp--uv)
7. [Registrar el servidor y verificarlo](#7-registrar-el-servidor-y-verificarlo)
8. [El repo de servidores MCP](#8-el-repo-de-servidores-mcp)
9. [Plantillas de CLAUDE.md](#9-plantillas-de-claudemd)
10. [Checklist de seguridad](#10-checklist-de-seguridad)
11. [Cerrar lo que se abre](#11-cerrar-lo-que-se-abre)
12. [Opcional: repartir la carga con otro proveedor](#12-opcional-repartir-la-carga-con-otro-proveedor)
13. [Dónde guarda Claude Code cada cosa](#13-dónde-guarda-claude-code-cada-cosa)

---

## 1. Prompt de arranque

Pégalo tal cual en una sesión nueva de Claude Code, abierta en la carpeta donde está esta guía:

```text
Lee GUIA_FLUJOS_A_MCP.md entera antes de hacer nada. Es tu instrucción de arranque y vale para ti y para cada subagente que lances.

Quiero que sigas sus fases en orden:
0. Preparación: revisa qué tengo instalado (git, uv, Python, el CLI `claude`) y dime qué falta. No instales nada sin preguntarme.
1. Relevamiento: haz el inventario de mis proyectos, scripts, skills, comandos, agentes, hooks y servidores MCP, y revisa el historial
   de sesiones de ~/.claude/projects y los scratchpads, si existen. Usa el relevador que viene en la carpeta relevador/ (por consola
   o, con mi sí, registrado como MCP). Pregúntame primero en qué carpetas están mis proyectos. Solo lectura.
2. Propuesta: dame la tabla de candidatos con el nivel que propones para cada uno (script de sesión, herramienta del repo o servidor MCP)
   y por qué. No construyas nada hasta que yo diga que sí, candidato por candidato.
3. Construcción: crea el repo de servidores MCP y los primeros servidores que yo apruebe, con su entorno uv, sus pruebas, el catálogo
   y el registro en Claude Code. Déjalo funcionando y verificado: cada servidor debe aparecer como conectado.
4. Visión: propónme el CLAUDE.md global y el de cada proyecto con el criterio de consolidar. Muéstrame el texto antes de escribirlo.

Reglas que no se negocian:
- Pregúntame antes de instalar, de escribir fuera de la carpeta de trabajo, de registrar servidores y de tocar cualquier cosa
  que escriba en producción o en un servicio externo.
- Nada de secretos en archivos versionados.
- Al terminar cada fase, dime en pocas líneas qué hiciste, cómo lo verificaste y qué queda pendiente.
- Mis comandos me los das para mi sistema operativo y mi consola. Averigua cuáles son antes.
```

---

## 2. La idea en una página

Con hachas y fuego se hace una forja. Con la forja se hacen herramientas simples, con esas, herramientas complejas, y con estas se puede hacer casi cualquier cosa. Así se trabaja con un agente: **gastar tokens en crear lo que no existe y usar lo que ya existe para no volver a gastarlos.**

Una herramienta sube al nivel siguiente solo cuando el anterior ya no alcanza:

| Nivel | Qué es | Cuándo |
|---|---|---|
| **1. Script de sesión** | Un script que resuelve la tarea de hoy. Vive en el scratchpad o en una carpeta de borradores. | Siempre se empieza aquí. Muchos se quedan aquí, y está bien. |
| **2. Herramienta del repo** | Una CLI con parámetros (argparse, sin rutas fijas en el código), con prueba y documentación, dentro del proyecto al que pertenece. | El tipo de script se repite: lo reescribiste o lo copiaste más de una vez. |
| **3. Servidor MCP** | Un servidor que **envuelve** la herramienta del repo y publica sus funciones con tipos y descripción. **No la reemplaza ni la saca de su proyecto.** | La usan al menos 2 proyectos, o se repitió en 3 sesiones, y su interfaz ya es estable. |

Lo que pide este método:

- **Antes de escribir un script, buscar si ya hay una herramienta:** el catálogo de MCP, las CLI del proyecto, las skills.
- **Si no existe y el tipo de tarea se repite, sugerir la herramienta al usuario.** No construirla en silencio.
- **Si existe, usarla.** No leer su código salvo que su documentación no alcance.
- **Cuanto más se repite una tarea, más se justifica consolidarla.** Una tarea puntual no lo amerita. Un script de una sola vez, por ejemplo reconstruir una historia puntual, no califica.
- **Cada subagente informa** qué herramientas usó y cuáles le faltaron. Esa lista es la que alimenta la próxima consolidación.

---

## 3. Por qué lo hacemos así: las decisiones de diseño

Estas decisiones no son de gusto. Cada una responde a un costo que se midió o a un error que ya pasó.

### 3.1 El agente conversa con el MCP: recibe funciones y descripciones, no lee scripts

Cuando el agente tiene que usar un script suelto, primero lo lee entero para saber qué argumentos acepta, qué devuelve y qué rutas espera. Esa lectura cuesta tokens y se repite en cada sesión.

Con un servidor MCP, el agente recibe solo **el nombre de cada función, una descripción corta y el esquema de sus parámetros con tipos**. Llama `carpeta_resumen(ruta="...")` como llamaría a cualquier herramienta propia, sin armar comandos de consola, sin escapar comillas y sin abrir el código.

Además, Claude Code carga las herramientas de forma diferida. Los nombres y las instrucciones del servidor van siempre al contexto, pero la descripción y el esquema de cada función entran solo cuando el agente la va a usar. Por eso:

- **Cada función publicada cuesta contexto.** No se publica lo que no hace falta. Por ejemplo, `trabajo_lanzar` y `trabajo_estado` se publican solo si el servidor tiene alguna función larga.
- **Las descripciones son telegráficas.** La primera línea dice qué hace la función, sin relleno.
- **Las instrucciones del servidor son las reglas que costaron:** qué llamar primero, qué es LARGO, qué pide confirmación.

### 3.2 Parametrizar los scripts ahorra tokens

Un script con rutas, nombres o umbrales escritos en el código sirve una sola vez. La vez siguiente, el agente lo lee, lo copia, cambia tres líneas y lo vuelve a correr, y cada una de esas vueltas cuesta tokens.

Un script con parámetros (`--entrada`, `--salida`, `--umbral`), sin rutas fijas en el código, se **llama**. No hace falta reescribirlo. Es la diferencia entre gastar tokens una vez y gastarlos cada vez.

Regla práctica: si vas a escribir un script nuevo y uno viejo se le parece, **un script nuevo parametrizable vale más que reciclar uno viejo de confiabilidad desconocida**. Después se reemplaza el viejo.

### 3.3 Parametrizar y usar herramientas da resultados predecibles

Un agente que reescribe un script cada vez produce una variante distinta cada vez: otro redondeo, otro filtro, otro caso borde olvidado. Dos sesiones que hacen «lo mismo» llegan a números distintos, y nadie sabe cuál está bien.

Una herramienta con parámetros, **probada y con una sola implementación**, da el mismo resultado con los mismos parámetros. Si tiene un error, se arregla una vez y queda arreglado para todos. Si se le escriben pruebas de regresión, ni siquiera vuelve a romperse.

### 3.4 Medir antes de razonar

El cómputo local (un script de Python, un render, una consulta) cuesta casi cero. El razonamiento de un modelo iterando sin datos es caro, y además puede converger a algo plausible y falso.

Ante una incógnita, la primera pregunta es: **¿qué script de una pasada la respondería?** Se escribe, se corre y se razona sobre el resultado. Si esa pregunta vuelve a aparecer, ese script es candidato a herramienta.

### 3.5 Una sola fuente para la lógica

Toda la lógica vive en **un** módulo (`api.py`), como funciones normales con tipos y docstring. De ahí salen la CLI, el servidor MCP (que publica esas mismas funciones) y la documentación de uso.

No se duplica ni el esquema ni la lógica. Si mañana se quiere una API HTTP, sale del mismo lugar. Lo que hay en dos lugares termina distinto en los dos.

### 3.6 El MCP envuelve la herramienta, no la reemplaza

La herramienta sigue viviendo en el proyecto al que pertenece, con sus pruebas, sus guardas y su flujo de ramas y PR. El servidor MCP es una capa delgada encima.

Así el proyecto sigue funcionando sin MCP, el servidor no inventa reglas que el proyecto no tiene, y quien mantiene el código sigue siendo el proyecto dueño.

### 3.7 Respuestas cortas

Lo que devuelve una función lo lee el agente, y eso cuesta tokens:

- Se devuelven **rutas y cifras en JSON**, nunca contenidos enteros.
- Si algo no cabe, se recorta y se devuelve también `completo` con la ruta del archivo que tiene el texto entero.
- Las imágenes van reducidas (por ejemplo a 1024 px), con un parámetro `ver=false` para no adjuntarlas.
- Las listas se paginan o se recortan (`max_items`), pero **los totales siempre vienen completos**, para que el agente sepa que hay más.

### 3.8 Lo largo no bloquea: trabajos con id

Lo que tarda minutos (renders, transcripciones, modelos locales, recorrer un disco) no puede dejar al agente esperando. `trabajo_lanzar(funcion, args)` devuelve un id al instante, y `trabajo_estado(id)` se consulta cada 20 a 60 segundos.

El trabajo corre en un proceso aparte que sobrevive si se cierra la sesión. Su petición, su estado y su resultado quedan en disco.

### 3.9 Nombres `objeto_acción`, sin alias

Los nombres se forman con el objeto primero y la acción después: `pdf_texto`, `audio_transcribir`, `rig_ficha`, `trabajo_estado`. Así se agrupan solos y se adivinan.

Cuando una función cambia de nombre, el nombre viejo **se quita**. No se deja un alias que ensucie el catálogo. En su lugar, se guarda una tabla `viejo -> nuevo`, y quien llame al nombre viejo recibe un error que dice a dónde se migró y con qué parámetros.

### 3.10 Entornos livianos y aislados

Cada servidor tiene su propio entorno (`uv`), con lo mínimo: el SDK de MCP y poco más. Si una función necesita algo pesado (torch, OpenCV, un programa de escritorio), el servidor la corre **como subproceso** con el Python del proyecto dueño y recibe JSON. No se mezclan entornos ni se instala lo pesado dos veces.

### 3.11 Lo que escribe, simula primero

Una función que escribe:

- **simula por defecto** y devuelve el plan de lo que haría;
- escribe solo con `confirmar=true`, y ese valor se pasa **solo con un sí explícito del usuario en el chat**;
- nunca pisa un archivo existente sin respaldo;
- nunca escribe fuera de su carpeta de salidas.

Las salidas de cada servidor van a una carpeta propia (`<salidas>/<servidor>/`), nunca junto a los originales.

### 3.12 Errores claros, no trazas

Un error de uso, como una ruta que no existe o un parámetro inválido, se devuelve como **mensaje claro para el agente** («no es una carpeta: …»). Así el agente corrige la llamada sin abrir el código. La traza completa queda en el log del servidor, en stderr. Nada va a stdout salvo el protocolo MCP: si un `print` se cuela, el servidor deja de funcionar.

---

## 4. Las fases, con su criterio de «listo»

Para el agente: no te saltes fases. Al final de cada una, dile al usuario en pocas líneas qué hiciste, cómo lo verificaste y qué queda pendiente.

### Fase 0. Preparación

1. Averigua el sistema operativo y la consola del usuario. En Windows, `$PSVersionTable.PSVersion`: **PowerShell 5.1 no acepta `&&` ni `||`**, así que ahí se encadena con `;` o con `; if ($?) { ... }`.
2. Revisa qué está instalado: `git --version`, `uv --version`, `python --version` (o `python3`), `claude --version`.
3. Si falta `uv`, **propón** cómo instalarlo y espera el sí:
   - Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
   - macOS / Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`

   Con `uv`, Python se instala por proyecto (`uv python install 3.12`), así que no hace falta tener un Python del sistema.
4. Si el CLI `claude` no está en el PATH (pasa con algunas instalaciones de la app de escritorio), búscalo y anota su ruta para la fase 3.

**Listo cuando:** sabes el sistema operativo, la consola y las versiones, y el usuario aprobó lo que haya que instalar.

### Fase 1. Relevamiento (solo lectura)

1. **Pregunta** en qué carpetas están los proyectos. No recorras discos enteros por tu cuenta.
2. **Usa el relevador (§5)** antes de leer nada a mano: `uv sync` y `uv run prueba_cliente.py` en `relevador/`, y después `sesiones_repetidas`, `scratchpads_revisar` y `proyecto_candidatos` por consola (`uv run api.py llamar …`). Si el usuario aprueba registrarlo como MCP (§7), mejor aún: es el primer servidor y sirve para probar el registro.
3. Lo que el relevador no cubre, complétalo con un subagente por zona, para no llenar tu contexto. Cada subagente devuelve tablas, no volcados:
   - **Proyectos:** carpeta, lenguaje, si es repo git, si tiene `CLAUDE.md` o `AGENTS.md`, y la última actividad.
   - **Scripts:** ruta, qué hace (de su docstring o del encabezado), si acepta argumentos (argparse, click, `sys.argv`, `param()` en PowerShell), qué lee y escribe, si tiene prueba, y en qué documentos se cita.
   - **Lo del agente:** skills (`.claude/skills/*/SKILL.md`), comandos (`.claude/commands/*.md`), agentes (`.claude/agents/*.md`), hooks (`settings.json`) y servidores MCP ya registrados (`claude mcp list`, `.mcp.json`). Ver §13.
   - **Historial y scratchpads:** ver §5.2 y §5.3.
4. Ignora `.git`, `.venv`, `node_modules`, cachés, worktrees, carpetas de datos (muchos archivos y ningún script) y lo archivado (`_respaldo`, `old`, `deprecated`). El relevador ya lo hace.
5. Escribe el resultado en `INVENTARIO.md`, en la carpeta de trabajo: un resumen arriba y las tablas abajo.

**Listo cuando:** existe `INVENTARIO.md` con todos los proyectos que nombró el usuario, cada script tiene su fila y están las tablas de lo que más se repite en el historial y en los scratchpads (o la nota de que no hay). No se escribió nada fuera de la carpeta de trabajo.

### Fase 2. Propuesta (el usuario decide)

1. Con el inventario, arma la tabla de candidatos usando los criterios del §5.
2. Para cada candidato: **qué es, nivel propuesto, por qué** (cifras: en cuántas sesiones, en cuántos proyectos, cuántas copias) y **qué haría falta** (parametrizar, escribir una prueba, unir dos variantes).
3. Marca los avisos: si **escribe en producción o en un servicio externo**, si usa GPU o un programa de escritorio, si gasta API de pago.
4. Junta en un solo candidato las variantes del mismo script repartidas por varios proyectos. Suele ser lo que más rinde.
5. Presenta la tabla y **espera el sí candidato por candidato**. Recomienda empezar por 2 o 3 servidores, no por 15.

**Listo cuando:** el usuario eligió qué se construye, y en qué nivel.

### Fase 3. Construcción

Para cada candidato aprobado, en este orden:

1. **Herramienta del repo primero.** Si el candidato todavía es un script suelto, conviértelo en CLI dentro de su proyecto: parámetros, docstring, prueba y una línea en la documentación del proyecto. Si el proyecto tiene su propio flujo (ramas, PR, pruebas), se respeta.
2. **Repo de servidores MCP** (solo la primera vez). Ver §8. Pregunta dónde crearlo; por ejemplo `~/mcp` o `C:\mcp`. Inicializa git. Si el usuario quiere un remoto privado, que lo cree él o que te dé la URL.
3. **El servidor:** copia `plantilla_servidor/` a `<repo-mcp>/<nombre>/`, cambia `NOMBRE`, reemplaza las funciones de ejemplo por llamadas a la herramienta del repo (importándola, o como subproceso si tiene su propio entorno) y ajusta `prueba_cliente.py`.
4. **Entorno:** `uv sync` dentro de la carpeta del servidor.
5. **Prueba de punta a punta:** `uv run prueba_cliente.py` tiene que terminar en `TODO OK`.
6. **Catálogo:** una fila en `CATALOGO.md`.
7. **Registro** (con el sí del usuario): ver §7.
8. **Verificación:** `claude mcp list` muestra el servidor como `✓ Connected`. En una sesión nueva, llama una función de verdad y muéstrale el resultado al usuario.
9. **Commit** en una rama, y PR o merge según lo que el usuario prefiera (§8).

**Listo cuando:** cada servidor aprobado pasa su prueba, aparece conectado en `claude mcp list`, responde a una llamada real desde una sesión nueva y tiene su fila en el catálogo.

**Limpiar el proyecto de origen se pregunta.** El MCP envuelve el código, no lo mueve. No retires, muevas ni borres código, datos ni dependencias del proyecto de origen sin mostrarle antes la lista al usuario y recibir su sí.

### Fase 4. Instalar la visión

1. Propón el `CLAUDE.md` global (§9.1) adaptado a lo que aprendiste del usuario: su sistema operativo, su consola, dónde está su repo de MCP y qué servidores tiene. **Muestra el texto y espera el sí** antes de escribir `~/.claude/CLAUDE.md`. Si ya existe uno, propón agregar una sección, no reemplazarlo.
2. Para cada proyecto con herramientas, propón la sección de proyecto (§9.2): qué CLI tiene, qué servidores MCP usa y qué no se toca.
3. Crea el `AGENTS.md` del repo de MCP (§8.3).

**Listo cuando:** el `CLAUDE.md` global tiene el criterio de consolidar, cada proyecto con herramientas tiene su sección, y una sesión nueva, ante una tarea que ya tiene herramienta, la usa sin que nadie se lo recuerde.

### Fase 5. Mantener (continuo)

- **Al cerrar un trabajo:** revisa los scripts del scratchpad. El scratchpad se pierde al cerrar la sesión, así que si un script de ahí se usó más de una vez o sirve para repetir la tarea, dile al usuario cuáles son y propón dónde guardarlos.
- **Cada tanto** (por ejemplo una vez al mes, o cuando el usuario lo pida): vuelve a correr el relevador (§5) y compara con la vez anterior. ¿Qué nuevo se repite? ¿Qué servidor nadie usa?
- **Los informes de los subagentes** («usé X; me faltó una herramienta para Y») se juntan: si la misma falta aparece varias veces, es un candidato.
- **Si una herramienta existe y la usan 2 proyectos, o ya se repitió en 3 sesiones, con interfaz estable,** sugiere convertirla en MCP.

---

## 5. El relevador: cómo detectar qué conviene convertir

Conviene que **el relevador sea el primer servidor MCP**, porque es justo la herramienta que encuentra a los demás. Viene hecho y probado en la carpeta `relevador/` (ver su `README.md`). Es un prototipo limpio de uno que se usa en un repo de MCP real. Todo es de solo lectura y usa solo la biblioteca estándar de Python.

Tiene tres fuentes, que se complementan:

| Función | Fuente | Qué rastro busca |
|---|---|---|
| `proyecto_inventariar`, `proyecto_candidatos` | Las carpetas de los proyectos | Scripts con CLI, citados en la documentación, copiados entre proyectos; skills repetidas; servidores MCP sueltos (§5.1) |
| `sesiones_repetidas` | El historial de sesiones de Claude Code | Scripts, comandos, skills y herramientas MCP que se usan en muchas sesiones y proyectos (§5.2) |
| `scratchpads_revisar` | Los scratchpads de las sesiones | Scripts de sesión que se reescribieron una y otra vez, con otro nombre o con el mismo (§5.3) |

Ninguna decide sola. Cada fila trae sus cifras y razones para que el usuario elija.

### 5.1 Inventario estático de un proyecto (`proyecto_inventariar`, `proyecto_candidatos`)

Recorre un proyecto sin ejecutar nada y arma una **tarjeta por script**: uso (docstring), si es CLI y con qué argumentos, sus dependencias (y si necesita GPU), qué lee y qué escribe, si tiene prueba y en qué documentos se cita. También lista skills, agentes, comandos, hooks y servidores MCP propios.

Después puntúa cada elemento. Es una heurística: cada punto trae su razón, para que el usuario vea por qué.

| Señal | Puntos |
|---|---|
| CLI con argumentos (argparse, click, typer, `param()` de PowerShell) | +3 (solo `sys.argv`: +1) |
| Tiene docstring o encabezado que explica qué hace | +1 |
| Citado en N documentos del proyecto | +min(N, 4) |
| Citado por skills o agentes | +2 |
| Aparece en una tarjeta de herramientas del proyecto | +2 |
| Biblioteca importada por N scripts | +min(N, 3) |
| Mismo nombre (o mismo hash) en otros proyectos | +4 |
| Tiene prueba | +1 |
| Nombre de una sola vez (`fix_`, `tmp_`, `prueba_`, `old_`) | −3 |
| Viejo y sin citas | −1 |
| Skill | +2 (+4 si está en otros proyectos, +2 si trae scripts) |
| Agente | +1 (+3 si está en otros proyectos) |
| Servidor MCP propio fuera del repo de MCP | +6 |

Con eso asigna un nivel:

| Nivel | Significa | Acción |
|---|---|---|
| `mcp` | Se repite (citado en ≥5 documentos, o por ≥2 skills o agentes, o el mismo script está en otro proyecto) **y** tiene interfaz estable | Subir a MCP. Si ya hay una función parecida, extender ese servidor. |
| `ya_existe` | Una función del catálogo ya hace lo mismo | Usar el MCP. Si le falta un matiz, extenderlo. |
| `herramienta_repo` | CLI útil de un solo proyecto | Dejarla como herramienta del repo, con su tarjeta y su prueba. |
| `ya_publicado` | Un servidor ya la envuelve | Nada. |
| `script_sesion` | De una vez, sin CLI ni citas | No subir. |

Para marcar `ya_existe`, compara contra el catálogo real: lee los nombres y descripciones de las funciones que ya publican los servidores. **No arranques los servidores para eso:** basta con leer su `api.py`.

Cada fila trae además sus **avisos**: escribe en producción o en un servicio externo (no se publica sin preguntar), usa GPU, gasta una API de pago.

### 5.2 Historial de sesiones (`sesiones_repetidas`)

Claude Code guarda cada sesión en `~/.claude/projects/<carpeta-del-proyecto>/<id-de-sesión>.jsonl`. Es un JSON por línea, y las llamadas a herramientas aparecen como bloques `"type": "tool_use"` dentro de `message.content`, con `name` e `input`. En esas líneas se ve:

- **comandos de consola** (`name` = `Bash` o `PowerShell`, `input.command`);
- **skills** usadas (`name` = `Skill`, `input.skill`);
- **herramientas MCP** usadas (`name` empieza con `mcp__`);
- **el proyecto** (`cwd`).

`sesiones_repetidas` agrupa los comandos por el script que corren (o por sus dos primeras palabras útiles) y cuenta cuántas veces aparece cada uno, **en cuántas sesiones y en cuántos proyectos**. Lo que aparece en muchas sesiones o en varios proyectos pesa más que lo que se llamó mil veces en una sola.

- Ignora la navegación y la lectura (`cd`, `ls`, `mkdir`, `cat`, `git`…): no son candidatos.
- Cuenta los worktrees como su proyecto, no como proyectos aparte.
- Cuenta los subagentes dentro de la sesión que los lanzó.

Cómo leer la tabla:

- `scratchpad: x.py` en varias sesiones: un script de sesión que ya se usa como herramienta sin serlo.
- `script: x.py` en varios proyectos: candidato a MCP.
- `cmd: python -c` muy repetido: código que se escribe en línea una y otra vez. Hay que mirar qué hace.
- Un `cmd:` largo que se repite: candidato a CLI.

Ojo: el formato del historial no es una API pública y puede cambiar. Si las tablas salen vacías con un historial que sí existe, mira una línea del `.jsonl` y ajusta la lectura. No concluyas que «no se repite nada».

### 5.3 Scratchpads (`scratchpads_revisar`)

Claude Code le da a cada sesión una carpeta de borradores: `<temporal>/claude/<proyecto>/<sesión>/scratchpad`. En Windows, `<temporal>` es `%TEMP%`. Ahí quedan los scripts de sesión. **Si el mismo script se reescribe en varias sesiones, es la señal más directa de que esa tarea se repite y todavía no tiene herramienta.** Además, el scratchpad se borra o se pierde, y con él el trabajo.

`scratchpads_revisar`:

- agrupa los scripts por **familia de nombre** (`medir.py`, `medir_v2.py` y `medir2.py` son una familia) y por **contenido idéntico**, aunque cambie el nombre;
- para cada familia da en cuántas sesiones y proyectos aparece, cuántas versiones distintas hay, si ya acepta parámetros y la ruta de la versión más reciente;
- mide el `parecido_medio` entre las versiones (funciones y argumentos en común o, en los scripts cortos, vocabulario del código), porque dos `chk.py` de sesiones distintas suelen ser cosas distintas. Los nombres genéricos salen marcados y al final;
- mira hasta dos niveles bajo `scratchpad/` y archivos de hasta 150 KB. Más abajo o más grande suele ser código de terceros clonado o extraído, que no cuenta.

Medido en un equipo real: 2 800 scratchpads se revisan en un segundo. Una familia con `parecido_medio` ≥ 0,3 en 3 o más sesiones es candidata a **herramienta del repo**: juntar las versiones en una CLI con parámetros, en el proyecto al que pertenece.

### 5.4 Otras señales que sí valen

- El mismo bloque de código pegado en varios scripts: es una biblioteca que todavía no existe.
- Skills o agentes con el mismo nombre en varios proyectos, idénticos o con deriva: hay que unificarlos.
- Un comando largo que el usuario pega a mano una y otra vez.
- Un subagente que dice «no había herramienta para X», más de una vez.

---

## 6. Plantilla de servidor MCP (Python + FastMCP + uv)

La carpeta `plantilla_servidor/` que acompaña a esta guía está **probada de punta a punta**: arranca por stdio como lo hace Claude Code y sus 10 pasos de prueba pasan. `relevador/` está hecho con el mismo molde: su `servidor.py` es **idéntico, byte a byte**, y solo cambian `api.py` y la lógica. Ese es el punto: crear un servidor nuevo es escribir funciones, no infraestructura. Si solo tienes este documento, abajo está lo esencial para rehacer la plantilla.

### 6.1 Estructura

```text
<repo-mcp>/<servidor>/
  api.py              # TODA la lógica: funciones con tipos y docstring + CLI (lista, llamar)
  servidor.py         # publica las funciones de api.py como herramientas MCP; sin lógica propia
  prueba_cliente.py   # arranca el servidor por stdio y llama cada función; termina en "TODO OK"
  pyproject.toml      # dependencias (mcp y lo mínimo)
  uv.lock             # lo genera uv; se versiona
  README.md           # funciones, ejemplos, registro, límites
  .gitignore          # .venv/, __pycache__/, logs/, .env*
```

### 6.2 Nota sobre FastMCP

En el SDK oficial de Python (`mcp`), **la versión 2.x renombró `FastMCP` a `MCPServer`**: `from mcp.server.mcpserver import MCPServer`. La 1.x usa `from mcp.server.fastmcp import FastMCP`. La plantilla acepta las dos. También existe un paquete aparte llamado `fastmcp`, con otra API; esta guía no lo usa.

### 6.3 `pyproject.toml`

```toml
[project]
name = "mcp-<servidor>"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["mcp>=1.9"]

[tool.uv]
package = false
```

### 6.4 `api.py` (esqueleto)

```python
"""Funciones del servidor <servidor>. Una sola fuente para la CLI y para el MCP."""
import argparse, json, os, sys
from pathlib import Path

NOMBRE = "<servidor>"
SALIDAS = Path(os.environ.get("MCP_SALIDAS", Path.home() / "mcp_salidas")) / NOMBRE

class ErrorUso(Exception):
    """Error del que llama: se devuelve como mensaje claro, sin traza."""

def carpeta_resumen(ruta: str, max_items: int = 15) -> dict:
    """Resume una carpeta: archivos por extensión y tamaño. Solo lectura."""
    raiz = Path(ruta).expanduser()
    if not raiz.is_dir():
        raise ErrorUso(f"no es una carpeta: {raiz}")
    ...  # devolver cifras y rutas, nunca contenidos

def nota_escribir(nombre: str, texto: str, confirmar: bool = False) -> dict:
    """Escribe una nota en la carpeta de salidas. SIMULA por defecto."""
    destino = SALIDAS / "notas" / f"{nombre}.md"
    if destino.exists():
        raise ErrorUso(f"ya existe {destino}")
    if not confirmar:
        return {"simulado": True, "destino": str(destino)}
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    return {"simulado": False, "destino": str(destino)}

# nombre -> (función, es_larga)
FUNCIONES = {"carpeta_resumen": (carpeta_resumen, False), "nota_escribir": (nota_escribir, False)}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="orden", required=True)
    sub.add_parser("lista")
    ll = sub.add_parser("llamar"); ll.add_argument("funcion")
    ll.add_argument("--json", default="{}"); ll.add_argument("--json-archivo"); ll.add_argument("--salida")
    a = ap.parse_args()
    if a.orden == "lista":
        for n, (f, larga) in FUNCIONES.items():
            print(n, "[LARGA]" if larga else "", (f.__doc__ or "").splitlines()[0])
        sys.exit(0)
    try:
        args = json.loads(Path(a.json_archivo).read_text(encoding="utf-8-sig") if a.json_archivo else a.json)
        resp = {"ok": True, "resultado": FUNCIONES[a.funcion][0](**args)}
    except Exception as e:
        resp = {"ok": False, "error": str(e)}
    txt = json.dumps(resp, ensure_ascii=False)
    if a.salida:
        Path(a.salida).write_text(txt, encoding="utf-8")
    print(txt)
```

### 6.5 `servidor.py` (esqueleto)

```python
"""Servidor MCP <servidor> (stdio). Publica las funciones de api.py. Sin lógica propia."""
import functools, logging, sys
from pathlib import Path

try:                                   # SDK mcp 2.x
    from mcp.server.mcpserver import MCPServer as Servidor
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:                    # SDK mcp 1.x
    from mcp.server.fastmcp import FastMCP as Servidor
    from mcp.server.fastmcp.exceptions import ToolError

sys.path.insert(0, str(Path(__file__).resolve().parent))
import api

logging.basicConfig(stream=sys.stderr, level=logging.INFO)   # NUNCA a stdout: stdout es el protocolo

servidor = Servidor(api.NOMBRE, instructions="Reglas cortas: qué llamar primero, qué es LARGO, qué pide confirmar.")

def publicar(f):
    @functools.wraps(f)                # conserva firma y docstring: de ahí salen el esquema y la descripción
    def envuelta(*a, **k):
        try:
            return f(*a, **k)
        except api.ErrorUso as e:      # el agente recibe el mensaje claro
            raise ToolError(str(e)) from None
    return envuelta

for nombre, (f, _larga) in api.FUNCIONES.items():
    servidor.tool(name=nombre)(publicar(f))

if __name__ == "__main__":
    servidor.run()                     # stdio
```

La versión completa de `plantilla_servidor/servidor.py` agrega `trabajo_lanzar` y `trabajo_estado`. Esas funciones lanzan `python api.py llamar <función> --json-archivo peticion.json --salida resultado.json` como proceso desacoplado de la sesión (en Windows con `DETACHED_PROCESS` y, si se puede, `CREATE_BREAKAWAY_FROM_JOB`; en macOS y Linux con `start_new_session=True`) y dejan `peticion.json`, `estado.json`, `resultado.json` y `log.txt` en `<salidas>/<servidor>/trabajos/<id>/`.

### 6.6 Envolver una herramienta que ya existe

- **Si la herramienta es Python y no trae dependencias pesadas,** `api.py` la importa (por ejemplo, agregando la ruta del proyecto a `sys.path`) y expone sus funciones con parámetros tipados.
- **Si tiene su propio entorno** (torch, OpenCV, etc.), `api.py` la llama como subproceso con **el Python de ese proyecto** y recibe JSON por stdout. El entorno del servidor queda liviano.
- **Si es una CLI de otro lenguaje** (Node, PowerShell, un ejecutable), se hace lo mismo: subproceso, argumentos y JSON de vuelta.
- **Si varios servidores necesitan el mismo cliente** (de una API, de un programa, un lector de PDF), ese cliente va a `<repo-mcp>/comun/` y se importa desde ahí. Un cliente, un lugar.

### 6.7 Instalar y probar

Windows (PowerShell):

```powershell
cd <repo-mcp>\<servidor>; uv sync; $env:PYTHONIOENCODING='utf-8'; uv run prueba_cliente.py
```

macOS / Linux:

```bash
cd <repo-mcp>/<servidor> && uv sync && uv run prueba_cliente.py
```

`prueba_cliente.py` usa el cliente stdio del SDK (`ClientSession` y `stdio_client`), igual que Claude Code. Debe probar:

- que la lista de herramientas es la esperada;
- cada función con un caso normal;
- un error de uso, comprobando que el mensaje llega claro;
- que lo que escribe simula por defecto;
- que no escribe fuera de su carpeta ni pisa archivos;
- un trabajo largo de punta a punta.

Las pruebas escriben solo en una carpeta temporal (por ejemplo apuntando `MCP_SALIDAS` ahí).

---

## 7. Registrar el servidor y verificarlo

### 7.1 Con `claude mcp add` (recomendado)

El ámbito `user` deja el servidor disponible en todos los proyectos, que es lo que se quiere para un repo de servidores compartidos. Se apunta directo al Python del entorno del servidor, porque arranca más rápido que `uv run` y no resincroniza dependencias en cada sesión.

Windows:

```powershell
claude mcp add --scope user <servidor> -- "<repo-mcp>\<servidor>\.venv\Scripts\python.exe" "<repo-mcp>\<servidor>\servidor.py"
```

macOS / Linux:

```bash
claude mcp add --scope user <servidor> -- <repo-mcp>/<servidor>/.venv/bin/python <repo-mcp>/<servidor>/servidor.py
```

- Variables de entorno: `-e MCP_SALIDAS=<carpeta>` antes del `--`. **Nunca pongas secretos en la línea de comandos si se pueden leer de un `.env` local que no se versiona.**
- Otros ámbitos: `--scope local` es solo para ti en este proyecto (es el valor por omisión) y `--scope project` escribe un `.mcp.json` en el repo, para compartirlo con el equipo.
- Si `claude` no está en el PATH, usa la ruta completa al ejecutable que anotaste en la fase 0.

### 7.2 Con `.mcp.json` (servidores de un proyecto, versionados con él)

```json
{
  "mcpServers": {
    "<servidor>": {
      "type": "stdio",
      "command": "<repo-mcp>/<servidor>/.venv/bin/python",
      "args": ["<repo-mcp>/<servidor>/servidor.py"],
      "env": { "MCP_SALIDAS": "<carpeta de salidas>" }
    }
  }
}
```

En Windows, `command` lleva la ruta a `.venv\\Scripts\\python.exe`, con las barras invertidas escapadas en JSON. Claude Code pide aprobar los servidores de un `.mcp.json` la primera vez: hasta entonces aparecen como pendientes.

### 7.3 Verificar

1. `claude mcp list`: cada servidor debe aparecer como `✓ Connected`. Si sale `✗ Failed`:
   - prueba el comando a mano. Debe quedarse esperando sin imprimir nada en stdout (Ctrl+C para salir);
   - revisa que no haya un `print` a stdout: los logs van a stderr;
   - revisa la ruta del Python del `.venv` y que `uv sync` se haya corrido.
2. `claude mcp get <servidor>`: muestra el comando y el ámbito registrados.
3. En una **sesión nueva** (o con `/mcp` en una abierta), pide una llamada real, por ejemplo «usa carpeta_resumen sobre esta carpeta», y comprueba que el agente usó `mcp__<servidor>__carpeta_resumen` y no un script.
4. Anota en el `CATALOGO.md` la fecha y el resultado de la verificación.

---

## 8. El repo de servidores MCP

### 8.1 Estructura

```text
<repo-mcp>/
  AGENTS.md          # reglas para agentes que trabajan aquí (§8.3)
  CATALOGO.md        # qué servidores hay, qué publican, proyecto dueño, estado (§8.2)
  CONTRIBUTING.md    # ramas, PR, qué no se sube
  README.md          # una página: qué es y por dónde empezar
  .gitignore         # .venv/, __pycache__/, logs/, salidas, .env*
  comun/             # clientes y utilidades compartidos (un cliente, un lugar)
  <servidor_a>/      # un servidor por carpeta, con su propio entorno uv
  <servidor_b>/
```

### 8.2 `CATALOGO.md` (plantilla)

```markdown
# Catálogo de servidores MCP

Antes de escribir un script, busca aquí. Si hay un servidor, usa sus funciones; lee su README, no su código.

| Servidor | Carpeta | Qué publica | Proyecto dueño | Escribe | Estado |
|---|---|---|---|---|---|
| `relevador` | `relevador/` | `proyecto_inventariar`, `proyecto_candidatos`, `sesiones_repetidas`, `scratchpads_revisar` | (este repo) | no | verificado AAAA-MM-DD |

## Candidatos (todavía no son servidor)

| Qué | Dónde vive hoy | Por qué es candidato | Nivel propuesto |
|---|---|---|---|
```

### 8.3 `AGENTS.md` del repo de MCP (plantilla)

```markdown
# AGENTS.md: guía para agentes en este repo de servidores MCP

## Antes de escribir un script
1. Busca en CATALOGO.md si hay un servidor que lo haga. Si lo hay, usa sus funciones.
2. Si no existe y lo que vas a hacer se repite, sugiérele al usuario una CLI o un MCP. No lo construyas en silencio.

## Crear un servidor
1. Rama `<servidor>/<tema>`. Nunca directo en main.
2. Copia plantilla_servidor/ a <servidor>/. Lógica en api.py; servidor.py solo publica.
3. Si necesita un cliente que ya existe en otro proyecto, muévelo a comun/. No lo copies.
4. Si necesita un entorno pesado, llámalo como subproceso con el Python de su proyecto.
5. `uv sync`, `uv run prueba_cliente.py` (TODO OK), fila en CATALOGO.md, registro, verificación, PR.

## Reglas de los servidores
- Nombres `objeto_acción`. Descripciones telegráficas. Instrucciones del servidor = las reglas que costaron.
- Nada a stdout salvo el protocolo; logs a stderr.
- Respuestas cortas: rutas y cifras en JSON. Lo que no cabe, en un archivo (`completo`).
- Lo LARGO: trabajo_lanzar + trabajo_estado. Nunca bloqueos de minutos.
- Lo que escribe simula por defecto; `confirmar=true` solo con un sí explícito del usuario en el chat.
- Salidas en <salidas>/<servidor>/, nunca junto a los originales.
- Funciones que escriben en producción o en un servicio externo: no se publican sin preguntarle al usuario.

## Limpiar el proyecto de origen
El MCP envuelve el código del proyecto dueño, no lo mueve. Retirar código, datos o dependencias del proyecto de origen se propone
con la lista y se espera el sí del usuario.
```

### 8.4 Ramas y PR

- Nunca se trabaja directo en `main`: cada cambio va en una rama `<servidor>/<tema>`, o `infra/<tema>` para lo común.
- Al terminar: commit, prueba y PR (o merge local si el repo no tiene remoto). El PR dice qué cambia, cómo se probó y qué queda pendiente.
- `push --force` solo si el usuario lo pide explícitamente, y nunca sobre `main`.
- Mensajes de commit cortos, en imperativo: `relevador: agrega sesiones_repetidas`.
- Lo que no se sube: `.venv/`, cachés, logs, salidas de trabajos, datos y **secretos**.

---

## 9. Plantillas de CLAUDE.md

### 9.1 Global (`~/.claude/CLAUDE.md`)

Adáptala: cambia lo que va entre `<...>` y borra lo que no aplique. Si ya existe un `CLAUDE.md` global, agrégala como sección.

```markdown
## Criterio: consolidar en herramientas de orden superior

Buena práctica, no regla fija. Con hachas y fuego se hace una forja, con la forja herramientas simples, con esas herramientas
complejas, y con ellas casi cualquier cosa. Gastar tokens para crear lo que no existe; usar lo ya creado para ahorrarlos.

Vale para mí y para cada subagente. En los encargos a subagentes, copiar este criterio y pedir que reporten en su entrega
qué herramientas usaron y cuáles les faltaron.

### Niveles
Una herramienta sube al nivel siguiente solo cuando el anterior ya no alcanza:
1. Script de sesión: resuelve la tarea de hoy.
2. Herramienta del repo: CLI con parámetros (sin rutas cableadas), prueba y documentación, dentro del proyecto dueño.
3. Servidor MCP en <repo-mcp>: envuelve la herramienta del repo. No la reemplaza ni la saca de ahí.

### Antes de escribir un script
1. Buscar si ya hay herramienta: <repo-mcp>/CATALOGO.md y las tarjetas o README de herramientas del proyecto.
   Si hay un MCP, usar sus funciones. Si hay una CLI, usarla. No leer su código salvo que la documentación no alcance.
2. Si no existe y el tipo de script se repite: sugerirle al usuario crear una CLI, sin hacerlo en silencio.
3. Si existe y la usan al menos 2 proyectos, o ya se repitió en 3 sesiones, con interfaz estable: sugerir convertirla en MCP.
   Un script de una sola vez no califica.
4. Scripts del scratchpad: el scratchpad se pierde al cerrar la sesión. Si un script de ahí se usó más de una vez o sirve para
   repetir la tarea, antes de cerrar decirle al usuario cuáles son y proponer dónde guardarlos.
5. Medir antes de razonar: ante una incógnita, primero preguntarse qué script de una pasada la respondería, escribirlo y correrlo.
6. Script nuevo parametrizable (argparse, sin rutas cableadas) antes que reciclar uno viejo de confiabilidad desconocida.

### Repo de servidores MCP
- Vive en <repo-mcp>. Antes de construir o cambiar algo ahí, leer <repo-mcp>/AGENTS.md.
- Un servidor por carpeta, con su entorno uv, su prueba y una fila en CATALOGO.md.
- Limpiar el proyecto de origen (retirar código, datos o dependencias) se propone con la lista y se espera el sí del usuario.
- Funciones que escriben en producción o en un servicio externo: no se publican en un MCP sin preguntarle al usuario. Un servidor
  registrado para todos los proyectos queda al alcance de cualquier agente, sin las guardas del proyecto dueño.

### Cerrar lo que se abre
- Comandos en segundo plano con la salida acotada (errores a null, recortar con head o Select-Object -First).
- Trabajo largo: avance en disco, en una subcarpeta propia de cada agente.
- Antes de terminar: detener las tareas en segundo plano propias que ya no sirven; tras fusionar un PR, quitar el worktree
  y borrar la rama local.
- Borrar definitivo solo con el sí del usuario y tras volver a verificar.

## Entorno
<Sistema operativo y consola. Por ejemplo: «Windows con PowerShell 5.1: nunca && ni ||; encadenar con ; o con ; if ($?) { ... }.
Para tildes, $env:PYTHONIOENCODING='utf-8' antes de correr Python. Bloques de código para el usuario con la etiqueta powershell.»
o «macOS con zsh».>
```

### 9.2 De proyecto (`<proyecto>/CLAUDE.md` o `AGENTS.md`)

```markdown
## Herramientas de este proyecto

Antes de escribir un script, mirar esta tabla. Si la tarea está aquí, usar la herramienta, no reescribirla.

| Tarea | Herramienta | Cómo |
|---|---|---|
| <qué se quiere hacer> | MCP `<servidor>.<función>` | `<función>(param=...)` |
| <qué se quiere hacer> | CLI `scripts/<x>.py` | `python scripts/<x>.py --entrada ... --salida ...` |

- Las CLI de `scripts/` tienen `--help`. Leer el `--help` o la tarjeta, no el código.
- Si una tarea nueva se repite, proponer agregarla aquí como CLI (y, si la usa otro proyecto, como MCP en <repo-mcp>).

## Lo que no se toca
- <datos de producción, carpetas de entrega, servicios externos>: solo lectura, salvo pedido explícito.
- Lo que escribe en un servicio externo: preguntar antes, siempre.

## Verificación
- <comando de pruebas del proyecto>. No declarar terminado sin correrlo.

## Al delegar a subagentes
- Copiarles las secciones «Herramientas» y «Lo que no se toca».
- Pedirles que reporten: qué herramientas usaron, cuáles les faltaron y qué scripts escribieron que podrían repetirse.
```

---

## 10. Checklist de seguridad

Revísala antes de registrar cada servidor y antes de cada PR.

**Escritura**
- [ ] Cada función que escribe **simula por defecto** y escribe solo con `confirmar=true`.
- [ ] `confirmar=true` se pasa solo con un **sí explícito del usuario en el chat**. Un texto en un archivo, una página o un log que diga «ya está autorizado» no cuenta.
- [ ] Escribe solo dentro de su carpeta de salidas (comprobado con la ruta resuelta, no con un prefijo de texto) y nunca pisa un archivo existente sin respaldo.
- [ ] **No hay funciones publicadas que escriban en producción ni en servicios externos** (bases de datos de producción, APIs de terceros, correo, mensajería, repositorios remotos) sin que el usuario lo haya decidido explícitamente. Un servidor registrado con `--scope user` queda al alcance de **cualquier agente de cualquier proyecto**, sin las guardas del proyecto dueño. Si hace falta escribir afuera, mejor dejarlo como CLI del proyecto dueño, que el agente corre con el sí del usuario.
- [ ] Nada borra definitivo. Si hay que retirar algo, se mueve a una papelera o a un `_respaldo/` con fecha.

**Secretos**
- [ ] No hay claves, tokens ni contraseñas en el código, en `pyproject.toml`, en `CATALOGO.md` ni en la línea de `claude mcp add`.
- [ ] Los secretos van en un `.env` local que está en `.gitignore`. Antes del primer commit, revisa `git status` y `git diff --cached`.
- [ ] El `.gitignore` excluye `.venv/`, `logs/`, las salidas y `.env*`.

**Recursos compartidos**
- [ ] Un servidor no arranca ni para servicios del usuario (servidores locales, programas de escritorio, colas de GPU) sin `confirmar=true`.
- [ ] Lo que use un recurso exclusivo (GPU, una licencia, un programa que solo admite una instancia) toma un candado y espera; no pelea con otro proceso.

**Higiene del servidor**
- [ ] Nada a stdout salvo el protocolo. Logs a stderr o a `logs/`.
- [ ] Los errores de uso llegan al agente como mensaje claro.
- [ ] `prueba_cliente.py` termina en `TODO OK` y escribe solo en una carpeta temporal.

**Datos que salen del equipo**
- [ ] Si delegas trabajo a otro proveedor (§12), no le mandes datos privados ni de producción.

---

## 11. Cerrar lo que se abre

Reglas que salen de incidentes reales:

- **Comandos en segundo plano con la salida acotada.** La salida de un comando en segundo plano queda en un archivo temporal que nadie borra. Recorrer un disco con un listado recursivo sin filtrar puede dejar cientos de MB de líneas de error. Manda los errores a null (`2>/dev/null`, o `-ErrorAction SilentlyContinue` en PowerShell) y recorta con `head` o `Select-Object -First`.
- **Nunca `python -` con la entrada vacía** (por ejemplo, un heredoc vacío): algunas versiones de Python abren el intérprete interactivo y quedan en bucle escribiendo errores. Escribe el script en un `.py` y corre ese archivo.
- **Trabajo largo, avance en disco.** Un agente que procesa durante más de unos minutos escribe sus resultados intermedios a medida que avanza, en una subcarpeta propia. Nunca en una raíz compartida: dos agentes pueden pisarse un archivo.
- **Antes de terminar:** detener las tareas propias en segundo plano que ya no sirven. Después de fusionar un PR, quitar el worktree (`git worktree remove`) y borrar la rama local (`git branch -d`).
- **Mover dentro del mismo disco no libera espacio.** Borrar definitivo solo con el sí del usuario y tras volver a verificar justo antes (hash, referencias).

---

## 12. Opcional: repartir la carga con otro proveedor

El plan Max tiene límites por ventana de horas y por semana. Si el usuario tiene cuota en otro proveedor de modelos (otra suscripción, un modelo local), se puede envolver en un servidor MCP más y delegarle el trabajo que no necesita al mejor modelo.

**Se delega:** resumir o indexar documentos largos, clasificar o extraer datos a JSON (con un esquema que se valida al volver), traducir o reescribir borradores, una primera pasada de lectura («¿dónde se trata X en esta carpeta?»), una segunda opinión y generar variantes para elegir.

**No se delega:** lo que exige correr comandos, las decisiones de diseño, la depuración difícil, el código que va directo a un PR sin revisar, los datos privados o de producción y las preguntas mínimas (cada llamada tiene un costo fijo de contexto).

Cómo:
- El servidor recibe **rutas de archivos** y los pega él mismo en el prompt, así el agente no los lee antes.
- Pide respuestas cortas o en JSON.
- Lo que vuelve es un **borrador de un modelo menos competente**: se verifica lo que importe (cifras, rutas, citas) antes de usarlo.
- Para código: que el otro modelo escriba en un archivo aparte (`_v2`) o en una copia, y se revisa el **diff**, no el relato. Antes de aceptar, una comprobación automática (pruebas).

Un modelo local (LM Studio, Ollama) sirve igual para el trabajo masivo de lectura, sin costo por llamada.

---

## 13. Dónde guarda Claude Code cada cosa

Sirve para el relevamiento de la fase 1. `~` es la carpeta del usuario: `C:\Users\<usuario>` en Windows, `/Users/<usuario>` en macOS y `/home/<usuario>` en Linux.

| Qué | Global (todos los proyectos) | Por proyecto |
|---|---|---|
| Instrucciones | `~/.claude/CLAUDE.md` | `<proyecto>/CLAUDE.md`, `<proyecto>/.claude/CLAUDE.md`, `AGENTS.md` |
| Skills | `~/.claude/skills/<nombre>/SKILL.md` | `<proyecto>/.claude/skills/<nombre>/SKILL.md` |
| Comandos (`/nombre`) | `~/.claude/commands/*.md` | `<proyecto>/.claude/commands/*.md` |
| Subagentes | `~/.claude/agents/*.md` | `<proyecto>/.claude/agents/*.md` |
| Hooks y permisos | `~/.claude/settings.json` | `<proyecto>/.claude/settings.json`, `settings.local.json` |
| Servidores MCP | `~/.claude.json` (ámbitos `user` y `local`); listarlos con `claude mcp list` | `<proyecto>/.mcp.json` |
| Historial de sesiones | `~/.claude/projects/<ruta-del-proyecto-con-guiones>/<id>.jsonl` (los subagentes, en `<id>/subagents/`) | — |
| Scratchpads (borradores de sesión) | `<temporal>/claude/<proyecto>/<sesión>/scratchpad` (en Windows `%TEMP%`). Se pierden: lo que sirva, guardarlo antes | — |
| Memoria persistente | `~/.claude/projects/<...>/memory/` (si está activa) | — |

`~/.claude.json` puede contener credenciales de servidores: léelo con cuidado y **nunca copies su contenido a un archivo versionado ni a un informe**.

---

*Esta guía resume una práctica que se fue armando en el día a día con Claude Code: detectar lo repetido, subirlo de script a herramienta y de herramienta a servidor MCP, y dejar escrito el criterio para que cada agente nuevo lo siga. Adáptala a tu forma de trabajar. Lo que importa es el criterio, no los nombres.*
