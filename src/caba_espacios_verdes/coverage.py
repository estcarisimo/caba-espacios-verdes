"""500 m straight-line coverage of OSM green space, in EPSG:5347.

A resident is covered when they are within 500 m of the perimeter of a public
green space, not of its centroid. Three scenarios are written: every kept
space, only spaces of at least 0.5 ha, and every kept space except
``landuse=recreation_ground``.
"""

from __future__ import annotations

import geopandas as gpd
from shapely.ops import unary_union

from caba_espacios_verdes.barrios import load_barrios
from caba_espacios_verdes.jsonio import dumps, write
from caba_espacios_verdes.osm import build
from caba_espacios_verdes.paths import Layout, require
from caba_espacios_verdes.sources import BUFFER_M, METRIC_CRS, MIN_HA, OSM_RELATION_ID, QUAD_SEGS


def run(layout: Layout) -> dict:
    """Build polygons from the Overpass extracts, then write the coverage tables."""
    layout.ensure()
    build(layout)
    return analyze(layout)


def analyze(layout: Layout) -> dict:
    require(layout.boundary_osm, "Run `caba-espacios-verdes coverage` first.")
    require(layout.green_raw, "Run `caba-espacios-verdes coverage` first.")
    require(layout.barrios, "Run `caba-espacios-verdes download` first.")

    caba = gpd.read_file(layout.boundary_osm).to_crs(METRIC_CRS)
    city = caba.geometry.iloc[0]
    barrios = load_barrios(layout.barrios).to_crs(METRIC_CRS)[["nombre", "comuna", "geometry"]]
    green = gpd.read_file(layout.green_raw).to_crs(METRIC_CRS)
    green["ha"] = green.area / 1e4
    raw_count = len(green)

    excluded: dict[str, int] = {}
    drop_type = green.cat.isin(["leisure=golf_course", "leisure=nature_reserve"])
    excluded["tipo excluido (golf_course / nature_reserve)"] = int(drop_type.sum())
    drop_access = green.access.isin(["private", "no", "customers"])
    excluded["access=private/no/customers"] = int((drop_access & ~drop_type).sum())
    drop_residential = green.garden_type == "residential"
    excluded["garden:type=residential"] = int((drop_residential & ~drop_type & ~drop_access).sum())
    inside = green.geometry.representative_point().within(city)
    excluded["fuera de CABA (punto representativo)"] = int(
        (~inside & ~drop_type & ~drop_access & ~drop_residential).sum()
    )

    kept = green[~drop_type & ~drop_access & ~drop_residential & inside].copy()
    kept["geometry"] = kept.geometry.intersection(city)
    kept = kept[~kept.is_empty]
    kept["ha"] = kept.area / 1e4
    kept.to_crs(4326).to_file(layout.green_used, driver="GeoJSON")

    summary = {
        "osm_relation": OSM_RELATION_ID,
        "caba_osm_area_km2": round(city.area / 1e6, 3),
        "barrios_gcba_union_area_km2": round(unary_union(barrios.geometry).area / 1e6, 3),
        "raw_features_with_polygon": raw_count,
        "excluded": excluded,
        "counts_used_by_tag": kept.cat.value_counts().to_dict(),
        "area_used_by_tag_ha": kept.groupby("cat").ha.sum().round(1).to_dict(),
        "scenarios": {},
    }
    _scenario(kept, "500m_todos", city, barrios, summary, layout)
    _scenario(kept[kept.ha >= MIN_HA], "500m_min05ha", city, barrios, summary, layout)
    _scenario(
        kept[kept.cat != "landuse=recreation_ground"],
        "500m_sin_recreation_ground",
        city,
        barrios,
        summary,
        layout,
    )
    write(layout.resumen, summary)
    print(dumps(summary, indent=1))
    print(f"wrote {layout.resumen}")
    return summary


def _scenario(spaces, key: str, city, barrios, summary: dict, layout: Layout) -> None:
    green_union = unary_union(spaces.geometry)
    covered_union = unary_union(spaces.geometry.buffer(BUFFER_M, quad_segs=QUAD_SEGS))
    covered = covered_union.intersection(city)
    uncovered = city.difference(covered_union)
    result = {
        "n_green": len(spaces),
        "green_area_ha": round(green_union.area / 1e4, 1),
        "covered_km2": round(covered.area / 1e6, 3),
        "covered_pct": round(100 * covered.area / city.area, 2),
        "uncovered_km2": round(uncovered.area / 1e6, 3),
        "uncovered_pct": round(100 * uncovered.area / city.area, 2),
    }
    table = barrios.copy()
    table["barrio_km2"] = table.area / 1e6
    table["uncov_km2"] = table.geometry.intersection(uncovered).area / 1e6
    table["uncov_pct"] = 100 * table.uncov_km2 / table.barrio_km2
    table = table.sort_values("uncov_km2", ascending=False)
    csv_path = layout.results / f"barrios_{key}.csv"
    table.drop(columns="geometry").round(3).to_csv(csv_path, index=False)
    result["top_barrios"] = (
        table.head(8)[["nombre", "comuna", "barrio_km2", "uncov_km2", "uncov_pct"]]
        .round(3)
        .to_dict("records")
    )
    result["uncovered_in_barrios_km2"] = round(table.uncov_km2.sum(), 3)

    patches = gpd.GeoDataFrame({"scenario": [key]}, geometry=[uncovered], crs=METRIC_CRS)
    patches = patches.explode(index_parts=False)
    patches["area_m2"] = patches.area.round(0)
    patches = patches[patches.area_m2 > 0]
    result["n_uncovered_patches"] = len(patches)
    result["n_patches_ge_1ha"] = int((patches.area_m2 >= 1e4).sum())
    patches.to_crs(4326).to_file(
        layout.interim / f"zonas_sin_cobertura_{key}.geojson", driver="GeoJSON"
    )
    gpd.GeoDataFrame({"s": [key]}, geometry=[covered], crs=METRIC_CRS).to_crs(4326).to_file(
        layout.interim / f"cobertura_{key}.geojson",
        driver="GeoJSON",
    )
    summary["scenarios"][key] = result
