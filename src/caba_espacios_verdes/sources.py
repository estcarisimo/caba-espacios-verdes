"""Direct links for every dataset the pipeline downloads or reads."""

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OSM_COPYRIGHT_URL = "https://www.openstreetmap.org/copyright"
OSM_RELATION_URL = "https://www.openstreetmap.org/relation/3082668"
OSM_RELATION_ID = 3082668

BARRIOS_DATASET_URL = "https://data.buenosaires.gob.ar/dataset/barrios"
BARRIOS_GEOJSON_URL = (
    "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/barrios/barrios.geojson"
)

INDEC_CENSO_URL = "https://www.indec.gob.ar/indec/web/Nivel4-Tema-2-41-165"
CENSUS_VISOR_URL = "https://ideec.estadisticaciudad.gob.ar/visualizador/cnphyv_2022"
WFS_URL = (
    "https://ideec.estadisticaciudad.gob.ar/geoserver/ows?service=WFS&version=1.0.0"
    "&request=GetFeature&typeName=geonube:total_pob_vivp_radio_censal2022"
    "&outputFormat=application/json"
)
WFS_LAYER = "geonube:total_pob_vivp_radio_censal2022"

EARTH_SEARCH_STAC = "https://earth-search.aws.element84.com/v1"
EARTH_SEARCH_COLLECTION = "https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a"
COPERNICUS_SENTINEL2_URL = (
    "https://dataspace.copernicus.eu/explore-data/data-collections/sentinel-data/sentinel-2"
)

WORLDCOVER_SITE_URL = "https://esa-worldcover.org/en"
WORLDCOVER_URL = (
    "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
    "ESA_WorldCover_10m_2021_v200_S36W060_Map.tif"
)

CHM_REGISTRY_URL = "https://registry.opendata.aws/dataforgood-fb-forests/"
CHM_TILES = {
    "210321300": (
        "https://dataforgood-fb-data.s3.amazonaws.com/forests/v1/"
        "alsgedi_global_v6_float/chm/210321300.tif"
    ),
    "210321301": (
        "https://dataforgood-fb-data.s3.amazonaws.com/forests/v1/"
        "alsgedi_global_v6_float/chm/210321301.tif"
    ),
}

ESRI_GRAY_CANVAS_URL = "https://www.arcgis.com/home/item.html?id=291da5eab3a0412593b66d384379f89f"

USER_AGENT = "caba-espacios-verdes/0.1 (+https://github.com/estcarisimo/caba-espacios-verdes)"

# Overpass attic timestamp of the extract behind the published figures.
DEFAULT_OSM_DATE = "2026-10-18"

# POSGAR 2007 / Argentina 5. Distances in this CRS are metres.
METRIC_CRS = 5347
BUFFER_M = 500
QUAD_SEGS = 16
MIN_HA = 0.5
