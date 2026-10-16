#!/usr/bin/env bash
# Batería completa: todo verde antes de commitear.
set -euo pipefail
cd "$(dirname "$0")/.."
uv sync --locked
uv run ruff format --check
uv run ruff check
uv run mypy src tests
uv run pytest
