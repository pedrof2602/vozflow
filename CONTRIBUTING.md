# Cómo colaborar con vozflow

¡Gracias por querer ayudar! Esta guía es corta a propósito.

## Antes de empezar

- Todo va **en español**: código, comentarios, mensajes, documentación y commits.
- Mirá las incidencias abiertas antes de empezar algo grande, así no repetimos trabajo.

## Preparar el proyecto

Necesitás Linux con GNOME, [uv](https://docs.astral.sh/uv/) y Python 3.14 (uv lo instala solo):

```bash
git clone https://github.com/pedrof2602/vozflow.git
cd vozflow
uv sync
```

## Correr las pruebas

Todo lo que se verifica corre con un solo comando, el mismo que corre la integración continua:

```bash
scripts/ci.sh
```

Revisa el formato (`ruff format`), el estilo (`ruff check`), los tipos (`mypy` estricto) y las
pruebas (`pytest`). **Tiene que quedar en verde antes de proponer un cambio.**

## Cómo trabajamos

- **La prueba primero.** Escribí la prueba, mirala **fallar** por la razón correcta y recién
  después escribí el código. No se modifica una prueba para que pase, ni se la saltea.
- **Cambios chicos y enfocados**: una idea por propuesta.
- **Commits** en español, en una línea que diga qué cambió.

## Lo que nunca se sube

- **Audios** (`.wav`, `.mp3`…): lo que dictás es privado, también en las pruebas.
- **Modelos** de voz (archivos `model.bin` y parecidos): pesan cientos de megas.
- **Claves** de acceso, contraseñas, archivos `.env` ni datos personales.

Antes de proponer un cambio podés revisar el repositorio con
`uv run python scripts/revisar_publicacion.py`.

## Probar en tu computadora

Lo que depende del escritorio (atajos, pegado, ventana activa) no se puede probar solo con
`scripts/ci.sh`. Probalo a mano en tu escritorio y contá en la propuesta qué probaste.

## Reportar un fallo o proponer algo

Usá las plantillas de [incidencias](../../issues/new/choose). Para un fallo, pegá el resultado de
`uv run python -m vozflow diagnostico --copiable`: no incluye nada personal.
