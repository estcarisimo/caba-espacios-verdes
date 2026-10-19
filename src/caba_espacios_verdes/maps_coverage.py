"""Static and interactive maps of the 500 m coverage scenarios."""

from __future__ import annotations

import json

import contextily as cx
import folium
import geopandas as gpd
import matplotlib
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from caba_espacios_verdes.paths import Layout, require

matplotlib.use("Agg")


def run(layout: Layout) -> None:
    layout.ensure()
    require(layout.resumen, "Run `caba-espacios-verdes coverage` first.")
    require(layout.boundary_osm, "Run `caba-espacios-verdes coverage` first.")
    require(layout.barrios, "Run `caba-espacios-verdes download` first.")
    require(layout.green_used, "Run `caba-espacios-verdes coverage` first.")

    summary = json.loads(layout.resumen.read_text(encoding="utf-8"))
    caba = gpd.read_file(layout.boundary_osm).to_crs(3857)
    barrios = gpd.read_file(layout.barrios).to_crs(3857)
    green = gpd.read_file(layout.green_used).to_crs(3857)
    green["ha"] = green.to_crs(5347).area / 1e4

    def figure(key: str, spaces, title: str, output) -> None:
        covered = gpd.read_file(layout.interim / f"cobertura_{key}.geojson").to_crs(3857)
        uncovered = gpd.read_file(layout.interim / f"zonas_sin_cobertura_{key}.geojson").to_crs(
            3857
        )
        scenario = summary["scenarios"][key]
        fig, ax = plt.subplots(figsize=(10, 10.5), dpi=260)
        covered.plot(ax=ax, color="#a6dba0", alpha=0.35, lw=0, zorder=2)
        uncovered.plot(ax=ax, color="#e6550d", alpha=0.75, lw=0.3, edgecolor="#a63603", zorder=3)
        spaces.plot(ax=ax, color="#1b7837", lw=0, zorder=4)
        barrios.boundary.plot(ax=ax, color="#555555", lw=0.35, zorder=5)
        caba.boundary.plot(ax=ax, color="black", lw=1.2, zorder=6)
        try:
            cx.add_basemap(ax, source=cx.providers.Esri.WorldGrayCanvas, zoom=13, attribution=False)
            basemap = "Esri World Gray Canvas"
        except Exception as exc:
            print("basemap failed", exc)
            basemap = "sin mapa base"
        ax.set_axis_off()
        ax.set_title(title, fontsize=15, weight="bold")
        handles = [
            mpatches.Patch(
                color="#1b7837", label=f"Espacios verdes usados (n={scenario['n_green']})"
            ),
            mpatches.Patch(
                color="#a6dba0",
                alpha=0.6,
                label=f"A ≤ 500 m: {scenario['covered_pct']:.1f}% de CABA",
            ),
            mpatches.Patch(
                color="#e6550d",
                alpha=0.75,
                label=(
                    f"A > 500 m: {scenario['uncovered_km2']:.2f} km² "
                    f"({scenario['uncovered_pct']:.1f}%)"
                ),
            ),
            Line2D([0], [0], color="#555", lw=0.8, label="Barrios (GCBA)"),
            Line2D([0], [0], color="k", lw=1.5, label="Límite CABA (OSM)"),
        ]
        ax.legend(handles=handles, loc="upper left", fontsize=9, framealpha=0.9)
        ax.text(
            0.01,
            0.01,
            "Datos: © colaboradores de OpenStreetMap (ODbL), Overpass 2026-10-18; "
            "barrios: GCBA datos abiertos.\n"
            f"Mapa base: {basemap}. Distancia euclidiana desde el perímetro (EPSG:5347). "
            "leisure=park/garden, place=square,\n"
            "landuse=recreation_ground; excluye golf, reservas naturales, "
            "access=private/no/customers.",
            transform=ax.transAxes,
            fontsize=6.5,
            va="bottom",
            bbox={"fc": "white", "alpha": 0.8, "lw": 0},
        )
        fig.savefig(output, dpi=260, bbox_inches="tight")
        plt.close(fig)
        print(f"wrote {output}")

    figure(
        "500m_todos",
        green,
        "CABA: zonas a más de 500 m de un espacio verde (OSM)",
        layout.figures / "mapa_cobertura_500m.png",
    )
    figure(
        "500m_min05ha",
        green[green.ha >= 0.5],
        "CABA: zonas a más de 500 m de un espacio verde ≥ 0,5 ha (OSM)",
        layout.figures / "mapa_cobertura_500m_min05ha.png",
    )

    key = "500m_todos"
    covered = gpd.read_file(layout.interim / f"cobertura_{key}.geojson")
    uncovered = gpd.read_file(layout.interim / f"zonas_sin_cobertura_{key}.geojson")
    green_wgs = green.to_crs(4326)[["name", "cat", "ha", "osm_type", "osm_id", "geometry"]].copy()
    green_wgs["ha"] = green_wgs.ha.round(2)
    green_wgs["name"] = green_wgs.name.fillna("(sin nombre)")
    barrios_wgs = barrios.to_crs(4326)[["nombre", "comuna", "geometry"]]
    interactive = folium.Map(location=[-34.615, -58.445], zoom_start=12, tiles="OpenStreetMap")
    folium.GeoJson(
        covered,
        name="Cobertura ≤ 500 m",
        style_function=lambda _feature: {
            "fillColor": "#a6dba0",
            "color": "none",
            "fillOpacity": 0.35,
        },
    ).add_to(interactive)
    uncovered = uncovered.copy()
    uncovered["ha"] = (uncovered.area_m2 / 1e4).round(2)
    folium.GeoJson(
        uncovered,
        name="> 500 m (sin cobertura)",
        style_function=lambda _feature: {
            "fillColor": "#e6550d",
            "color": "#a63603",
            "weight": 0.5,
            "fillOpacity": 0.65,
        },
        tooltip=folium.GeoJsonTooltip(["ha"], aliases=["Superficie (ha)"]),
    ).add_to(interactive)
    folium.GeoJson(
        green_wgs,
        name="Espacios verdes",
        style_function=lambda _feature: {
            "fillColor": "#1b7837",
            "color": "#1b7837",
            "weight": 0.5,
            "fillOpacity": 0.8,
        },
        tooltip=folium.GeoJsonTooltip(["name", "cat", "ha"], aliases=["Nombre", "Tag", "ha"]),
    ).add_to(interactive)
    folium.GeoJson(
        barrios_wgs,
        name="Barrios",
        style_function=lambda _feature: {"fill": False, "color": "#555", "weight": 0.8},
        tooltip=folium.GeoJsonTooltip(["nombre", "comuna"]),
    ).add_to(interactive)
    folium.GeoJson(
        caba.to_crs(4326),
        name="Límite CABA",
        style_function=lambda _feature: {"fill": False, "color": "black", "weight": 2},
    ).add_to(interactive)
    folium.LayerControl().add_to(interactive)
    interactive.get_root().html.add_child(
        folium.Element(
            '<h3 style="position:fixed;top:8px;left:60px;z-index:9999;background:white;'
            'padding:4px 8px;">CABA: zonas a más de 500 m de un espacio verde (OSM)</h3>'
        )
    )
    html_path = layout.figures / "mapa_cobertura_500m.html"
    interactive.save(html_path)
    print(f"wrote {html_path}")
