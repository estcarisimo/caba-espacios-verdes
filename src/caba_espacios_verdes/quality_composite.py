"""Sentinel-2 L2A median composite (B04, B08, NDVI) over CABA.

Scenes come from the Element84 Earth Search STAC API (``sentinel-2-l2a`` COGs
on AWS, no authentication): tile 21HUB, 2025-12-01 to 2026-03-31, tile cloud
cover under 10%. Pixels whose SCL class is not 4, 5 or 6 are dropped. The
median of B04 and of B08 is taken per pixel at 10 m, and NDVI is computed on
that median. The raster stays on the native UTM zone 21S grid (EPSG:32721).
"""

from __future__ import annotations

import json
import os

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.windows import from_bounds

from caba_espacios_verdes.paths import Layout, require
from caba_espacios_verdes.sources import EARTH_SEARCH_STAC

# SCL: vegetation, bare soil / urban, water.
VALID_SCL = [4, 5, 6]
PERIOD = "2025-12-01/2026-03-31"
MAX_CLOUD = 10
PAD_M = 300


def _gdal_env() -> None:
    os.environ.update(
        AWS_NO_SIGN_REQUEST="YES",
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
    )


def run(layout: Layout, *, force: bool = False) -> dict:
    """Build ``data/calidad_src/s2_median_b04_b08_ndvi_32721.tif`` and ``escenas.json``."""
    import pystac_client

    layout.ensure()
    if layout.sentinel_tif.exists() and layout.scenes_json.exists() and not force:
        print(f"keep {layout.sentinel_tif}")
        return json.loads(layout.scenes_json.read_text(encoding="utf-8"))

    _gdal_env()
    require(layout.boundary_osm, "Run `caba-espacios-verdes coverage` first.")
    caba = gpd.read_file(layout.boundary_osm)
    city_utm = caba.to_crs(32721)
    xmin, ymin, xmax, ymax = city_utm.total_bounds
    xmin = np.floor(xmin / 10) * 10 - PAD_M
    ymin = np.floor(ymin / 10) * 10 - PAD_M
    xmax = np.ceil(xmax / 10) * 10 + PAD_M
    ymax = np.ceil(ymax / 10) * 10 + PAD_M

    catalog = pystac_client.Client.open(EARTH_SEARCH_STAC)
    items = sorted(
        catalog.search(
            collections=["sentinel-2-l2a"],
            bbox=list(caba.total_bounds),
            datetime=PERIOD,
            query={"eo:cloud_cover": {"lt": MAX_CLOUD}},
        ).items(),
        key=lambda item: item.datetime,
    )
    if not items:
        raise SystemExit("Earth Search returned no Sentinel-2 scenes for the summer window.")

    reds: list[np.ndarray] = []
    nirs: list[np.ndarray] = []
    masks: list[np.ndarray] = []
    scenes: list[dict] = []
    transform = None
    for item in items:
        bands: dict[str, np.ndarray] = {}
        for key in ("red", "nir"):
            with rasterio.open(item.assets[key].href) as src:
                if src.crs.to_epsg() != 32721:
                    raise RuntimeError(f"{item.id} {key} is not EPSG:32721")
                window = from_bounds(xmin, ymin, xmax, ymax, src.transform)
                window = window.round_offsets().round_lengths()
                values = src.read(1, window=window).astype("float32")
                transform = src.window_transform(window)
            band = item.assets[key].extra_fields["raster:bands"][0]
            # Earth Search sets earthsearch:boa_offset_applied when the DN is already
            # corrected by BOA_ADD_OFFSET (-1000). Applying the raster:bands offset
            # again produced negative red reflectance on about 30% of pixels.
            offset = (
                0.0
                if item.properties.get("earthsearch:boa_offset_applied")
                else band.get("offset", 0.0)
            )
            bands[key] = np.where(values == 0, np.nan, values * band["scale"] + offset)
        with rasterio.open(item.assets["scl"].href) as src:
            window = from_bounds(xmin, ymin, xmax, ymax, src.transform)
            scl = src.read(
                1,
                window=window,
                out_shape=bands["red"].shape,
                resampling=Resampling.nearest,
            )
        inside = ~geometry_mask(city_utm.geometry, bands["red"].shape, transform)
        valid = np.isin(scl, VALID_SCL) & np.isfinite(bands["red"]) & np.isfinite(bands["nir"])
        reds.append(bands["red"])
        nirs.append(bands["nir"])
        masks.append(valid)
        scene = {
            "id": item.id,
            "fecha": str(item.datetime)[:10],
            "plataforma": item.properties["platform"],
            "nubosidad_tile_pct": round(item.properties["eo:cloud_cover"], 2),
            "baseline": item.properties.get("s2:processing_baseline"),
            "boa_offset_applied": item.properties.get("earthsearch:boa_offset_applied"),
            "pct_validos_SCL_en_CABA": round(100 * valid[inside].mean(), 2),
            "pct_nubes_sombra_SCL_en_CABA": round(
                100 * np.isin(scl, [3, 8, 9, 10])[inside].mean(), 2
            ),
        }
        scenes.append(scene)
        print(scene, flush=True)

    red_stack = np.stack(reds)
    nir_stack = np.stack(nirs)
    mask_stack = np.stack(masks)
    count = mask_stack.sum(0)
    red = np.nanmedian(np.where(mask_stack, red_stack, np.nan), 0)
    nir = np.nanmedian(np.where(mask_stack, nir_stack, np.nan), 0)
    fallback = count == 0
    red[fallback] = np.nanmedian(red_stack[:, fallback], 0)
    nir[fallback] = np.nanmedian(nir_stack[:, fallback], 0)
    ndvi = np.where((nir + red) > 0, (nir - red) / (nir + red), np.nan)
    inside = ~geometry_mask(city_utm.geometry, red.shape, transform)
    ndvi_city = np.where(inside, ndvi, np.nan)
    with rasterio.open(
        layout.sentinel_tif,
        "w",
        driver="GTiff",
        height=red.shape[0],
        width=red.shape[1],
        count=4,
        dtype="float32",
        crs="EPSG:32721",
        transform=transform,
        nodata=np.nan,
        compress="deflate",
    ) as dst:
        dst.write(np.stack([red, nir, ndvi_city, count.astype("float32")]))
        dst.descriptions = (
            "B04_median_reflectance",
            "B08_median_reflectance",
            "NDVI_clip_CABA",
            "n_obs_validas_SCL",
        )
    info = {
        "fuente": (
            "Element84 Earth Search STAC v1, colección sentinel-2-l2a "
            "(COGs en s3://sentinel-cogs, AWS us-west-2, sin autenticación)"
        ),
        "stac": EARTH_SEARCH_STAC,
        "periodo": PERIOD,
        "filtro": f"eo:cloud_cover < {MAX_CLOUD}% (tile)",
        "tile_mgrs": "21HUB",
        "crs_raster": "EPSG:32721 (grilla nativa 10 m)",
        "reflectancia": (
            "DN*0.0001; earthsearch:boa_offset_applied=True en todas las escenas => "
            "DN ya corregidos por BOA_ADD_OFFSET; no se vuelve a aplicar el offset -0.1 "
            "de raster:bands (aplicarlo daba 30% de píxeles con rojo negativo)"
        ),
        "mascara": (
            f"SCL en {VALID_SCL} (4 vegetación, 5 no vegetado, 6 agua); se excluyen 0-3, "
            "7-11 (sin dato, saturado, sombra oscura, sombra de nube, sin clasificar, "
            "nubes, cirros, nieve)"
        ),
        "compuesto": (
            "mediana por píxel de B04 y B08 (por separado) sobre observaciones válidas; "
            "NDVI = (B08-B04)/(B08+B04) del compuesto"
        ),
        "n_escenas": len(items),
        "escenas": scenes,
        "obs_validas_por_pixel_CABA": {
            "min": int(count[inside].min()),
            "mediana": float(np.median(count[inside])),
            "max": int(count[inside].max()),
            "pct_pixeles_sin_obs_valida_fallback": round(100 * fallback[inside].mean(), 3),
        },
        "ndvi_CABA": {
            "media": round(float(np.nanmean(ndvi_city)), 3),
            "p10": round(float(np.nanpercentile(ndvi_city, 10)), 3),
            "mediana": round(float(np.nanmedian(ndvi_city)), 3),
            "p90": round(float(np.nanpercentile(ndvi_city, 90)), 3),
            "pct_pix_gt03": round(100 * float(np.nanmean(ndvi_city > 0.3)), 2),
            "pct_pix_gt05": round(100 * float(np.nanmean(ndvi_city > 0.5)), 2),
        },
    }
    layout.scenes_json.write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
    printable = {key: value for key, value in info.items() if key != "escenas"}
    print(json.dumps(printable, indent=1, ensure_ascii=False))
    print(f"wrote {layout.sentinel_tif}")
    return info
