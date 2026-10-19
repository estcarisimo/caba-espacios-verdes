"""NDVI, vegetated 2SFCA and the density-versus-access bivariate map."""

from __future__ import annotations

import json

import contextily as cx
import geopandas as gpd
import matplotlib
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D
from rasterio.warp import Resampling, calculate_default_transform, reproject

from caba_espacios_verdes.paths import Layout, require

matplotlib.use("Agg")

LEGEND = {"loc": "upper left", "bbox_to_anchor": (1.01, 0.98)}


def _comma(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def run(layout: Layout) -> None:
    layout.ensure()
    require(layout.resumen_calidad, "Run `caba-espacios-verdes quality` first.")
    require(layout.boundary_osm, "Run `caba-espacios-verdes coverage` first.")
    require(layout.barrios, "Run `caba-espacios-verdes download` first.")
    require(layout.sentinel_tif, "Run `caba-espacios-verdes quality` first.")
    require(
        layout.interim / "espacios_verdes_calidad.geojson",
        "Run `caba-espacios-verdes quality` first.",
    )
    require(
        layout.interim / "radios_2sfca_vegetado.geojson",
        "Run `caba-espacios-verdes quality` first.",
    )

    summary = json.loads(layout.resumen_calidad.read_text(encoding="utf-8"))
    caba = gpd.read_file(layout.boundary_osm).to_crs(3857)
    barrios = gpd.read_file(layout.barrios).to_crs(3857)
    green = gpd.read_file(layout.interim / "espacios_verdes_calidad.geojson").to_crs(3857)
    large = green[green.ha >= 0.5]
    dates = [scene["fecha"] for scene in summary["sentinel2"]["escenas"]]
    source = (
        "Sentinel-2 L2A (ESA Copernicus) vía Element84 Earth Search: mediana de "
        f"{len(dates)} escenas {dates[0]} a {dates[-1]} (tile 21HUB, nubosidad < 10%, "
        "máscara SCL).\n"
        "Espacios verdes: © colaboradores de OpenStreetMap (ODbL), Overpass 2026-10-18; "
        "barrios: GCBA datos abiertos. "
    )

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

    with rasterio.open(layout.sentinel_tif) as src:
        ndvi = src.read(3)
        transform, (height, width) = src.transform, ndvi.shape
        dst_transform, dst_width, dst_height = calculate_default_transform(
            src.crs, "EPSG:3857", width, height, *src.bounds
        )
        warped = np.full((dst_height, dst_width), np.nan, "float32")
        reproject(
            ndvi,
            warped,
            src_transform=transform,
            src_crs=src.crs,
            dst_transform=dst_transform,
            dst_crs="EPSG:3857",
            resampling=Resampling.bilinear,
            src_nodata=np.nan,
            dst_nodata=np.nan,
        )
    extent = (
        dst_transform.c,
        dst_transform.c + dst_transform.a * dst_width,
        dst_transform.f + dst_transform.e * dst_height,
        dst_transform.f,
    )
    colormap = LinearSegmentedColormap.from_list(
        "ndvi", ["#f2efe9", "#e8e4d0", "#c7dca0", "#7fbf7b", "#2d7a3a"]
    )
    class_colors = {"seca/dura": "#d95f02", "intermedia": "#fec44f", "verde/arbolada": "#1a9850"}
    quality = summary["calidad"]
    fig, ax = plt.subplots(figsize=(10, 10.5), dpi=260)
    caba.plot(ax=ax, color="none", lw=0)
    image = ax.imshow(
        warped,
        extent=extent,
        cmap=colormap,
        vmin=0,
        vmax=0.8,
        alpha=0.75,
        zorder=2,
        interpolation="nearest",
    )
    for label, color in class_colors.items():
        green[green.clase == label].plot(
            ax=ax, color=color, edgecolor="#222222", lw=0.25, alpha=0.95, zorder=4
        )
    ax.set_xlim(caba.total_bounds[[0, 2]] + [-400, 400])
    ax.set_ylim(caba.total_bounds[[1, 3]] + [-400, 400])
    basemap = base(
        ax, "CABA: calidad de vegetación de los espacios verdes (NDVI Sentinel-2, verano 2025-26)"
    )
    class_labels = {
        "seca/dura": "Seca/dura (NDVI medio < 0,3)",
        "intermedia": "Intermedia (0,3–0,5)",
        "verde/arbolada": "Verde/arbolada (≥ 0,5)",
    }
    handles = [mpatches.Patch(color="white", label="Espacios verdes OSM por NDVI medio:")] + [
        mpatches.Patch(
            fc=class_colors[label],
            ec="#222",
            lw=0.4,
            label=(
                f"{class_labels[label]}: {quality['todos']['clases'][label]['n']} "
                f"({quality['min05ha']['clases'][label]['n']} de ≥ 0,5 ha)"
            ),
        )
        for label in class_colors
    ]
    handles += [
        Line2D([0], [0], color="#555", lw=0.8, label="Barrios (GCBA)"),
        Line2D([0], [0], color="k", lw=1.5, label="Límite CABA (OSM)"),
    ]
    ax.legend(
        handles=handles,
        **LEGEND,
        fontsize=8.5,
        framealpha=0.92,
        title_fontsize=8.5,
        title=(
            f"n = {quality['todos']['n']} espacios; NDVI medio mediano "
            f"{_comma(quality['todos']['ndvi_mediana'], 2)}\n"
            f"(entre paréntesis: espacios ≥ 0,5 ha, n = {quality['min05ha']['n']})"
        ),
    )
    colorbar_ax = ax.inset_axes([1.04, 0.52, 0.32, 0.022])
    colorbar = fig.colorbar(image, cax=colorbar_ax, orientation="horizontal")
    colorbar.set_label("NDVI (fondo, mediana del verano, 10 m)", fontsize=7.5)
    colorbar.ax.tick_params(labelsize=7)
    for record in quality["secas_grandes_nombradas_plazas_parques"][:6]:
        match = green[(green.name == record["name"]) & (abs(green.ha - record["ha"]) < 0.01)]
        if len(match):
            point = match.geometry.iloc[0].representative_point()
            ax.annotate(
                record["name"],
                (point.x, point.y),
                xytext=(6, 6),
                textcoords="offset points",
                fontsize=5.5,
                zorder=9,
                color="#7f2704",
                bbox={"fc": "white", "alpha": 0.7, "lw": 0, "pad": 0.5},
            )
    foot(
        ax,
        source + f"Mapa base: {basemap}.\nNDVI = (B08−B04)/(B08+B04). NDVI no equivale a cobertura "
        "arbórea (césped regado también supera 0,5). \nPíxeles de 10 m mezclan bordes "
        "(calles, agua). Rótulos: espacios ≥ 0,5 ha nombrados con NDVI < 0,3.",
    )
    ndvi_map = layout.figures / "mapa_calidad_ndvi_espacios_verdes.png"
    fig.savefig(ndvi_map, dpi=260, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {ndvi_map}")

    radios = gpd.read_file(layout.interim / "radios_2sfca_vegetado.geojson").to_crs(3857)
    access = summary["2sfca_500m"]
    values = radios["m2hab_veg_500"]
    classes = np.select([values == 0, values < 1, values < 3, values < 9], [0, 1, 2, 3], 4)
    class_labels = ["0 (sin espacio ≥ 0,5 ha a ≤ 500 m)", "< 1", "1–3", "3–9", "≥ 9"]
    class_colors_list = ["#67001f", "#e34a33", "#fdbb84", "#d9f0a3", "#41ab5d"]
    fig, ax = plt.subplots(figsize=(10, 10.5), dpi=260)
    for index, color in enumerate(class_colors_list):
        radios[classes == index].plot(ax=ax, color=color, alpha=0.85, lw=0, zorder=3)
    large.plot(ax=ax, color="none", edgecolor="#00441b", lw=0.5, hatch="////", zorder=4)
    basemap = base(
        ax,
        "CABA: m² de superficie vegetada (NDVI > 0,3) en espacios verdes ≥ 0,5 ha\n"
        "accesible por habitante (2SFCA, 500 m)",
    )
    share = radios.groupby(classes)["pop"].sum() / radios["pop"].sum() * 100
    handles = [
        mpatches.Patch(
            color=class_colors_list[index],
            label=f"{class_labels[index]}  ({_comma(share.get(index, 0))}% de la pob.)",
        )
        for index in range(5)
    ]
    handles += [
        mpatches.Patch(fc="none", ec="#00441b", hatch="////", label="Espacios verdes ≥ 0,5 ha"),
        Line2D([0], [0], color="#555", lw=0.8, label="Barrios (GCBA)"),
        Line2D([0], [0], color="k", lw=1.5, label="Límite CABA (OSM)"),
    ]
    vegetated = access["vegetado_mismas_unidades"]
    raw = access["raw_control"]
    ax.legend(
        handles=handles,
        **LEGEND,
        fontsize=8.5,
        framealpha=0.92,
        title_fontsize=8.5,
        title=(
            "m² vegetados/hab por radio censal (promedio del radio;\n"
            "% de población según clase del radio)\n"
            f"Mediana por residente: {_comma(vegetated['mediana_m2hab_residentes'], 2)} "
            "m²/hab vegetados\n"
            f"(vs {_comma(raw['mediana_m2hab_residentes'], 2)} m²/hab de superficie bruta) "
            "· ref. 9 m²/hab*"
        ),
    )
    summary.setdefault("mapas", {})["pct_pob_por_clase_radio_2sfca_veg_500"] = {
        class_labels[index]: round(float(share.get(index, 0)), 2) for index in range(5)
    }
    foot(
        ax,
        source + f"Población: INDEC, Censo 2022, vía IDECBA. Mapa base: {basemap}.\n"
        "2SFCA: oferta = área del parque × fracción de píxeles con NDVI > 0,3 / población "
        "a ≤ 500 m de su perímetro; demanda = puntos (grilla 40 m).\n"
        "*9 m²/hab: valor frecuentemente citado y atribuido a la OMS (no es norma formal). "
        "NDVI ≠ copa arbórea; sin arbolado de calle ni efecto borde (Provincia).",
    )
    vegetated_map = layout.figures / "mapa_2sfca_m2_vegetado_por_habitante.png"
    fig.savefig(vegetated_map, dpi=260, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {vegetated_map}")

    gap = access["brecha_bivariada"]
    palette = {
        (0, 2): "#e8e8e8",
        (1, 2): "#b5c0da",
        (2, 2): "#6c83b5",
        (0, 1): "#e4d9ac",
        (1, 1): "#b0a99d",
        (2, 1): "#6a6d8e",
        (0, 0): "#e8b25c",
        (1, 0): "#c2723f",
        (2, 0): "#8c1d1d",
    }
    fig, ax = plt.subplots(figsize=(10, 10.5), dpi=260)
    radios["cl_dens"] = pd.cut(radios.dens_ha, [0, 150, 350, np.inf], right=False, labels=False)
    radios["cl_acc"] = pd.cut(
        radios.m2hab_veg_500, [-np.inf, 1, 3, np.inf], right=False, labels=False
    )
    for (density, access_class), color in palette.items():
        radios[(radios.cl_dens == density) & (radios.cl_acc == access_class)].plot(
            ax=ax, color=color, lw=0, zorder=3, alpha=0.95
        )
    large.plot(ax=ax, color="none", edgecolor="#00441b", lw=0.4, zorder=4)
    basemap = base(
        ax,
        "CABA: brecha de verde — densidad de población × acceso a superficie vegetada\n"
        "(2SFCA 500 m, m² con NDVI > 0,3 por habitante)",
    )
    inset = ax.inset_axes([1.06, 0.62, 0.24, 0.24])
    dark = {(2, 0), (2, 2), (2, 1), (1, 0)}
    for (density, access_class), color in palette.items():
        inset.add_patch(mpatches.Rectangle((density, 2 - access_class), 1, 1, color=color))
        inset.text(
            density + 0.5,
            2 - access_class + 0.5,
            f"{gap['pob_por_celda'][f'dens{density}_acc{access_class}'] / 1e3:.0f} mil",
            ha="center",
            va="center",
            fontsize=6.5,
            color="white" if (density, access_class) in dark else "black",
        )
    inset.set_xlim(0, 3)
    inset.set_ylim(0, 3)
    inset.set_xticks([0.5, 1.5, 2.5], ["< 150", "150–350", "≥ 350"], fontsize=7)
    inset.set_yticks([0.5, 1.5, 2.5], ["≥ 3", "1–3", "< 1"], fontsize=7)
    inset.set_xlabel("Densidad del radio (hab/ha) →", fontsize=7.5)
    inset.set_ylabel("m² vegetados/hab (menos ↑)", fontsize=7.5)
    inset.set_title("Población por celda", fontsize=7.5)
    handles = [
        mpatches.Patch(fc="none", ec="#00441b", label="Espacios verdes ≥ 0,5 ha"),
        Line2D([0], [0], color="#555", lw=0.8, label="Barrios (GCBA)"),
        Line2D([0], [0], color="k", lw=1.5, label="Límite CABA (OSM)"),
    ]
    ax.legend(
        handles=handles,
        loc="upper left",
        bbox_to_anchor=(1.01, 0.5),
        fontsize=8.5,
        framealpha=0.92,
        title_fontsize=8.5,
        title=(
            "Rojo oscuro: ≥ 350 hab/ha y < 1 m² vegetado/hab\n"
            f"= {gap['pob_alta_densidad_menos1m2'] / 1e3:.0f} mil hab. "
            f"({_comma(gap['pct_pob_alta_densidad_menos1m2'])}% de la población)"
        ),
    )
    foot(
        ax,
        source
        + f"Población: INDEC, Censo 2022 (viv. particulares), vía IDECBA. Mapa base: {basemap}.\n"
        "Clases por radio censal (promedio del radio). NDVI ≠ copa arbórea; sin arbolado de "
        "calle ni efecto borde (Provincia).",
    )
    gap_map = layout.figures / "mapa_brecha_densidad_vs_verde_vegetado.png"
    fig.savefig(gap_map, dpi=260, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {gap_map}")
    layout.resumen_calidad.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
