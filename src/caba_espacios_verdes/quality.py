"""Vegetation quality of the green spaces, and access metrics weighted by it.

Requires the Sentinel-2 median from ``quality_composite`` and, unless skipped,
the Meta/WRI canopy-height tiles. ESA WorldCover 2021 is read remotely, by
window, and is not stored. This stage only writes new ``*_calidad`` and
``*_vegetado`` files. It checks that the coverage and population outputs it
reads were not rewritten while it ran.
"""

from __future__ import annotations

import json
import os

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize
from rasterio.merge import merge
from rasterio.windows import Window, from_bounds
from shapely.ops import unary_union

from caba_espacios_verdes.barrios import load_barrios
from caba_espacios_verdes.download import download_canopy
from caba_espacios_verdes.jsonio import write
from caba_espacios_verdes.paths import Layout, require
from caba_espacios_verdes.sources import BUFFER_M, METRIC_CRS, MIN_HA, QUAD_SEGS, WORLDCOVER_URL

T_VEG = 0.3
T_DENSE = 0.5
W_LO = 0.2
W_HI = 0.7
STEP_M = 40


def _gdal_env() -> None:
    os.environ.update(AWS_NO_SIGN_REQUEST="YES", GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR")


def _weight(values: np.ndarray) -> np.ndarray:
    return np.clip((values - W_LO) / (W_HI - W_LO), 0, 1)


def _zonal(geom, arr, transform, supersample: int):
    bounds = geom.bounds
    window = from_bounds(*bounds, transform).round_offsets(op="floor").round_lengths(op="ceil")
    row0 = max(int(window.row_off) - 1, 0)
    col0 = max(int(window.col_off) - 1, 0)
    row1 = min(int(window.row_off + window.height) + 2, arr.shape[0])
    col1 = min(int(window.col_off + window.width) + 2, arr.shape[1])
    height, width = row1 - row0, col1 - col0
    if height <= 0 or width <= 0:
        return np.array([]), np.array([])
    sub = rasterio.windows.transform(Window(col0, row0, width, height), transform)
    sub = sub * rasterio.Affine.scale(1 / supersample)
    mask = rasterize(
        [(geom, 1)],
        out_shape=(height * supersample, width * supersample),
        transform=sub,
        fill=0,
        dtype="uint8",
    )
    if supersample > 1:
        covered = mask.reshape(height, supersample, width, supersample).mean((1, 3))
    else:
        covered = mask.astype(float)
    values = arr[row0:row1, col0:col1]
    keep = (covered > 0) & np.isfinite(values)
    return values[keep], covered[keep]


def _s2_stats(geometries, ndvi, transform, crs_metric: int) -> pd.DataFrame:
    rows = []
    for geom in gpd.GeoSeries(geometries, crs=crs_metric).to_crs(32721):
        values, covered = _zonal(geom, ndvi, transform, 10)
        if covered.sum() == 0:
            rows.append([np.nan] * 5)
            continue
        rows.append(
            [
                covered.sum(),
                np.average(values, weights=covered),
                np.average(values > T_VEG, weights=covered),
                np.average(values > T_DENSE, weights=covered),
                np.average(_weight(values), weights=covered),
            ]
        )
    return pd.DataFrame(rows, columns=["n_pix", "ndvi_mean", "f_veg", "f_dense", "f_cont"])


def _weighted_quantile(values, weights, quantile: float) -> float:
    order = np.argsort(values)
    cumulative = np.cumsum(weights[order])
    return float(values[order][np.searchsorted(cumulative, quantile * cumulative[-1])])


def run(layout: Layout, *, skip_canopy: bool = False) -> dict:
    layout.ensure()
    _gdal_env()
    if not skip_canopy:
        download_canopy(layout)
    require(layout.boundary_osm, "Run `caba-espacios-verdes coverage` first.")
    require(layout.green_used, "Run `caba-espacios-verdes coverage` first.")
    require(layout.green_raw, "Run `caba-espacios-verdes coverage` first.")
    require(layout.barrios, "Run `caba-espacios-verdes download` first.")
    require(layout.radios, "Run `caba-espacios-verdes download` first.")
    require(
        layout.sentinel_tif,
        "Run `caba-espacios-verdes quality` so the Sentinel composite is built.",
    )
    require(
        layout.scenes_json, "Run `caba-espacios-verdes quality` so the Sentinel composite is built."
    )
    require(layout.resumen_poblacion, "Run `caba-espacios-verdes population` first.")

    protected = [
        layout.resumen,
        layout.resumen_poblacion,
        layout.interim / "radios_2sfca.geojson",
        layout.results / "barrios_2sfca_500m.csv",
    ]
    for path in protected:
        require(path, "Run coverage and population before quality.")
    stamps = {path: path.stat().st_mtime_ns for path in protected}

    caba = gpd.read_file(layout.boundary_osm).to_crs(METRIC_CRS)
    city = caba.geometry.iloc[0]
    barrios = load_barrios(layout.barrios).to_crs(METRIC_CRS)[["nombre", "comuna", "geometry"]]
    radios = gpd.read_file(layout.radios).to_crs(METRIC_CRS)
    radios = radios[["cro", "ncom", "p_vp", "geometry"]].rename(columns={"p_vp": "pop"})
    radios["geometry"] = radios.geometry.make_valid()
    radios["area_m2"] = radios.area
    radios["dens_ha"] = radios["pop"] / (radios.area_m2 / 1e4)
    population = int(radios["pop"].sum())
    green = gpd.read_file(layout.green_used).to_crs(METRIC_CRS).reset_index(drop=True)
    green["gid"] = green.index
    green["area_m2"] = green.area
    green["ha"] = green.area_m2 / 1e4
    raw = gpd.read_file(layout.green_raw).to_crs(METRIC_CRS)
    summary: dict = {"sentinel2": json.loads(layout.scenes_json.read_text(encoding="utf-8"))}

    with rasterio.open(layout.sentinel_tif) as src:
        red, nir, _ndvi_clip, _nobs = src.read()
        transform = src.transform
    ndvi = np.where((nir + red) > 0, (nir - red) / (nir + red), np.nan)

    stats = _s2_stats(green.geometry, ndvi, transform, METRIC_CRS)
    green = pd.concat([green, stats], axis=1)
    if not isinstance(green, gpd.GeoDataFrame):
        green = gpd.GeoDataFrame(green, geometry="geometry", crs=METRIC_CRS)

    eroded = green.geometry.buffer(-10)
    inner_geoms = [
        geom if not geom.is_empty else green.geometry.iloc[i] for i, geom in enumerate(eroded)
    ]
    inner_stats = _s2_stats(inner_geoms, ndvi, transform, METRIC_CRS)
    green["ndvi_mean_int10m"] = np.where(~eroded.is_empty, inner_stats.ndvi_mean, np.nan)
    green["f_veg_int10m"] = np.where(~eroded.is_empty, inner_stats.f_veg, np.nan)

    green_wgs = green.to_crs(4326)
    bounds = green_wgs.total_bounds + np.array([-0.01, -0.01, 0.01, 0.01])
    with rasterio.open(WORLDCOVER_URL) as src:
        window = from_bounds(*bounds, src.transform).round_offsets().round_lengths()
        worldcover = src.read(1, window=window).astype("float32")
        worldcover_transform = src.window_transform(window)
    worldcover[worldcover == 0] = np.nan
    tree_fraction = []
    grass_fraction = []
    for geom in green_wgs.geometry:
        values, covered = _zonal(geom, worldcover, worldcover_transform, 6)
        if covered.sum():
            tree_fraction.append(np.average(values == 10, weights=covered))
            grass_fraction.append(np.average(values == 30, weights=covered))
        else:
            tree_fraction.append(np.nan)
            grass_fraction.append(np.nan)
    green["wc_tree_pct"] = 100 * np.array(tree_fraction)
    green["wc_grass_pct"] = 100 * np.array(grass_fraction)

    canopy_files = [layout.chm_tile(tile_id) for tile_id in ("210321300", "210321301")]
    if all(path.exists() for path in canopy_files):
        green_web = green.to_crs(3857)
        padded = green_web.total_bounds + np.array([-50, -50, 50, 50])
        canopy, canopy_transform = merge(canopy_files, bounds=tuple(padded))
        canopy = canopy[0].astype("float32")
        above_3 = []
        above_5 = []
        for geom in green_web.geometry:
            values, covered = _zonal(geom, canopy, canopy_transform, 1)
            if covered.sum() == 0:
                values, covered = _zonal(geom.buffer(0.6), canopy, canopy_transform, 1)
            if covered.sum():
                above_3.append(np.average(values >= 3, weights=covered))
                above_5.append(np.average(values >= 5, weights=covered))
            else:
                above_3.append(np.nan)
                above_5.append(np.nan)
        green["chm_ge3m_pct"] = 100 * np.array(above_3)
        green["chm_ge5m_pct"] = 100 * np.array(above_5)
        del canopy

    points = gpd.GeoDataFrame(geometry=green.representative_point(), crs=METRIC_CRS)
    joined = gpd.sjoin(points, barrios[["nombre", "geometry"]], how="left", predicate="within")
    green["barrio"] = joined[~joined.index.duplicated()].nombre.reindex(green.index).values
    green["clase"] = np.select(
        [green.ndvi_mean < 0.3, green.ndvi_mean < 0.5],
        ["seca/dura", "intermedia"],
        "verde/arbolada",
    )
    green["veg_m2"] = green.area_m2 * green.f_veg
    green["veg_ha"] = green.veg_m2 / 1e4
    green["cont_m2"] = green.area_m2 * green.f_cont
    green["dense_m2"] = green.area_m2 * green.f_dense
    columns = [
        "osm_type",
        "osm_id",
        "name",
        "cat",
        "barrio",
        "ha",
        "n_pix",
        "ndvi_mean",
        "f_veg",
        "f_dense",
        "f_cont",
        "veg_ha",
        "clase",
        "ndvi_mean_int10m",
        "f_veg_int10m",
        "wc_tree_pct",
        "wc_grass_pct",
    ]
    columns += [column for column in ("chm_ge3m_pct", "chm_ge5m_pct") if column in green]
    green.to_crs(4326)[columns + ["geometry"]].to_file(
        layout.interim / "espacios_verdes_calidad.geojson", driver="GeoJSON"
    )
    green[columns].sort_values("ha", ascending=False).round(4).to_csv(
        layout.results / "espacios_verdes_calidad.csv", index=False
    )

    def class_summary(frame: pd.DataFrame) -> dict:
        out = {}
        for label in ("seca/dura", "intermedia", "verde/arbolada"):
            subset = frame[frame.clase == label]
            record = {
                "n": len(subset),
                "ha": round(subset.ha.sum(), 1),
                "veg_ha": round(subset.veg_ha.sum(), 1),
                "ndvi_medio": round(subset.ndvi_mean.mean(), 3),
                "wc_tree_pct_mediana": round(subset.wc_tree_pct.median(), 1),
            }
            if "chm_ge3m_pct" in subset:
                record["chm_ge3m_pct_mediana"] = round(subset.chm_ge3m_pct.median(), 1)
            out[label] = record
        return out

    large = green[green.ha >= MIN_HA]
    detail_columns = ["name", "cat", "barrio", "ha", "ndvi_mean", "f_veg", "veg_ha", "wc_tree_pct"]
    if "chm_ge3m_pct" in green:
        detail_columns.append("chm_ge3m_pct")
    interior = ~eroded.is_empty
    interior_mask = interior.to_numpy()
    full_class = np.select([green.ndvi_mean < 0.3, green.ndvi_mean < 0.5], [0, 1], 2)
    inner_class = np.select([green.ndvi_mean_int10m < 0.3, green.ndvi_mean_int10m < 0.5], [0, 1], 2)
    correlation = {
        "ndvi_vs_wc_tree": round(green[["ndvi_mean", "wc_tree_pct"]].corr().iloc[0, 1], 3)
    }
    if "chm_ge3m_pct" in green:
        correlation["ndvi_vs_chm3m"] = round(
            green[["ndvi_mean", "chm_ge3m_pct"]].corr().iloc[0, 1], 3
        )
        correlation["f_dense_vs_chm3m"] = round(
            green[["f_dense", "chm_ge3m_pct"]].corr().iloc[0, 1], 3
        )
    quality = {
        "umbrales": {
            "clases": (
                "NDVI medio del polígono: < 0,3 seca/dura; 0,3–0,5 intermedia; "
                ">= 0,5 verde/arbolada"
            ),
            "vegetado": f"NDVI > {T_VEG}",
            "denso": f"NDVI > {T_DENSE}",
            "peso_continuo": f"clip((NDVI-{W_LO})/({W_HI}-{W_LO}),0,1)",
            "zonal": "media ponderada por fracción de píxel cubierta (supermuestreo 10x, 1 m)",
        },
        "todos": {
            "n": len(green),
            "clases": class_summary(green),
            "ndvi_mediana": round(green.ndvi_mean.median(), 3),
        },
        "min05ha": {
            "n": len(large),
            "clases": class_summary(large),
            "ndvi_mediana": round(large.ndvi_mean.median(), 3),
        },
        "area_union": {"ha_raw_union_todos": round(unary_union(green.geometry).area / 1e4, 1)},
        "sensibilidad_borde_10m": {
            "n_con_interior": int(interior.sum()),
            "ndvi_medio_completo": round(green.loc[interior, "ndvi_mean"].mean(), 3),
            "ndvi_medio_interior": round(green.ndvi_mean_int10m.mean(), 3),
            "n_cambia_clase_si_interior": int(
                (inner_class[interior_mask] != full_class[interior_mask]).sum()
            ),
        },
        "por_categoria_osm": green.groupby("cat")
        .agg(
            n=("ha", "size"),
            ndvi_medio=("ndvi_mean", "mean"),
            f_veg_media=("f_veg", "mean"),
            pct_seca=("clase", lambda series: 100 * (series == "seca/dura").mean()),
        )
        .round(3)
        .reset_index()
        .to_dict("records"),
        "correlacion": correlation,
    }
    dry_large = green[(green.clase == "seca/dura") & (green.ha >= MIN_HA)].sort_values(
        "ha", ascending=False
    )
    quality["secas_grandes"] = dry_large[detail_columns].head(25).round(3).to_dict("records")
    named_dry = dry_large[dry_large.name.notna() & (dry_large.cat != "landuse=recreation_ground")]
    quality["secas_grandes_nombradas_plazas_parques"] = (
        named_dry[detail_columns].head(20).round(3).to_dict("records")
    )
    quality["mayor_perdida_ha"] = (
        green.assign(perd=green.ha - green.veg_ha)
        .sort_values("perd", ascending=False)[detail_columns + ["perd"]]
        .head(15)
        .round(3)
        .to_dict("records")
    )
    quality["mas_verdes_ge1ha"] = (
        green[green.ha >= 1]
        .sort_values("ndvi_mean", ascending=False)[detail_columns]
        .head(10)
        .round(3)
        .to_dict("records")
    )
    quality["seleccion"] = {
        "n_raw_ge05": len(large),
        "n_veg_ge05": int((green.veg_ha >= MIN_HA).sum()),
        "n_cont_ge05": int((green.cont_m2 >= 5000).sum()),
        "n_raw_ge05_que_pierden": int(((green.ha >= MIN_HA) & (green.veg_ha < MIN_HA)).sum()),
        "ha_raw_ge05": round(large.ha.sum(), 1),
        "ha_veg_de_ge05": round(large.veg_ha.sum(), 1),
    }
    summary["calidad"] = quality

    pieces = gpd.overlay(
        radios[["cro", "pop", "area_m2", "geometry"]],
        barrios,
        how="intersection",
        keep_geom_type=True,
    )
    pieces["a"] = pieces.area
    pieces["pop_piece"] = pieces["pop"] * pieces.a / pieces.groupby("cro").a.transform("sum")

    def coverage(spaces):
        covered = unary_union(spaces.geometry.buffer(BUFFER_M, quad_segs=QUAD_SEGS))
        uncovered_pop = (
            population
            - (radios["pop"] * radios.geometry.intersection(covered).area / radios.area_m2).sum()
        )
        parts = pieces.copy()
        parts["pop_unc"] = parts.pop_piece * parts.geometry.difference(covered).area / parts.a
        table = (
            parts.groupby(["nombre", "comuna"])
            .agg(pob=("pop_piece", "sum"), pob_sin_cob=("pop_unc", "sum"))
            .reset_index()
        )
        table["pct_pob_sin_cob"] = 100 * table.pob_sin_cob / table.pob
        return covered, uncovered_pop, table, 100 * city.difference(covered).area / city.area

    scenarios = {
        "raw_ge05ha_control": large,
        "vegetado_ndvi03_ge05ha": green[green.veg_ha >= MIN_HA],
        "peso_continuo_ge05ha": green[green.cont_m2 >= 5000],
        "denso_ndvi05_ge05ha": green[green.dense_m2 >= 5000],
    }
    coverage_tables = {}
    summary["cobertura_500m"] = {}
    for key, spaces in scenarios.items():
        covered, uncovered_pop, table, area_pct = coverage(spaces)
        coverage_tables[key] = (covered, table)
        summary["cobertura_500m"][key] = {
            "n_espacios": len(spaces),
            "pob_sin_cobertura": round(uncovered_pop),
            "pct_pob_sin_cobertura": round(100 * uncovered_pop / population, 2),
            "pct_area_sin_cobertura": round(area_pct, 2),
        }
    vegetated_table = coverage_tables["vegetado_ndvi03_ge05ha"][1].merge(
        coverage_tables["raw_ge05ha_control"][1][["nombre", "pob_sin_cob", "pct_pob_sin_cob"]],
        on="nombre",
        suffixes=("", "_raw"),
    )
    vegetated_table["dif_pob"] = vegetated_table.pob_sin_cob - vegetated_table.pob_sin_cob_raw
    vegetated_table = vegetated_table.sort_values("pob_sin_cob", ascending=False)
    vegetated_table.round(2).to_csv(
        layout.results / "barrios_poblacion_500m_vegetado05ha.csv", index=False
    )
    summary["cobertura_500m"]["top_barrios_vegetado"] = (
        vegetated_table.head(10).round(1).to_dict("records")
    )
    summary["cobertura_500m"]["barrios_mas_empeoran"] = (
        vegetated_table.sort_values("dif_pob", ascending=False).head(8).round(1).to_dict("records")
    )
    new_covered = coverage_tables["vegetado_ndvi03_ge05ha"][0]
    old_covered = coverage_tables["raw_ge05ha_control"][0]
    gpd.GeoDataFrame(geometry=[city.difference(new_covered)], crs=METRIC_CRS).to_crs(4326).to_file(
        layout.interim / "zonas_sin_cobertura_500m_vegetado05ha.geojson", driver="GeoJSON"
    )
    gpd.GeoDataFrame(
        geometry=[city.intersection(old_covered).difference(new_covered)], crs=METRIC_CRS
    ).to_crs(4326).to_file(
        layout.interim / "zonas_pierden_cobertura_por_calidad.geojson", driver="GeoJSON"
    )

    non_residential = unary_union(raw.geometry.buffer(0))
    xmin, ymin, xmax, ymax = radios.total_bounds
    xs, ys = np.meshgrid(
        np.arange(xmin + STEP_M / 2, xmax, STEP_M),
        np.arange(ymin + STEP_M / 2, ymax, STEP_M),
    )
    points = gpd.GeoDataFrame(geometry=gpd.points_from_xy(xs.ravel(), ys.ravel()), crs=METRIC_CRS)
    habitable = radios[["cro", "geometry"]].copy()
    habitable["geometry"] = habitable.geometry.difference(non_residential)
    points = gpd.sjoin(points, habitable[~habitable.is_empty], predicate="within", how="inner")[
        ["cro", "geometry"]
    ]
    missing = set(radios.cro) - set(points.cro)
    extra = radios[radios.cro.isin(missing)].copy()
    extra["geometry"] = extra.geometry.representative_point()
    points = pd.concat([points, extra[["cro", "geometry"]]], ignore_index=True).merge(
        radios[["cro", "pop"]], on="cro"
    )
    points["w"] = points["pop"] / points.groupby("cro").cro.transform("size")
    points = gpd.GeoDataFrame(points, geometry="geometry", crs=METRIC_CRS).reset_index(drop=True)
    points["pid"] = points.index
    point_barrio = (
        gpd.sjoin(
            points[["pid", "geometry"]],
            barrios[["nombre", "geometry"]],
            predicate="within",
            how="left",
        )
        .drop_duplicates("pid")
        .set_index("pid")
    )
    points["barrio"] = point_barrio.reindex(points.pid)["nombre"].values
    weights = points.w.values

    def units(spaces):
        dissolved = gpd.GeoDataFrame(geometry=[unary_union(spaces.geometry)], crs=METRIC_CRS)
        dissolved = dissolved.explode(index_parts=False).reset_index(drop=True)
        dissolved["area_m2"] = dissolved.area
        dissolved["park_id"] = dissolved.index
        names = gpd.sjoin(
            dissolved, spaces[["name", "ha", "geometry"]], predicate="intersects"
        ).sort_values("ha", ascending=False)
        dissolved["name"] = dissolved.park_id.map(
            names.drop_duplicates("park_id").set_index("park_id")["name"]
        )
        zonal = _s2_stats(dissolved.geometry, ndvi, transform, METRIC_CRS)
        dissolved["veg_m2"] = dissolved.area_m2 * zonal.f_veg.values
        dissolved["cont_m2"] = dissolved.area_m2 * zonal.f_cont.values
        dissolved["ndvi_mean"] = zonal.ndvi_mean.values
        return dissolved

    def two_sfca(park_units, column: str, distance: float = BUFFER_M):
        catchments = gpd.GeoDataFrame(
            park_units[["park_id", column]].copy(),
            geometry=park_units.geometry.buffer(distance, quad_segs=QUAD_SEGS),
            crs=METRIC_CRS,
        )
        joined = gpd.sjoin(points[["pid", "w", "geometry"]], catchments, predicate="within")[
            ["pid", "w", "park_id", column]
        ]
        catchment_pop = joined.groupby("park_id").w.sum()
        ratio = park_units.set_index("park_id")[column] / catchment_pop
        joined["R"] = joined.park_id.map(ratio)
        access = joined.groupby("pid").R.sum().reindex(points.pid).fillna(0).values
        return access, ratio, catchment_pop

    def access_stats(access) -> dict:
        return {
            "mediana_m2hab_residentes": round(_weighted_quantile(access, weights, 0.5), 2),
            "p25": round(_weighted_quantile(access, weights, 0.25), 2),
            "p75": round(_weighted_quantile(access, weights, 0.75), 2),
            "media_ponderada_m2hab": round(float((access * weights).sum() / weights.sum()), 2),
            "pct_pob_0": round(100 * weights[access == 0].sum() / population, 2),
            "pct_pob_lt1": round(100 * weights[access < 1].sum() / population, 2),
            "pct_pob_lt3": round(100 * weights[access < 3].sum() / population, 2),
            "pct_pob_lt9": round(100 * weights[access < 9].sum() / population, 2),
        }

    raw_units = units(large)
    vegetated_units = units(green[green.veg_ha >= MIN_HA])
    runs = {
        "raw_control": (raw_units, "area_m2"),
        "vegetado_mismas_unidades": (raw_units, "veg_m2"),
        "vegetado_unidades_veg_ge05ha": (vegetated_units, "veg_m2"),
        "peso_continuo_mismas_unidades": (raw_units, "cont_m2"),
    }
    two_sfca_summary = {
        "metodo": (
            "Idéntico a population.py (puntos de grilla 40 m, cuenca binaria 500 m desde el "
            "perímetro) cambiando la oferta: raw = área del polígono-unidad; vegetado = área "
            "de la unidad x fracción de píxeles NDVI>0,3; peso continuo = área x media de "
            'clip((NDVI-0,2)/0,5,0,1). "mismas_unidades" = las 404 unidades de espacios '
            '>= 0,5 ha brutos; "unidades_veg_ge05ha" = unión de polígonos cuya área '
            "vegetada >= 0,5 ha."
        ),
        "n_puntos": len(points),
        "n_unidades_raw": len(raw_units),
        "n_unidades_veg": len(vegetated_units),
        "ha_unidades_raw": round(raw_units.area_m2.sum() / 1e4, 1),
        "ha_vegetadas_unidades_raw": round(raw_units.veg_m2.sum() / 1e4, 1),
        "ha_vegetadas_unidades_veg": round(vegetated_units.veg_m2.sum() / 1e4, 1),
    }
    access_values = {}
    for key, (park_units, column) in runs.items():
        access, ratio, catchment_pop = two_sfca(park_units, column)
        access_values[key] = access
        two_sfca_summary[key] = access_stats(access)
        indexed = park_units.set_index("park_id")
        two_sfca_summary[key]["parques_mas_presionados"] = (
            pd.DataFrame(
                {
                    "name": indexed.name,
                    "ha": indexed.area_m2 / 1e4,
                    "veg_ha": indexed.veg_m2 / 1e4,
                    "pob_cuenca": catchment_pop,
                    "m2_por_hab_cuenca": ratio,
                }
            )
            .dropna(subset=["pob_cuenca"])
            .query("ha >= 1")
            .sort_values("m2_por_hab_cuenca")
            .head(5)
            .round(2)
            .to_dict("records")
        )
    raw_access = access_values["raw_control"]
    vegetated_access = access_values["vegetado_mismas_unidades"]
    points["A_raw"] = raw_access
    points["A_veg"] = vegetated_access
    by_barrio = (
        points.assign(
            wr=weights * raw_access,
            wv=weights * vegetated_access,
            l1=weights * (vegetated_access < 1),
            l9=weights * (vegetated_access < 9),
        )
        .groupby("barrio")
        .agg(
            pob=("w", "sum"), wr=("wr", "sum"), wv=("wv", "sum"), l1=("l1", "sum"), l9=("l9", "sum")
        )
    )
    by_barrio["m2hab_raw"] = by_barrio.wr / by_barrio.pob
    by_barrio["m2hab_veg"] = by_barrio.wv / by_barrio.pob
    by_barrio["ratio_veg_raw"] = by_barrio.m2hab_veg / by_barrio.m2hab_raw
    by_barrio["pct_pob_lt1_veg"] = 100 * by_barrio.l1 / by_barrio.pob
    by_barrio["pct_pob_lt9_veg"] = 100 * by_barrio.l9 / by_barrio.pob
    by_barrio = by_barrio.drop(columns=["wr", "wv", "l1", "l9"]).sort_values("m2hab_veg")
    by_barrio.round(3).to_csv(layout.results / "barrios_2sfca_vegetado_500m.csv")
    two_sfca_summary["peores_barrios_vegetado"] = (
        by_barrio.head(10).reset_index().round(2).to_dict("records")
    )
    two_sfca_summary["mejores_barrios_vegetado"] = (
        by_barrio.tail(5).reset_index().round(2).to_dict("records")
    )
    two_sfca_summary["barrios_mayor_perdida_relativa"] = (
        by_barrio[by_barrio.m2hab_raw > 0.5]
        .sort_values("ratio_veg_raw")
        .head(8)
        .reset_index()
        .round(3)
        .to_dict("records")
    )
    two_sfca_summary["ratio_ciudad_veg_raw_media"] = round(
        float((vegetated_access * weights).sum() / (raw_access * weights).sum()), 3
    )
    radio_out = radios[["cro", "ncom", "pop", "dens_ha", "geometry"]].copy()
    radio_out["m2hab_raw_500"] = points.groupby("cro").A_raw.mean().reindex(radio_out.cro).values
    radio_out["m2hab_veg_500"] = points.groupby("cro").A_veg.mean().reindex(radio_out.cro).values
    density_bins = [0, 150, 350, np.inf]
    access_bins = [-np.inf, 1, 3, np.inf]
    radio_out["cl_dens"] = pd.cut(radio_out.dens_ha, density_bins, right=False, labels=False)
    radio_out["cl_acc"] = pd.cut(radio_out.m2hab_veg_500, access_bins, right=False, labels=False)
    counts = radio_out.pivot_table(
        index="cl_dens", columns="cl_acc", values="pop", aggfunc="sum", fill_value=0
    )
    two_sfca_summary["brecha_bivariada"] = {
        "clases_densidad_hab_ha": ["< 150", "150–350", ">= 350"],
        "clases_m2veg_hab": ["< 1", "1–3", ">= 3"],
        "pob_por_celda": {
            f"dens{i}_acc{j}": round(float(counts.loc[i, j]))
            for i in counts.index
            for j in counts.columns
        },
        "pob_alta_densidad_menos1m2": round(float(counts.loc[2, 0])),
        "pct_pob_alta_densidad_menos1m2": round(100 * float(counts.loc[2, 0]) / population, 2),
        "pob_dens_ge150_menos1m2": round(float(counts.loc[[1, 2], 0].sum())),
        "pct_pob_dens_ge150_menos1m2": round(
            100 * float(counts.loc[[1, 2], 0].sum()) / population, 2
        ),
    }
    radio_points = gpd.GeoDataFrame(
        radio_out[["pop", "cl_dens", "cl_acc"]],
        geometry=radio_out.representative_point(),
        crs=METRIC_CRS,
    )
    radio_barrio = gpd.sjoin(
        radio_points, barrios[["nombre", "geometry"]], how="left", predicate="within"
    )
    high_density_gap = radio_barrio[(radio_barrio.cl_dens == 2) & (radio_barrio.cl_acc == 0)]
    two_sfca_summary["brecha_bivariada"]["barrios_mas_pob_alta_dens_menos1m2"] = (
        high_density_gap.groupby("nombre")["pop"]
        .sum()
        .sort_values(ascending=False)
        .head(10)
        .round()
        .to_dict()
    )
    radio_out.to_crs(4326).to_file(
        layout.interim / "radios_2sfca_vegetado.geojson", driver="GeoJSON"
    )
    raw_units.to_crs(4326).to_file(
        layout.interim / "unidades_parque_calidad.geojson", driver="GeoJSON"
    )
    summary["2sfca_500m"] = two_sfca_summary

    published = json.loads(layout.resumen_poblacion.read_text(encoding="utf-8"))
    published_500 = published["2sfca"]["500m"]
    coverage_summary = summary["cobertura_500m"]
    summary["comparacion"] = {
        "pct_pob_sin_cobertura_500m": {
            "raw_publicado": published["scenarios"]["500m_min05ha"]["pct_pob_sin_cobertura"],
            "raw_recalculado": coverage_summary["raw_ge05ha_control"]["pct_pob_sin_cobertura"],
            "vegetado_ndvi03": coverage_summary["vegetado_ndvi03_ge05ha"]["pct_pob_sin_cobertura"],
            "peso_continuo": coverage_summary["peso_continuo_ge05ha"]["pct_pob_sin_cobertura"],
            "denso_ndvi05": coverage_summary["denso_ndvi05_ge05ha"]["pct_pob_sin_cobertura"],
        },
        "mediana_m2hab_2sfca500": {
            "raw_publicado": published_500["mediana_m2hab_residentes"],
            "raw_recalculado": two_sfca_summary["raw_control"]["mediana_m2hab_residentes"],
            "vegetado": two_sfca_summary["vegetado_mismas_unidades"]["mediana_m2hab_residentes"],
            "vegetado_unidades_veg": two_sfca_summary["vegetado_unidades_veg_ge05ha"][
                "mediana_m2hab_residentes"
            ],
            "peso_continuo": two_sfca_summary["peso_continuo_mismas_unidades"][
                "mediana_m2hab_residentes"
            ],
        },
        "pct_pob_lt1": {
            "raw_publicado": published_500["pct_pob_lt1"],
            "raw_recalculado": two_sfca_summary["raw_control"]["pct_pob_lt1"],
            "vegetado": two_sfca_summary["vegetado_mismas_unidades"]["pct_pob_lt1"],
            "vegetado_unidades_veg": two_sfca_summary["vegetado_unidades_veg_ge05ha"][
                "pct_pob_lt1"
            ],
            "peso_continuo": two_sfca_summary["peso_continuo_mismas_unidades"]["pct_pob_lt1"],
        },
        "pct_pob_lt9": {
            "raw_publicado": published_500["pct_pob_lt9"],
            "raw_recalculado": two_sfca_summary["raw_control"]["pct_pob_lt9"],
            "vegetado": two_sfca_summary["vegetado_mismas_unidades"]["pct_pob_lt9"],
            "vegetado_unidades_veg": two_sfca_summary["vegetado_unidades_veg_ge05ha"][
                "pct_pob_lt9"
            ],
            "peso_continuo": two_sfca_summary["peso_continuo_mismas_unidades"]["pct_pob_lt9"],
        },
    }
    summary["fuentes_copa"] = {
        "esa_worldcover": WORLDCOVER_URL + " (v200, 2021, clase 10 = tree cover; 10 m)",
        "meta_wri_chm": (
            "https://dataforgood-fb-data.s3.amazonaws.com/forests/v1/alsgedi_global_v6_float/"
            "chm/{210321300,210321301}.tif (Meta & WRI, High Resolution Canopy Height Maps v1, "
            "~1 m, imágenes Maxar mayormente 2009-2020; % píxeles >= 3 m y >= 5 m)"
        ),
    }
    for path, stamp in stamps.items():
        if path.stat().st_mtime_ns != stamp:
            raise RuntimeError(f"{path} was modified while quality metrics were computed")
    write(layout.resumen_calidad, summary)
    print(f"wrote {layout.resumen_calidad}")
    return summary
