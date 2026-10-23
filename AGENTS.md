# AGENTS.md

Instructions for AI coding agents working in this repository. Humans should
read [CONTRIBUTING.md](CONTRIBUTING.md) and [README.md](README.md).

## What this project is

`caba-espacios-verdes` measures access to public green space in Ciudad
Autónoma de Buenos Aires. The command-line tool downloads OpenStreetMap parks
and plazas, buffers them by 500 m, weights the gap by the INDEC 2022 census,
and estimates accessible square metres per resident with a two-step floating
catchment area (2SFCA). A summer Sentinel-2 NDVI composite then repeats that
metric on vegetated area.

The distribution name, the import package, and the command are
`caba-espacios-verdes`, `caba_espacios_verdes`, and `caba-espacios-verdes`.
It is not on PyPI. Install it from this repository with uv. The version is
`0.1.0` in `pyproject.toml`, `src/caba_espacios_verdes/__init__.py`, and
`CITATION.cff`. Change those three together.

## Setup

Python 3.12 is what CI uses; 3.10 or newer works. `.python-version` pins 3.12.

```bash
uv sync
uv run pre-commit install
```

`uv sync` creates `.venv` and installs the package plus pytest, ruff, and
pre-commit. Prefix commands with `uv run`, or activate `.venv`. CI installs
with `uv sync --locked`. Do not edit `uv.lock` by hand.

## Run

```bash
uv run caba-espacios-verdes --help
uv run caba-espacios-verdes version
```

Stages run in this order. Each one reads what the previous stage wrote.
`make download`, `make coverage`, `make population`, `make quality`,
`make maps`, and `make all` call the same commands.

```bash
uv run caba-espacios-verdes download
uv run caba-espacios-verdes coverage
uv run caba-espacios-verdes population
uv run caba-espacios-verdes quality
uv run caba-espacios-verdes maps
uv run caba-espacios-verdes all
```

`download`, `population`, `quality`, and `all` need the network. `quality`
downloads two canopy-height tiles of about 530 MB each and writes a Sentinel
window under `data/`. Do not run those stages unless the task is to regenerate
a result. Tests and CI never download OSM, the census, Sentinel-2, or the
canopy tiles.

Paths default to `data/`, `results/`, and `figures/` next to the repository
root. Override them with `--data-dir`, `--results-dir`, and `--figures-dir`,
or with `CABA_DATA_DIR`, `CABA_RESULTS_DIR`, and `CABA_FIGURES_DIR`.

## Test

```bash
uv run pytest
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run caba-espacios-verdes version
```

`make test` and `make lint` wrap the same pytest and ruff commands. The suite
imports the package, checks the Overpass filters and the data-source URLs,
builds polygons from a small fixture, and runs the 500 m coverage math on a
synthetic city. Keep new tests off the network. A test that needs the network
should be marked and left out of the default run.

Do not commit `data/` or `results/`. Both are gitignored. The PNG maps in
`figures/` are the published figures; regenerate them only when a change is
supposed to change the maps, and say so in the pull request.

## Layout

```text
src/caba_espacios_verdes/
  cli.py                 download, coverage, population, quality, maps, all
  download.py            Overpass, GCBA barrios, IDECBA WFS, canopy tiles
  osm.py                 Overpass ways and relations to polygons
  coverage.py            Filters and the 500 m scenarios
  population.py          Census overlay and 2SFCA
  quality.py             Zonal NDVI, vegetated 2SFCA
  quality_composite.py   Sentinel-2 median composite
  maps_*.py              PNG maps
  sources.py             Dataset URLs and numeric constants
  queries/               Overpass query text
tests/                   pytest; no network
```

Distances, area thresholds, and census constants live in `sources.py` and in
the stage modules. There is no YAML config file.
