.PHONY: sync download coverage population quality maps all lint test

sync:
	uv sync

download:
	uv run caba-espacios-verdes download

coverage:
	uv run caba-espacios-verdes coverage

population:
	uv run caba-espacios-verdes population

quality:
	uv run caba-espacios-verdes quality

maps:
	uv run caba-espacios-verdes maps

all:
	uv run caba-espacios-verdes all

lint:
	uv run ruff check src/ tests/
	uv run ruff format --check src/ tests/

test:
	uv run pytest
