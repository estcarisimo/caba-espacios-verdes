"""Turn Overpass JSON into the green-space polygons the coverage stage uses."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, Polygon
from shapely.ops import polygonize, unary_union

from caba_espacios_verdes.paths import Layout, require


def rel_to_geom(element: Mapping[str, object]):
    """Polygonize an OSM relation from Overpass ``out geom`` members."""
    outers: list[LineString] = []
    inners: list[LineString] = []
    members = element.get("members") or []
    if not isinstance(members, list):
        return None
    for member in members:
        if not isinstance(member, dict):
            continue
        if member.get("type") != "way" or "geometry" not in member:
            continue
        line = LineString([(point["lon"], point["lat"]) for point in member["geometry"]])
        if member.get("role") == "inner":
            inners.append(line)
        else:
            outers.append(line)
    if not outers:
        return None
    outer = unary_union(list(polygonize(unary_union(outers))))
    if inners:
        inner = unary_union(list(polygonize(unary_union(inners))))
        outer = outer.difference(inner)
    if outer.is_empty:
        return None
    return outer


def way_to_geom(element: Mapping[str, object]):
    """Closed OSM way to a polygon. Open ways are dropped."""
    geometry = element.get("geometry")
    if not isinstance(geometry, list) or len(geometry) < 4:
        return None
    coords = [(point["lon"], point["lat"]) for point in geometry]
    if coords[0] != coords[-1]:
        return None
    polygon = Polygon(coords)
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if polygon.is_empty:
        return None
    return polygon


def _category(tags: Mapping[str, str]) -> str:
    if tags.get("leisure") == "golf_course":
        return "leisure=golf_course"
    if tags.get("leisure") == "nature_reserve":
        return "leisure=nature_reserve"
    if tags.get("leisure") == "park":
        return "leisure=park"
    if tags.get("leisure") == "garden":
        return "leisure=garden"
    if tags.get("place") == "square":
        return "place=square"
    if tags.get("landuse") == "recreation_ground":
        return "landuse=recreation_ground"
    return "other"


def _load_elements(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    elements = payload.get("elements")
    if not isinstance(elements, list):
        remark = payload.get("remark") or payload.get("error") or "no elements"
        raise SystemExit(f"{path} is not an Overpass result ({remark}).")
    return elements


def build(layout: Layout) -> None:
    """Write the CABA boundary and the raw green-space inventory."""
    layout.ensure()
    require(layout.boundary_json, "Run `caba-espacios-verdes download` first.")
    require(layout.green_json, "Run `caba-espacios-verdes download` first.")

    boundary = _load_elements(layout.boundary_json)[0]
    caba = gpd.GeoDataFrame(
        {"name": [boundary["tags"]["name"]]},
        geometry=[rel_to_geom(boundary)],
        crs=4326,
    )
    caba.to_file(layout.boundary_osm, driver="GeoJSON")

    rows = []
    for element in _load_elements(layout.green_json):
        tags = element.get("tags") or {}
        if element["type"] == "way":
            geometry = way_to_geom(element)
        elif element["type"] == "relation":
            geometry = rel_to_geom(element)
        else:
            geometry = None
        rows.append(
            {
                "osm_type": element["type"],
                "osm_id": element["id"],
                "name": tags.get("name"),
                "cat": _category(tags),
                "access": tags.get("access"),
                "leisure": tags.get("leisure"),
                "place": tags.get("place"),
                "landuse": tags.get("landuse"),
                "garden_type": tags.get("garden:type"),
                "geometry": geometry,
            }
        )
    frame = pd.DataFrame(rows)
    frame["has_poly"] = frame.geometry.notna()
    polygons = gpd.GeoDataFrame(frame[frame.has_poly].copy(), geometry="geometry", crs=4326)
    polygons.to_file(layout.green_raw, driver="GeoJSON")
    inventory = layout.results / "green_raw_inventory.csv"
    frame.drop(columns="geometry").to_csv(inventory, index=False)
    print(pd.crosstab(frame.cat, [frame.osm_type, frame.has_poly]))
    print(frame.access.value_counts(dropna=False))
    print(f"wrote {layout.boundary_osm}")
    print(f"wrote {layout.green_raw}")
    print(f"wrote {inventory}")
