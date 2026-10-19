"""Download OSM, GCBA barrios and the IDECBA census layer into ``data/raw``."""

from __future__ import annotations

import json
import shutil
import time
import urllib.error
import urllib.request
from importlib.resources import files
from pathlib import Path

from caba_espacios_verdes.barrios import normalize_barrios
from caba_espacios_verdes.paths import Layout
from caba_espacios_verdes.sources import (
    BARRIOS_GEOJSON_URL,
    CHM_TILES,
    DEFAULT_OSM_DATE,
    OVERPASS_URL,
    USER_AGENT,
    WFS_URL,
)

_ATTEMPTS = 4


def query_text(name: str) -> str:
    """Overpass query shipped with the package (``q_boundary.txt`` or ``q_green.txt``)."""
    return files("caba_espacios_verdes").joinpath(f"queries/{name}").read_text(encoding="utf-8")


def with_osm_date(query: str, osm_date: str) -> str:
    """Pin an Overpass query to an attic date. ``now`` leaves the query unchanged."""
    if not osm_date or osm_date == "now":
        return query
    token = f'[date:"{osm_date}T23:59:59Z"]'
    return query.replace("];", f"]{token};", 1)


def _request(url: str, data: bytes | None = None, timeout: int = 600) -> urllib.request.Request:
    headers = {"User-Agent": USER_AGENT}
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded; charset=utf-8"
    return urllib.request.Request(url, data=data, headers=headers)


def download_file(url: str, dest: Path, *, force: bool = False, timeout: int = 600) -> None:
    """Stream ``url`` to ``dest``. Existing non-empty files are kept unless ``force``."""
    if dest.exists() and not force and dest.stat().st_size > 0:
        print(f"keep {dest}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    temporary = dest.with_suffix(dest.suffix + ".part")
    last_error: Exception | None = None
    for attempt in range(1, _ATTEMPTS + 1):
        try:
            print(f"downloading {url}")
            with (
                urllib.request.urlopen(_request(url, timeout=timeout), timeout=timeout) as response,
                temporary.open("wb") as handle,
            ):
                shutil.copyfileobj(response, handle)
            temporary.replace(dest)
            print(f"wrote {dest} ({dest.stat().st_size} bytes)")
            return
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            print(f"download failed ({attempt}/{_ATTEMPTS}): {exc}")
            time.sleep(min(2**attempt, 30))
    raise SystemExit(f"Could not download {url} to {dest}: {last_error}")


def overpass_to_file(query: str, dest: Path, *, force: bool = False) -> None:
    if dest.exists() and not force and dest.stat().st_size > 0:
        print(f"keep {dest}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    body = query.encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(1, _ATTEMPTS + 1):
        try:
            print(f"querying Overpass -> {dest.name}")
            with urllib.request.urlopen(_request(OVERPASS_URL, data=body), timeout=600) as response:
                payload = response.read()
            parsed = json.loads(payload)
            if "elements" not in parsed:
                remark = parsed.get("remark") or parsed
                raise RuntimeError(f"Overpass returned no elements: {remark}")
            dest.write_bytes(payload)
            print(f"wrote {dest} ({len(parsed['elements'])} elements)")
            return
        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
            RuntimeError,
            json.JSONDecodeError,
        ) as exc:
            last_error = exc
            print(f"Overpass failed ({attempt}/{_ATTEMPTS}): {exc}")
            time.sleep(min(2**attempt, 30))
    raise SystemExit(f"Could not query Overpass for {dest.name}: {last_error}")


def download_inputs(
    layout: Layout, *, osm_date: str = DEFAULT_OSM_DATE, force: bool = False
) -> None:
    """Download the four inputs the coverage and population stages read."""
    layout.ensure()
    overpass_to_file(
        with_osm_date(query_text("q_boundary.txt"), osm_date), layout.boundary_json, force=force
    )
    overpass_to_file(
        with_osm_date(query_text("q_green.txt"), osm_date), layout.green_json, force=force
    )
    download_file(BARRIOS_GEOJSON_URL, layout.barrios, force=force)
    _normalize_barrios_file(layout.barrios)
    download_file(WFS_URL, layout.radios, force=force)
    print(
        "Inputs are in "
        f"{layout.raw}. OSM date: {osm_date}. "
        "Pass --osm-date now to use the live Overpass database."
    )


def download_canopy(layout: Layout, *, force: bool = False) -> None:
    """Download the two Meta/WRI canopy-height tiles that cover CABA."""
    layout.ensure()
    for tile_id, url in CHM_TILES.items():
        download_file(url, layout.chm_tile(tile_id), force=force)


def _normalize_barrios_file(path: Path) -> None:
    import geopandas as gpd

    normalized = normalize_barrios(gpd.read_file(path))
    normalized.to_file(path, driver="GeoJSON")
    print(f"normalized {len(normalized)} barrios -> {path}")
