"""Directories the pipeline reads and writes.

Downloaded inputs and intermediate geometries live under ``data/``. Small tables
and JSON summaries live under ``results/``. Both directories are gitignored;
the committed figures are the PNG maps already in ``figures/``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Layout:
    """Resolved locations for one pipeline run."""

    data: Path
    results: Path
    figures: Path

    @classmethod
    def from_options(
        cls,
        data: str | os.PathLike[str] | None = None,
        results: str | os.PathLike[str] | None = None,
        figures: str | os.PathLike[str] | None = None,
    ) -> Layout:
        return cls(
            data=Path(data or os.environ.get("CABA_DATA_DIR", "data")),
            results=Path(results or os.environ.get("CABA_RESULTS_DIR", "results")),
            figures=Path(figures or os.environ.get("CABA_FIGURES_DIR", "figures")),
        )

    def ensure(self) -> Layout:
        for path in (self.raw, self.interim, self.calidad, self.results, self.figures):
            path.mkdir(parents=True, exist_ok=True)
        return self

    @property
    def raw(self) -> Path:
        return self.data / "raw"

    @property
    def interim(self) -> Path:
        return self.data / "interim"

    @property
    def calidad(self) -> Path:
        return self.data / "calidad_src"

    @property
    def boundary_json(self) -> Path:
        return self.raw / "boundary.json"

    @property
    def green_json(self) -> Path:
        return self.raw / "green.json"

    @property
    def barrios(self) -> Path:
        return self.raw / "barrios.geojson"

    @property
    def radios(self) -> Path:
        return self.raw / "radios_censo2022_ideec.geojson"

    @property
    def boundary_osm(self) -> Path:
        return self.interim / "caba_boundary_osm.geojson"

    @property
    def green_raw(self) -> Path:
        return self.interim / "green_raw.geojson"

    @property
    def green_used(self) -> Path:
        return self.interim / "espacios_verdes_usados.geojson"

    @property
    def resumen(self) -> Path:
        return self.results / "resumen.json"

    @property
    def resumen_poblacion(self) -> Path:
        return self.results / "resumen_poblacion.json"

    @property
    def resumen_calidad(self) -> Path:
        return self.results / "resumen_calidad.json"

    @property
    def sentinel_tif(self) -> Path:
        return self.calidad / "s2_median_b04_b08_ndvi_32721.tif"

    @property
    def scenes_json(self) -> Path:
        return self.calidad / "escenas.json"

    def chm_tile(self, tile_id: str) -> Path:
        return self.calidad / f"meta_chm_{tile_id}.tif"


def require(path: Path, hint: str) -> Path:
    """Return ``path`` or exit with a message naming the stage that produces it."""
    if not path.exists():
        raise SystemExit(f"Missing {path}. {hint}")
    return path
