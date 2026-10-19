# vozflow

Dictado por voz local para el escritorio, al estilo Wispr Flow. Hablás, soltás la tecla y el texto
aparece donde tenías el cursor: en la terminal, en VS Code, en el navegador, en el chat.

- **Todo el reconocimiento de voz es local.** El audio no sale de tu computadora.
- Español (rioplatense o neutro) e inglés, con detección automática, y traducción a cualquier
  idioma con una tecla aparte (opcional).
- Puntuación, mayúsculas y comandos de voz («nueva línea», «punto», «borra eso») por reglas, sin
  modelo de lenguaje.
- Diccionario personal, atajos de texto, modos por aplicación e historial.
- Reescritura con un modelo de lenguaje (Ollama, Anthropic u OpenRouter): **opcional y apagada**.
  Sin un proveedor activo, nada sale de tu computadora.

Es una aplicación personal hecha para un solo equipo: Fedora con GNOME sobre Wayland.

## Requisitos

| Requisito | Para qué |
|---|---|
| GNOME Shell sobre Wayland | atajos globales y pegado en la ventana activa |
| Python 3.14 y [uv](https://docs.astral.sh/uv/) | correr el proyecto |
| Tu usuario en el grupo `input` | mantener-para-hablar (lectura del teclado) |
| `wl-clipboard` (`wl-copy`, `wl-paste`) | copiar el texto antes de pegarlo |
| `ydotoold` corriendo | mandar la combinación de pegado (respaldo: portal de escritorio remoto) |
| `portaudio` | captura de audio |
| `gnome-keyring` | guardar las claves de acceso de la reescritura |
| `gnome-shell-extension-appindicator` | ícono en la bandeja (si falta, vozflow usa su ventana) |

Para ver el ícono en la bandeja:

```bash
sudo dnf install gnome-shell-extension-appindicator
gnome-extensions enable appindicatorsupport@rgcjonas.gmail.com
```

(cerrá y volvé a abrir la sesión para que GNOME la cargue).

## Instalación

```bash
git clone https://github.com/pedrof2602/vozflow.git ~/Proyectos/vozflow
cd ~/Proyectos/vozflow
uv sync
uv run python -m vozflow descargar-modelo   # única vez que usa internet (~480 MB)
uv run python -m vozflow diagnostico        # revisa que el escritorio tenga todo lo necesario
```

## Uso diario

```bash
uv run python -m vozflow
```

Abre la bandeja y queda esperando. Para que arranque con la sesión:

```bash
uv run python -m vozflow autoinicio activar     # y `desactivar` para sacarlo
```

### Atajos (se cambian desde Ajustes → Teclas)

| Qué | Por defecto |
|---|---|
| Mantener para hablar | mantener apretada la tecla **Ctrl derecha** |
| Pulsar para empezar y terminar | **Ctrl + Alt + Espacio** |
| Mantener para hablar y **traducir** | mantener apretada la tecla **Alt derecha** (AltGr) |

Mientras grabás aparece un indicador pequeño abajo en la pantalla; no toma el foco, así que el
texto se inserta donde estaba el cursor. **Nunca se envía Enter.**

### Traducir lo que decís

Con la tercera tecla (Alt derecha), lo que dictás se traduce al idioma que elijas (por defecto,
inglés) antes de pegarse: hablás en español y escribís en inglés, o al revés. El idioma se escribe
a mano en Ajustes → Reescritura (sirve cualquiera que conozca el modelo) o con
`uv run python -m vozflow proveedor idioma portugués`.

Usa el mismo servicio de la reescritura (Claude, OpenRouter u Ollama), con su clave y su
interruptor general, que vienen apagados. Si no está configurado, no hay red o la clave falla, **no
se pega nada** en el idioma equivocado: aparece un aviso y el texto dictado queda en el historial.
Cuando dictás con la tecla de traducir, el indicador muestra el idioma de destino.

### Comandos de voz

«nueva línea», «punto», «coma», «dos puntos», «signo de interrogación», «abre paréntesis»,
«borra eso»… La tabla completa está en `specs/001-vozflow/contracts/comandos-de-voz.md`.

### Ajustes

Desde el ícono de la bandeja → *Abrir ajustes*: teclas, micrófono e idioma, modos por aplicación
(una terminal siempre recibe el texto en una sola línea), diccionario y atajos de texto,
reescritura, copia de seguridad e historial.

### Sin interfaz

```bash
uv run python -m vozflow --sin-interfaz        # solo el servicio de atajos
uv run python -m vozflow dictar --segundos 10  # grabar unos segundos y ver el texto
uv run python -m vozflow diccionario --help    # también: atajos, modos, asignar, historial,
                                               # exportar, importar y proveedor
```

## Aspecto

La ventana de ajustes sigue el aspecto de OpenWhispr (`docs/diseno/referencia-openwhispr.md`):
barra lateral agrupada (Inicio, Texto, Dictado, Inteligencia artificial, Datos), tarjetas
redondeadas, interruptores, teclas dibujadas como teclas y un tema que se elige en Ajustes → Apariencia (automático, claro u oscuro; el
automático sigue al del sistema), sin reiniciar, con acento cherry lavado. El indicador flotante es una píldora oscura con barras de onda que
siguen tu voz, y muestra «→ idioma» al traducir. La tipografía es la primera instalada entre
Inter, Adwaita Sans, Noto Sans y Cantarell; no se empaqueta ninguna fuente.

## Qué guarda y dónde

- `~/.local/share/vozflow/vozflow.db`: diccionario, atajos, modos, ajustes e historial. **El audio
  no se guarda.** El historial se puede apagar en Ajustes.
- Las claves de acceso viven en el llavero del escritorio, nunca en ese archivo ni en los
  registros.

## Solución de problemas

| Síntoma | Qué mirar |
|---|---|
| La tecla no hace nada | `uv run python -m vozflow diagnostico`: indica qué falta |
| «Atajo ocupado» al arrancar | otra función de GNOME usa esa combinación: cambiala en Ajustes → Teclas |
| No aparece el ícono | falta la extensión AppIndicator; la ventana de ajustes muestra el estado |
| El texto sale en la ventana equivocada | el historial guarda la aplicación detectada |
| Se pega como `^V` en la terminal | marcá la aplicación como terminal en Ajustes → Modos |
| Muy lento | `motor.hilos` en Ajustes → Audio (4 fue lo medido como mejor) |

## Salvedades

- **El texto dictado pasa por el portapapeles.** vozflow lo copia, manda la combinación de pegado
  y restaura lo que tenías. Si usás un historial de portapapeles (por ejemplo la extensión
  `clipboard-indicator`), el texto dictado queda anotado ahí.
- **La detección de la ventana activa no ve todo.** Chrome, Teams y Obsidian no se identifican
  hoy; en esas aplicaciones se usa el modo general. El pegado no depende de eso.
- Cambiar el micrófono, el idioma, el modelo o los hilos rige al reiniciar vozflow; las teclas y el
  indicador rigen enseguida.

## Desarrollo

`scripts/ci.sh` corre el formato, `ruff`, `mypy` estricto y las pruebas (el mismo script que la
CI de GitHub). La especificación, el plan y las tareas están en `specs/001-vozflow/`; las
validaciones hechas a mano, en `docs/validacion/`. Las convenciones de trabajo, en `CLAUDE.md`.
