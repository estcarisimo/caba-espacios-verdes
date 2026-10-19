"""Coverage math on a synthetic city. No network and no real census data."""

from __future__ import annotations

import json

import geopandas as gpd
from shapely.geometry import box

from caba_espacios_verdes.coverage import analyze
from caba_espacios_verdes.paths import Layout


def test_buffer_is_measured_from_the_perimeter(tmp_path):
    layout = Layout(
        data=tmp_path / "data",
        results=tmp_path / "results",
        figures=tmp_path / "figures",
    ).ensure()
    city = gpd.GeoDataFrame(geometry=[box(0, 0, 3000, 3000)], crs=5347)
    city.to_crs(4326).to_file(layout.boundary_osm, driver="GeoJSON")
    barrios = gpd.GeoDataFrame(
        {"BARRIO": ["BOCA"], "COMUNA": ["4.0"]},
        geometry=[box(0, 0, 3000, 3000)],
        crs=5347,
    )
    barrios.to_crs(4326).to_file(layout.barrios, driver="GeoJSON")
    green = gpd.GeoDataFrame(
        {
            "cat": ["leisure=park", "leisure=golf_course", "leisure=park"],
            "access": [None, None, "private"],
            "garden_type": [None, None, None],
            "name": ["Plaza", "Golf", "Club"],
        },
        geometry=[box(0, 0, 100, 100), box(2000, 2000, 2200, 2200), box(2500, 2500, 2600, 2600)],
        crs=5347,
    )
    green.to_crs(4326).to_file(layout.green_raw, driver="GeoJSON")

    summary = analyze(layout)
    scenario = summary["scenarios"]["500m_todos"]
    assert summary["excluded"]["tipo excluido (golf_course / nature_reserve)"] == 1
    assert summary["excluded"]["access=private/no/customers"] == 1
    assert scenario["n_green"] == 1
    assert 0 < scenario["covered_pct"] < 50
    assert 50 < scenario["uncovered_pct"] < 100
    assert abs(scenario["covered_pct"] + scenario["uncovered_pct"] - 100) < 0.02
    assert (layout.results / "barrios_500m_todos.csv").exists()
    assert (layout.interim / "cobertura_500m_todos.geojson").exists()
    table = (layout.results / "barrios_500m_todos.csv").read_text(encoding="utf-8")
    assert "La Boca" in table
    written = json.loads(layout.resumen.read_text(encoding="utf-8"))
    assert written["scenarios"]["500m_min05ha"]["n_green"] == 1
