"""Population (Censo 2022, radios censales) x green-space coverage, plus 2SFCA.

Population source: IDECBA / IECBA (GCBA), WFS layer
``geonube:total_pob_vivp_radio_censal2022`` (INDEC, CNPHyV 2022, definitive
results; ``p_vp`` is population in private dwellings).

Supply in the 2SFCA is the area of each park unit (overlapping or touching
spaces of at least 0.5 ha, dissolved). Demand is a 40 m grid of population
points placed on the residential part of each radio (the radio minus OSM
green space), with the radio's population split equally across its points.
``R_j`` is park area divided by the population within ``d`` metres of the
perimeter. ``A_i`` sums the ``R_j`` of every park within ``d`` metres.
"""

from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.ops import unary_union

from caba_espacios_verdes.barrios import load_barrios
from caba_espacios_verdes.jsonio import dumps, write
from caba_espacios_verdes.paths import Layout, require
from caba_espacios_verdes.sources import (
    BUFFER_M,
    CENSUS_VISOR_URL,
    METRIC_CRS,
    MIN_HA,
    QUAD_SEGS,
    WFS_LAYER,
    WFS_URL,
)

CABA_TOTAL_2022 = 3_121_707
COLECTIVAS = 23_850
VIA_PUBLICA = 2_403
STEP_M = 40


def run(layout: Layout) -> dict:
    layout.ensure()
    require(layout.boundary_osm, "Run `caba-espacios-verdes coverage` first.")
    require(layout.green_used, "Run `caba-espacios-verdes coverage` first.")
    require(layout.green_raw, "Run `caba-espacios-verdes coverage` first.")
    require(layout.barrios, "Run `caba-espacios-verdes download` first.")
    require(layout.radios, "Run `caba-espacios-verdes download` first.")
    require(layout.resumen, "Run `caba-espacios-verdes coverage` first.")

    caba = gpd.read_file(layout.boundary_osm).to_crs(METRIC_CRS)
    city = caba.geometry.iloc[0]
    barrios = load_barrios(layout.barrios).to_crs(METRIC_CRS)[["nombre", "comuna", "geometry"]]
    radios = gpd.read_file(layout.radios).to_crs(METRIC_CRS)
    radios = radios[["cro", "ncom", "p_vp", "hog", "vp", "geometry"]].rename(
        columns={"p_vp": "pop"}
    )
    radios["geometry"] = radios.geometry.make_valid()
    radios["area_m2"] = radios.area
    radios["dens_ha"] = radios["pop"] / (radios.area_m2 / 1e4)
    population = int(radios["pop"].sum())

    green = gpd.read_file(layout.green_used).to_crs(METRIC_CRS)
    green["ha"] = green.area / 1e4
    raw = gpd.read_file(layout.green_raw).to_crs(METRIC_CRS)
    large = green[green.ha >= MIN_HA]
    summary: dict = {
        "fuente_poblacion": {
            "dataset": (
                "Total de población en viviendas particulares por radio censal. "
                "CNPHyV 2022. Resultados definitivos"
            ),
            "capa_wfs": WFS_LAYER,
            "url": WFS_URL,
            "visor": CENSUS_VISOR_URL,
            "productor": "INDEC (Censo 2022) / IECBA-GCBA (IDECBA)",
            "anio": 2022,
            "n_radios": len(radios),
            "poblacion_viviendas_particulares": population,
            "poblacion_total_publicada_2022": CABA_TOTAL_2022,
            "verificacion": (
                f"{CABA_TOTAL_2022} - {COLECTIVAS} (viv. colectivas) - {VIA_PUBLICA} "
                f"(vía pública) = {CABA_TOTAL_2022 - COLECTIVAS - VIA_PUBLICA}; "
                f"suma radios = {population}"
            ),
            "area_radios_km2": round(radios.area_m2.sum() / 1e6, 3),
            "densidad_media_hab_ha": round(population / (radios.area_m2.sum() / 1e4), 1),
        },
        "scenarios": {},
    }

    pieces = gpd.overlay(
        radios[["cro", "pop", "area_m2", "geometry"]],
        barrios,
        how="intersection",
        keep_geom_type=True,
    )
    pieces["a"] = pieces.area
    pieces["pop_piece"] = pieces["pop"] * pieces.a / pieces.groupby("cro").a.transform("sum")
    population_by_barrio = pieces.groupby("nombre").pop_piece.sum()

    def coverage(spaces, key: str):
        covered = unary_union(spaces.geometry.buffer(BUFFER_M, quad_segs=QUAD_SEGS))
        weighted = radios.copy()
        weighted["pop_cov"] = (
            weighted["pop"] * weighted.geometry.intersection(covered).area / weighted.area_m2
        )
        uncovered_pop = population - weighted.pop_cov.sum()
        parts = pieces.copy()
        parts["pop_unc"] = parts.pop_piece * parts.geometry.difference(covered).area / parts.a
        table = (
            parts.groupby(["nombre", "comuna"])
            .agg(pob=("pop_piece", "sum"), pob_sin_cob=("pop_unc", "sum"))
            .reset_index()
        )
        table["pct_pob_sin_cob"] = 100 * table.pob_sin_cob / table.pob
        area_csv = pd.read_csv(layout.results / f"barrios_{key}.csv")[
            ["nombre", "uncov_pct"]
        ].rename(columns={"uncov_pct": "pct_area_sin_cob"})
        table = table.merge(area_csv, on="nombre", how="left").sort_values(
            "pob_sin_cob", ascending=False
        )
        table.round(2).to_csv(layout.results / f"barrios_poblacion_{key}.csv", index=False)
        area_pct = json.loads(layout.resumen.read_text(encoding="utf-8"))["scenarios"][key][
            "uncovered_pct"
        ]
        result = {
            "n_green": len(spaces),
            "pob_cubierta": round(population - uncovered_pop),
            "pob_sin_cobertura": round(uncovered_pop),
            "pct_pob_sin_cobertura": round(100 * uncovered_pop / population, 2),
            "pct_area_sin_cobertura": area_pct,
            "top_barrios": table.head(10)[
                ["nombre", "comuna", "pob", "pob_sin_cob", "pct_pob_sin_cob", "pct_area_sin_cob"]
            ]
            .round(1)
            .to_dict("records"),
        }
        non_residential = unary_union(raw.geometry.buffer(0))
        habitable = weighted.geometry.difference(non_residential)
        habitable_area = habitable.area
        covered_habitable = habitable.intersection(covered).area
        fraction = np.where(
            habitable_area > 1,
            covered_habitable / np.maximum(habitable_area, 1),
            weighted.pop_cov / weighted["pop"].clip(lower=1e-9),
        )
        result["sensibilidad_dasimetrica_pct_pob_sin_cobertura"] = round(
            100 * (1 - (weighted["pop"] * fraction).sum() / population), 2
        )
        summary["scenarios"][key] = result
        return covered

    covered_large = coverage(large, "500m_min05ha")
    coverage(green, "500m_todos")

    uncovered_radios = radios[["cro", "pop", "dens_ha", "geometry"]].copy()
    uncovered_radios["geometry"] = uncovered_radios.geometry.difference(covered_large)
    uncovered_radios = uncovered_radios[~uncovered_radios.is_empty & (uncovered_radios.area > 1)]
    uncovered_radios["pop_unc"] = uncovered_radios["dens_ha"] * uncovered_radios.area / 1e4
    uncovered_radios.to_crs(4326).to_file(
        layout.interim / "radios_sin_cobertura_05ha.geojson", driver="GeoJSON"
    )
    summary["scenarios"]["500m_min05ha"]["pob_sin_cob_en_radios_dens_ge_300_hab_ha"] = round(
        uncovered_radios.loc[uncovered_radios.dens_ha >= 300, "pop_unc"].sum()
    )

    non_residential = unary_union(raw.geometry.buffer(0))
    xmin, ymin, xmax, ymax = radios.total_bounds
    xs, ys = np.meshgrid(
        np.arange(xmin + STEP_M / 2, xmax, STEP_M),
        np.arange(ymin + STEP_M / 2, ymax, STEP_M),
    )
    points = gpd.GeoDataFrame(geometry=gpd.points_from_xy(xs.ravel(), ys.ravel()), crs=METRIC_CRS)
    habitable_radios = radios[["cro", "geometry"]].copy()
    habitable_radios["geometry"] = habitable_radios.geometry.difference(non_residential)
    points = gpd.sjoin(
        points, habitable_radios[~habitable_radios.is_empty], predicate="within", how="inner"
    )[["cro", "geometry"]]
    missing = set(radios.cro) - set(points.cro)
    extra = radios[radios.cro.isin(missing)].copy()
    extra["geometry"] = extra.geometry.representative_point()
    points = pd.concat([points, extra[["cro", "geometry"]]], ignore_index=True)
    points = points.merge(radios[["cro", "pop"]], on="cro")
    points["w"] = points["pop"] / points.groupby("cro").cro.transform("size")
    points = gpd.GeoDataFrame(points, geometry="geometry", crs=METRIC_CRS).reset_index(drop=True)
    points["pid"] = points.index
    if abs(points.w.sum() - population) >= 1:
        raise RuntimeError("Population points do not sum to the census population.")

    parks = gpd.GeoDataFrame(geometry=[unary_union(large.geometry)], crs=METRIC_CRS)
    parks = parks.explode(index_parts=False).reset_index(drop=True)
    parks["area_m2"] = parks.area
    parks["park_id"] = parks.index
    names = gpd.sjoin(parks, large[["name", "ha", "geometry"]], predicate="intersects").sort_values(
        "ha", ascending=False
    )
    parks["name"] = parks.park_id.map(names.drop_duplicates("park_id").set_index("park_id")["name"])

    def two_sfca(distance: float):
        catchments = parks[["park_id", "area_m2"]].copy()
        catchments["geometry"] = parks.geometry.buffer(distance, quad_segs=QUAD_SEGS)
        catchments = gpd.GeoDataFrame(catchments, geometry="geometry", crs=METRIC_CRS)
        joined = gpd.sjoin(points[["pid", "w", "geometry"]], catchments, predicate="within")[
            ["pid", "w", "park_id", "area_m2"]
        ]
        catchment_pop = joined.groupby("park_id").w.sum()
        ratio = parks.set_index("park_id").area_m2 / catchment_pop
        joined["R"] = joined.park_id.map(ratio)
        access = joined.groupby("pid").R.sum().reindex(points.pid).fillna(0).values
        return access, ratio, catchment_pop

    def weighted_quantile(values, weights, quantile: float) -> float:
        order = np.argsort(values)
        cumulative = np.cumsum(weights[order])
        return float(values[order][np.searchsorted(cumulative, quantile * cumulative[-1])])

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
    radio_out = radios[["cro", "ncom", "pop", "dens_ha", "geometry"]].copy()
    summary["2sfca"] = {
        "metodo": (
            "Puntos de población: grilla 40 m sobre cada radio menos espacios verdes OSM, "
            "población del radio repartida en partes iguales. Oferta: unidades de parque = "
            "unión de espacios verdes >=0,5 ha (polígonos solapados/contiguos fusionados). "
            "Paso 1: R_j = área_j / población a <= d del perímetro. "
            "Paso 2: A_i = suma de R_j alcanzables a <= d."
        ),
        "n_puntos": len(points),
        "n_parques_unidades": len(parks),
        "area_parques_ha": round(parks.area_m2.sum() / 1e4, 1),
    }
    weights = points.w.values
    for distance in (BUFFER_M, 1000):
        access, ratio, catchment_pop = two_sfca(distance)
        points[f"A{distance}"] = access
        radio_out[f"m2hab_{distance}"] = (
            points.groupby("cro")[f"A{distance}"].mean().reindex(radio_out.cro).values
        )
        by_barrio = (
            points.assign(wa=weights * access)
            .groupby("barrio")
            .agg(pob=("w", "sum"), wa=("wa", "sum"))
        )
        by_barrio["m2hab_2sfca"] = by_barrio.wa / by_barrio.pob
        by_barrio["pct_pob_lt1"] = (
            points.assign(x=weights * (access < 1)).groupby("barrio").x.sum() / by_barrio.pob * 100
        )
        by_barrio["pct_pob_lt9"] = (
            points.assign(x=weights * (access < 9)).groupby("barrio").x.sum() / by_barrio.pob * 100
        )
        by_barrio = by_barrio.drop(columns="wa").sort_values("m2hab_2sfca")
        by_barrio.round(2).to_csv(layout.results / f"barrios_2sfca_{distance}m.csv")
        served = parks.set_index("park_id").area_m2[catchment_pop.index].sum()
        summary["2sfca"][f"{distance}m"] = {
            "mediana_m2hab_residentes": round(weighted_quantile(access, weights, 0.5), 2),
            "p25": round(weighted_quantile(access, weights, 0.25), 2),
            "p75": round(weighted_quantile(access, weights, 0.75), 2),
            "media_ponderada_m2hab": round(float((access * weights).sum() / weights.sum()), 2),
            "control_conservacion": (
                f"sum(P_i*A_i)={(access * weights).sum() / 1e4:.1f} ha vs área de parques "
                f"con población en cuenca={served / 1e4:.1f} ha"
            ),
            "mediana_radios": round(float(np.nanmedian(radio_out[f"m2hab_{distance}"])), 2),
            "pct_pob_0": round(100 * weights[access == 0].sum() / population, 2),
            "pct_pob_lt1": round(100 * weights[access < 1].sum() / population, 2),
            "pct_pob_lt3": round(100 * weights[access < 3].sum() / population, 2),
            "pct_pob_lt9": round(100 * weights[access < 9].sum() / population, 2),
            "peores_barrios": by_barrio.head(8).reset_index().round(2).to_dict("records"),
            "mejores_barrios": by_barrio.tail(5).reset_index().round(2).to_dict("records"),
        }
        pressured = pd.DataFrame(
            {
                "name": parks.set_index("park_id").name,
                "ha": parks.set_index("park_id").area_m2 / 1e4,
                "pob_cuenca": catchment_pop,
                "m2_por_hab_cuenca": ratio,
            }
        )
        summary["2sfca"][f"{distance}m"]["parques_mas_presionados"] = (
            pressured.dropna(subset=["pob_cuenca"])
            .query("ha >= 1")
            .sort_values("m2_por_hab_cuenca")
            .head(5)
            .round(2)
            .to_dict("records")
        )
    radio_out.to_crs(4326).to_file(layout.interim / "radios_2sfca.geojson", driver="GeoJSON")

    all_green = unary_union(green.geometry)
    large_green = unary_union(large.geometry)
    supply = barrios.copy()
    supply["pob"] = supply.nombre.map(population_by_barrio)
    supply["m2_verde_todos"] = supply.geometry.intersection(all_green).area
    supply["m2_verde_05ha"] = supply.geometry.intersection(large_green).area
    supply["m2hab_todos"] = supply.m2_verde_todos / supply.pob
    supply["m2hab_05ha"] = supply.m2_verde_05ha / supply.pob
    supply = supply.drop(columns="geometry").sort_values("m2hab_todos")
    supply.round(2).to_csv(layout.results / "barrios_m2_verde_por_habitante.csv", index=False)
    summary["m2_verde_por_hab_barrio"] = {
        "ciudad_todos": round(all_green.intersection(city).area / population, 2),
        "ciudad_05ha": round(large_green.intersection(city).area / population, 2),
        "barrios_lt9_todos": int((supply.m2hab_todos < 9).sum()),
        "pob_en_barrios_lt9": round(supply.loc[supply.m2hab_todos < 9, "pob"].sum()),
        "peores": supply.head(8)[["nombre", "comuna", "pob", "m2hab_todos", "m2hab_05ha"]]
        .round(2)
        .to_dict("records"),
        "mejores": supply.tail(5)[["nombre", "comuna", "pob", "m2hab_todos", "m2hab_05ha"]]
        .round(2)
        .to_dict("records"),
    }
    summary["referencia_9m2"] = (
        "Valor de 9 m²/hab citado con frecuencia y atribuido a la OMS; no es una norma "
        "formal de la OMS. Se usa sólo como referencia."
    )
    write(layout.resumen_poblacion, summary)
    print(dumps(summary, indent=1))
    print(f"wrote {layout.resumen_poblacion}")
    return summary
