"""Load GCBA barrio polygons and label them the way the published tables do.

The open-data GeoJSON stores ``BARRIO`` and ``COMUNA`` in uppercase (``BOCA``,
not ``La Boca``). The coverage and population tables use title-case ``nombre``
and an integer ``comuna``. Renaming does not change the geometry.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd

_SPECIAL = {"BOCA": "La Boca"}


def display_barrio(name: object) -> str:
    """Map an official barrio name onto the label used in the result tables."""
    raw = str(name).strip()
    key = raw.upper()
    if key in _SPECIAL:
        return _SPECIAL[key]
    if raw != key:
        return raw
    return " ".join(part.capitalize() for part in raw.split(" "))


def normalize_barrios(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Return ``nombre``, ``comuna`` and ``geometry`` in EPSG:4326."""
    columns = {column.lower(): column for column in gdf.columns}
    name_col = columns.get("nombre") or columns.get("barrio")
    comuna_col = columns.get("comuna")
    if name_col is None or comuna_col is None or "geometry" not in gdf.columns:
        raise SystemExit(
            "Barrio file must have a name column (nombre or BARRIO), a comuna column, "
            f"and a geometry. Found columns: {list(gdf.columns)}"
        )
    out = gdf[[name_col, comuna_col, "geometry"]].copy()
    out = out.rename(columns={name_col: "nombre", comuna_col: "comuna"})
    out["nombre"] = out["nombre"].map(display_barrio)
    out["comuna"] = out["comuna"].astype(float).astype(int)
    if out.crs is None:
        out = out.set_crs(4326)
    return out.to_crs(4326)


def load_barrios(path: Path) -> gpd.GeoDataFrame:
    return normalize_barrios(gpd.read_file(path))
