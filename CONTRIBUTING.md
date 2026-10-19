# Contributing

Thanks for looking at this project. The analysis is a reproducible description of one city, so changes should keep the method stable unless the pull request says, in the description, exactly which step changed and why.

## Setup

```bash
git clone https://github.com/estcarisimo/caba-espacios-verdes.git
cd caba-espacios-verdes
uv sync
uv run pre-commit install
```

`uv sync` installs the package and the development tools (pytest, ruff, pre-commit). Python 3.10 or newer is required; CI runs 3.12.

## Checks

```bash
uv run ruff check src/ tests/
uv run ruff format src/ tests/
uv run pytest
uv run caba-espacios-verdes version
```

The test suite does not call Overpass, the census WFS, Earth Search or the canopy bucket. Please keep it that way: a new test that needs the network should be marked and left out of the default run.

`ruff check` and `ruff format --check` are required in CI.

## Pull requests

1. Fork the repository.
2. Create a feature branch (`git switch -c feat/amazing-feature`).
3. Commit your changes (`git commit -m 'feat: add amazing feature'`).
4. Push the branch (`git push origin feat/amazing-feature`).
5. Open a pull request.

Do not commit `data/` or `results/`. Those directories are produced by the pipeline and are gitignored. The PNG maps in `figures/` are the published figures; regenerate them only when a code change is supposed to change the maps, and say so in the pull request.
