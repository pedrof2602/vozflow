# vozflow

Dictá en lugar de escribir. Mantenés apretada una tecla, hablás, la soltás y el texto aparece donde
tenías el cursor: en un mensaje, un mail, un documento, la terminal.

Todo se entiende **en tu computadora**: tu voz no viaja por internet.

## Qué hace

- **Escribe lo que decís** en español o en inglés (y mezclados), con puntos, comas y mayúsculas.
- **Funciona en cualquier aplicación**: no hace falta copiar y pegar.
- **Entiende comandos de voz**: decí «nueva línea» o «punto» y escribe el signo.
- **Quita muletillas** («eh», «mmm») y repeticiones.
- **Aprende tus palabras**: nombres propios, términos de tu trabajo, y atajos para escribir textos
  largos con una frase.
- **Guarda un historial** de lo que dictaste, para buscarlo o recuperarlo si algo falla (se puede
  apagar).
- **Opcional**: un asistente de IA que mejora o traduce el texto. Viene apagado.

## Tu privacidad

- **Tu voz no sale de tu computadora**: se procesa ahí mismo, el audio nunca viaja ni se guarda.
- **Tus datos se quedan en tu computadora**: historial, vocabulario y ajustes están en una carpeta
  tuya (`~/.local/share/vozflow`).
- **No hay telemetría**: vozflow no manda estadísticas ni avisa nada a nadie.
- **Las claves** de los servicios de IA, si las usás, se guardan en el llavero de tu sistema, nunca
  en un archivo ni en los registros.
- **Con el asistente de IA apagado** (como viene) no sale nada de tu computadora.
  Si lo prendés, solo el texto que dictaste con las teclas de mejorar o de traducir viaja al
  servicio que elijas; el audio, nunca. **Dictar a secas nunca usa el asistente de IA.**
- **El texto pasa por el portapapeles** un instante para poder pegarse. Si usás una extensión que
  guarda un historial del portapapeles, ahí va a quedar anotado lo que dictaste.
- **Solo hay una excepción**: la primera vez baja el modelo de voz de internet (unos 480 MB).
  Después funciona sin conexión.

## Instalar

Necesitás **Linux con GNOME** (el escritorio de Fedora y de Ubuntu, entre otros) y unos **3 GB**
libres. Está probado en **Fedora**; en Ubuntu y Debian debería andar, y te pedimos que nos cuentes si
no. Todavía no funciona en Windows, macOS ni con otros escritorios.

Abrí una terminal y pegá estas tres líneas:

```bash
git clone https://github.com/pedrof2602/vozflow.git
cd vozflow
./scripts/instalar.sh
```

El instalador te cuenta qué va a hacer, te pide la contraseña de tu computadora **una sola vez**,
baja el modelo de voz y deja vozflow en tu menú de aplicaciones. Si algo falta, te lo dice en
palabras simples. Si lo corrés de nuevo, actualiza lo que haga falta sin romper nada.

Al final puede pedirte que **cierres sesión y vuelvas a entrar**: es para que el teclado funcione.

## Usarla en 3 pasos

1. Abrí **vozflow** desde el menú de aplicaciones. La primera vez te guía para elegir el micrófono y
   probar tu voz.
2. Hacé clic donde quieras escribir y **mantené apretada la tecla** para dictar (por defecto, la
   tecla **Ctrl de la derecha**). Hablá.
3. **Soltala**: el texto aparece donde tenías el cursor.

**Tres teclas, cada una hace una sola cosa** (todas se mantienen apretadas mientras hablás):

- **Ctrl de la derecha**: dictar tal cual. El texto sale limpio y no pasa por ningún servicio.
- **Shift de la derecha**: dictar y **mejorar** el texto con el asistente de IA (redacción,
  puntuación, el estilo de tu modo).
- **Alt de la derecha**: dictar, **mejorar y traducir** al idioma que elijas.

Las dos últimas necesitan el asistente de IA prendido (**Ajustes → Avanzado → Asistente de IA**).
Podés cambiar las teclas, el micrófono, el idioma y el tema en la ventana de **Ajustes**.

## Si algo no anda

| Si pasa esto | Probá esto |
|---|---|
| La tecla no hace nada | Si recién instalaste, cerrá sesión y volvé a entrar. Después abrí **Ajustes → Dictado**. |
| El texto no aparece en la ventana | Abrí **Ajustes → Historial**: ahí está lo que dictaste, con el motivo. Tocá **Copiar** y pegalo con Ctrl+V. |
| La barra del micrófono no se mueve | **Ajustes → Dictado → Micrófono**: elegí otro. |
| Dice que falta el modelo de voz | Corré `python -m vozflow descargar-modelo` (necesita internet esta única vez). |
| No veo el ícono arriba | GNOME no muestra íconos de bandeja sin una extensión. vozflow anda igual: abrila desde el menú. |
| Anda lento | **Ajustes → Avanzado → Modelo y rendimiento**: probá un modelo más chico, como «base». |
| En la terminal pega algo raro (`^V`) | **Ajustes → Avanzado → Modos**: marcá esa aplicación como terminal. |

## Cómo reportar un problema

1. Abrí una terminal en la carpeta de vozflow y corré:

   ```bash
   uv run python -m vozflow diagnostico --copiable
   ```

2. Copiá lo que sale y pegalo en una [incidencia nueva](../../issues/new/choose).

Ese resumen **no incluye** lo que dictaste, los títulos de tus ventanas, el nombre de tus
micrófonos ni tus claves.

## Desinstalar

```bash
./scripts/desinstalar.sh
```

Saca vozflow del menú y del arranque, y **te pregunta por separado** antes de borrar tus datos, el
modelo de voz, tus claves o los permisos del teclado. Si decís que no, no pierde nada.

## Licencia

vozflow es software libre con [licencia MIT](LICENSE): podés usarlo, copiarlo y modificarlo.

Se escribió desde cero; la app [OpenWhispr](https://github.com/OpenWhispr/openwhispr) fue una
inspiración para entender el problema, pero no se copió su código.

## Para quien quiera colaborar

Mirá [CONTRIBUTING.md](CONTRIBUTING.md): cómo preparar el proyecto, correr las pruebas y proponer
cambios. Todo (código, comentarios, documentación) está en español.
