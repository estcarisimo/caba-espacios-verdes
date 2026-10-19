"""Fast checks that do not download OSM, census or satellite data."""

from __future__ import annotations

import pytest

from caba_espacios_verdes import __version__
from caba_espacios_verdes.barrios import display_barrio
from caba_espacios_verdes.cli import main
from caba_espacios_verdes.download import query_text, with_osm_date
from caba_espacios_verdes.osm import rel_to_geom, way_to_geom
from caba_espacios_verdes.sources import (
    BARRIOS_GEOJSON_URL,
    CHM_TILES,
    DEFAULT_OSM_DATE,
    EARTH_SEARCH_STAC,
    OVERPASS_URL,
    WFS_LAYER,
    WFS_URL,
    WORLDCOVER_URL,
)


def test_version_constant():
    assert __version__ == "0.1.0"


def test_cli_help():
    with pytest.raises(SystemExit) as caught:
        main(["--help"])
    assert caught.value.code == 0


def test_cli_version(capsys):
    main(["version"])
    assert __version__ in capsys.readouterr().out


def test_cli_download_help():
    with pytest.raises(SystemExit) as caught:
        main(["download", "--help"])
    assert caught.value.code == 0


def test_pipeline_modules_import():
    import caba_espacios_verdes.coverage
    import caba_espacios_verdes.maps_coverage
    import caba_espacios_verdes.maps_population
    import caba_espacios_verdes.maps_quality
    import caba_espacios_verdes.population
    import caba_espacios_verdes.quality
    import caba_espacios_verdes.quality_composite

    assert caba_espacios_verdes.coverage.BUFFER_M == 500
    assert caba_espacios_verdes.population.STEP_M == 40
    assert caba_espacios_verdes.quality.T_VEG == 0.3
    assert caba_espacios_verdes.quality_composite.VALID_SCL == [4, 5, 6]
    assert caba_espacios_verdes.maps_coverage.run
    assert caba_espacios_verdes.maps_population.run
    assert caba_espacios_verdes.maps_quality.run


def test_source_links_are_the_published_endpoints():
    assert OVERPASS_URL == "https://overpass-api.de/api/interpreter"
    assert WFS_LAYER == "geonube:total_pob_vivp_radio_censal2022"
    assert WFS_LAYER in WFS_URL
    assert WFS_URL.startswith("https://ideec.estadisticaciudad.gob.ar/geoserver/ows?")
    assert BARRIOS_GEOJSON_URL.endswith("/barrios/barrios.geojson")
    assert EARTH_SEARCH_STAC == "https://earth-search.aws.element84.com/v1"
    assert "ESA_WorldCover_10m_2021_v200_S36W060_Map.tif" in WORLDCOVER_URL
    assert set(CHM_TILES) == {"210321300", "210321301"}
    assert all(
        url.startswith("https://dataforgood-fb-data.s3.amazonaws.com/")
        for url in CHM_TILES.values()
    )


def test_overpass_queries_match_the_analysis_filters():
    boundary = query_text("q_boundary.txt")
    green = query_text("q_green.txt")
    assert 'relation["boundary"="administrative"]["admin_level"="4"]' in boundary
    assert "Ciudad Autónoma de Buenos Aires" in boundary
    assert "rel(3082668)" in green
    for tag in (
        '["leisure"="park"]',
        '["leisure"="garden"]',
        '["place"="square"]',
        '["landuse"="recreation_ground"]',
        '["leisure"="golf_course"]',
        '["leisure"="nature_reserve"]',
    ):
        assert tag in green
    dated = with_osm_date(boundary, DEFAULT_OSM_DATE)
    assert f'[date:"{DEFAULT_OSM_DATE}T23:59:59Z"]' in dated
    assert with_osm_date(green, "now") == green


def test_way_and_relation_polygons():
    way = way_to_geom(
        {
            "geometry": [
                {"lon": 0, "lat": 0},
                {"lon": 1, "lat": 0},
                {"lon": 1, "lat": 1},
                {"lon": 0, "lat": 1},
                {"lon": 0, "lat": 0},
            ]
        }
    )
    assert way is not None
    assert way.area == pytest.approx(1)
    assert way_to_geom({"geometry": [{"lon": 0, "lat": 0}, {"lon": 1, "lat": 0}]}) is None

    relation = rel_to_geom(
        {
            "members": [
                {
                    "type": "way",
                    "role": "outer",
                    "geometry": [
                        {"lon": 0, "lat": 0},
                        {"lon": 2, "lat": 0},
                        {"lon": 2, "lat": 2},
                        {"lon": 0, "lat": 2},
                        {"lon": 0, "lat": 0},
                    ],
                }
            ]
        }
    )
    assert relation is not None
    assert relation.area == pytest.approx(4)


OFFICIAL_AND_PUBLISHED = {
    "AGRONOMIA": "Agronomia",
    "ALMAGRO": "Almagro",
    "BALVANERA": "Balvanera",
    "BARRACAS": "Barracas",
    "BELGRANO": "Belgrano",
    "BOCA": "La Boca",
    "BOEDO": "Boedo",
    "CABALLITO": "Caballito",
    "CHACARITA": "Chacarita",
    "COGHLAN": "Coghlan",
    "COLEGIALES": "Colegiales",
    "CONSTITUCION": "Constitucion",
    "FLORES": "Flores",
    "FLORESTA": "Floresta",
    "LINIERS": "Liniers",
    "MATADEROS": "Mataderos",
    "MONSERRAT": "Monserrat",
    "MONTE CASTRO": "Monte Castro",
    "NUEVA POMPEYA": "Nueva Pompeya",
    "NUÑEZ": "Nuñez",
    "PALERMO": "Palermo",
    "PARQUE AVELLANEDA": "Parque Avellaneda",
    "PARQUE CHACABUCO": "Parque Chacabuco",
    "PARQUE CHAS": "Parque Chas",
    "PARQUE PATRICIOS": "Parque Patricios",
    "PATERNAL": "Paternal",
    "PUERTO MADERO": "Puerto Madero",
    "RECOLETA": "Recoleta",
    "RETIRO": "Retiro",
    "SAAVEDRA": "Saavedra",
    "SAN CRISTOBAL": "San Cristobal",
    "SAN NICOLAS": "San Nicolas",
    "SAN TELMO": "San Telmo",
    "VELEZ SARSFIELD": "Velez Sarsfield",
    "VERSALLES": "Versalles",
    "VILLA CRESPO": "Villa Crespo",
    "VILLA DEL PARQUE": "Villa Del Parque",
    "VILLA DEVOTO": "Villa Devoto",
    "VILLA GRAL. MITRE": "Villa Gral. Mitre",
    "VILLA LUGANO": "Villa Lugano",
    "VILLA LURO": "Villa Luro",
    "VILLA ORTUZAR": "Villa Ortuzar",
    "VILLA PUEYRREDON": "Villa Pueyrredon",
    "VILLA REAL": "Villa Real",
    "VILLA RIACHUELO": "Villa Riachuelo",
    "VILLA SANTA RITA": "Villa Santa Rita",
    "VILLA SOLDATI": "Villa Soldati",
    "VILLA URQUIZA": "Villa Urquiza",
}


def test_barrio_labels_match_the_published_tables():
    assert len(OFFICIAL_AND_PUBLISHED) == 48
    for official, published in OFFICIAL_AND_PUBLISHED.items():
        assert display_barrio(official) == published
        assert display_barrio(published) == published
