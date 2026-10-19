"""Population maps: people beyond 500 m, and 2SFCA square metres per resident."""

from __future__ import annotations

import json

import contextily as cx
import geopandas as gpd
import matplotlib
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

from caba_espacios_verdes.paths import Layout, require

matplotlib.use("Agg")

SOURCE = (
    "Población: INDEC, Censo 2022 (res. definitivos), pob. en viviendas particulares "
    "por radio censal, vía IDECBA/IECBA-GCBA (WFS).\n"
    "Espacios verdes: © colaboradores de OpenStreetMap (ODbL), Overpass 2026-10-18; "
    "barrios: GCBA datos abiertos. "
)
LEGEND = {"loc": "upper left", "bbox_to_anchor": (1.01, 0.98)}


def _comma(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def run(layout: Layout) -> None:
    layout.ensure()
    require(layout.resumen_poblacion, "Run `caba-espacios-verdes population` first.")
    require(layout.boundary_osm, "Run `caba-espacios-verdes coverage` first.")
    require(layout.barrios, "Run `caba-espacios-verdes download` first.")
    require(layout.green_used, "Run `caba-espacios-verdes coverage` first.")
    require(
        layout.interim / "radios_sin_cobertura_05ha.geojson",
        "Run `caba-espacios-verdes population` first.",
    )
    require(layout.interim / "radios_2sfca.geojson", "Run `caba-espacios-verdes population` first.")

    summary = json.loads(layout.resumen_poblacion.read_text(encoding="utf-8"))
    caba = gpd.read_file(layout.boundary_osm).to_crs(3857)
    barrios = gpd.read_file(layout.barrios).to_crs(3857)
    green = gpd.read_file(layout.green_used).to_crs(3857)
    green["ha"] = green.to_crs(5347).area / 1e4
    large = green[green.ha >= 0.5]
    covered = gpd.read_file(layout.interim / "cobertura_500m_min05ha.geojson").to_crs(3857)

    def base(ax, title: str) -> str:
        barrios.boundary.plot(ax=ax, color="#555555", lw=0.35, zorder=6)
        caba.boundary.plot(ax=ax, color="black", lw=1.2, zorder=7)
        try:
            cx.add_basemap(ax, source=cx.providers.Esri.WorldGrayCanvas, zoom=13, attribution=False)
            basemap = "Esri World Gray Canvas"
        except Exception as exc:
            print("basemap failed", exc)
            basemap = "sin mapa base"
        ax.set_axis_off()
        ax.set_title(title, fontsize=15, weight="bold")
        return basemap

    def foot(ax, text: str) -> None:
        ax.text(
            0.01,
            0.01,
            text,
            transform=ax.transAxes,
            fontsize=6.5,
            va="bottom",
            bbox={"fc": "white", "alpha": 0.85, "lw": 0},
        )

    uncovered = gpd.read_file(layout.interim / "radios_sin_cobertura_05ha.geojson").to_crs(3857)
    bins = [0, 100, 200, 300, 500, np.inf]
    labels = ["< 100", "100–200", "200–300", "300–500", "≥ 500"]
    colors = ["#fee5d9", "#fcae91", "#fb6a4a", "#de2d26", "#7a0177"]
    uncovered["cl"] = pd.cut(uncovered.dens_ha, bins, right=False, labels=False)
    scenario = summary["scenarios"]["500m_min05ha"]
    fig, ax = plt.subplots(figsize=(10, 10.5), dpi=260)
    covered.plot(ax=ax, color="#a6dba0", alpha=0.35, lw=0, zorder=2)
    for index, color in enumerate(colors):
        uncovered[uncovered.cl == index].plot(ax=ax, color=color, alpha=0.9, lw=0, zorder=3)
    large.plot(ax=ax, color="#1b7837", lw=0, zorder=4)
    basemap = base(ax, "CABA: población a más de 500 m de un espacio verde ≥ 0,5 ha")
    pop_by_class = uncovered.groupby("cl").pop_unc.sum()
    handles = [
        mpatches.Patch(
            color=colors[index],
            label=(
                f"{labels[index]} hab/ha  "
                f"({pop_by_class.get(index, 0) / 1e3:,.0f} mil hab.)".replace(",", ".")
            ),
        )
        for index in range(5)
    ]
    handles = [
        mpatches.Patch(color="white", label="Densidad del radio en zona > 500 m:"),
        *handles,
        mpatches.Patch(color="#a6dba0", alpha=0.6, label="A ≤ 500 m de un espacio ≥ 0,5 ha"),
        mpatches.Patch(
            color="#1b7837", label=f"Espacios verdes ≥ 0,5 ha (n={scenario['n_green']})"
        ),
        Line2D([0], [0], color="#555", lw=0.8, label="Barrios (GCBA)"),
        Line2D([0], [0], color="k", lw=1.5, label="Límite CABA (OSM)"),
    ]
    ax.legend(
        handles=handles,
        **LEGEND,
        fontsize=8.5,
        framealpha=0.92,
        title=(
            f"{scenario['pob_sin_cobertura'] / 1e3:.0f} mil hab. sin cobertura "
            f"({_comma(scenario['pct_pob_sin_cobertura'])}% de la población;\n"
            f"{_comma(scenario['pct_area_sin_cobertura'])}% de la superficie)"
        ),
        title_fontsize=8.5,
    )
    foot(
        ax,
        SOURCE + f"Mapa base: {basemap}.\nPoblación supuesta uniforme dentro de cada radio; "
        "distancia euclidiana desde el perímetro (EPSG:5347).",
    )
    gap_map = layout.figures / "mapa_poblacion_sin_cobertura_05ha.png"
    fig.savefig(gap_map, dpi=260, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {gap_map}")

    radios = gpd.read_file(layout.interim / "radios_2sfca.geojson").to_crs(3857)

    def access_map(distance: int, output) -> None:
        values = radios[f"m2hab_{distance}"]
        classes = np.select([values == 0, values < 1, values < 3, values < 9], [0, 1, 2, 3], 4)
        class_labels = [
            f"0 (sin espacio ≥ 0,5 ha a ≤ {distance} m)",
            "< 1",
            "1–3",
            "3–9",
            "≥ 9",
        ]
        class_colors = ["#67001f", "#e34a33", "#fdbb84", "#d9f0a3", "#41ab5d"]
        stats = summary["2sfca"][f"{distance}m"]
        figure, axis = plt.subplots(figsize=(10, 10.5), dpi=260)
        for index, color in enumerate(class_colors):
            radios[classes == index].plot(ax=axis, color=color, alpha=0.85, lw=0, zorder=3)
        large.plot(ax=axis, color="none", edgecolor="#00441b", lw=0.5, hatch="////", zorder=4)
        basemap_name = base(
            axis,
            f"CABA: m² de espacio verde (≥ 0,5 ha) accesible por habitante (2SFCA, {distance} m)",
        )
        share = radios.groupby(classes)["pop"].sum() / radios["pop"].sum() * 100
        legend = [
            mpatches.Patch(
                color=class_colors[index],
                label=f"{class_labels[index]}  ({_comma(share.get(index, 0))}% de la pob.)",
            )
            for index in range(5)
        ]
        legend += [
            mpatches.Patch(fc="none", ec="#00441b", hatch="////", label="Espacios verdes ≥ 0,5 ha"),
            Line2D([0], [0], color="#555", lw=0.8, label="Barrios (GCBA)"),
            Line2D([0], [0], color="k", lw=1.5, label="Límite CABA (OSM)"),
        ]
        axis.legend(
            handles=legend,
            **LEGEND,
            fontsize=8.5,
            framealpha=0.92,
            title_fontsize=8.5,
            title=(
                "m²/hab por radio censal (promedio del radio;\n"
                "% de población según clase del radio)\n"
                f"Mediana por residente: {_comma(stats['mediana_m2hab_residentes'], 2)} m²/hab "
                "· ref. 9 m²/hab*"
            ),
        )
        summary["2sfca"][f"{distance}m"]["pct_pob_por_clase_radio"] = {
            class_labels[index]: round(float(share.get(index, 0)), 2) for index in range(5)
        }
        foot(
            axis,
            SOURCE + f"Mapa base: {basemap_name}.\n"
            f"2SFCA: oferta = superficie del parque / población a ≤ {distance} m de su perímetro; "
            "demanda = puntos de población (grilla 40 m).\n"
            "*9 m²/hab: valor frecuentemente citado y atribuido a la OMS (no es una norma formal). "
            "Sin calidad ni efecto borde (Provincia de Bs. As.).",
        )
        figure.savefig(output, dpi=260, bbox_inches="tight")
        plt.close(figure)
        print(f"wrote {output}")

    access_map(500, layout.figures / "mapa_2sfca_m2_por_habitante.png")
    access_map(1000, layout.figures / "mapa_2sfca_m2_por_habitante_1000m.png")
    layout.resumen_poblacion.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    table = pd.read_csv(layout.results / "barrios_poblacion_500m_min05ha.csv").head(15).iloc[::-1]
    fig, ax = plt.subplots(figsize=(9, 7), dpi=200)
    ax.barh(table.nombre, table.pob_sin_cob / 1e3, color="#e6550d")
    for y_pos, (people, percent) in enumerate(
        zip(table.pob_sin_cob, table.pct_pob_sin_cob, strict=True)
    ):
        ax.text(
            people / 1e3 + 0.8,
            y_pos,
            f"{people / 1e3:.1f} mil ({percent:.0f}%)".replace(".", ","),
            va="center",
            fontsize=8,
        )
    ax.set_xlabel("Habitantes a más de 500 m de un espacio verde ≥ 0,5 ha (miles)")
    ax.set_title("Barrios con más población sin espacio verde ≥ 0,5 ha a ≤ 500 m", weight="bold")
    ax.set_xlim(0, table.pob_sin_cob.max() / 1e3 * 1.25)
    ax.spines[["top", "right"]].set_visible(False)
    ax.text(
        0,
        -0.1,
        "Entre paréntesis: % de la población del barrio. Censo 2022 (INDEC, vía IDECBA), "
        "OSM 2026-10-18.",
        transform=ax.transAxes,
        fontsize=7,
    )
    chart = layout.figures / "grafico_barrios_pob_sin_cobertura_05ha.png"
    fig.savefig(chart, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {chart}")
