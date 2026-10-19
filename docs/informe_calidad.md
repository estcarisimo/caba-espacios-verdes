# CABA: calidad de vegetación de los espacios verdes (Sentinel-2) × acceso y población

> En el repositorio, el compuesto se arma con `caba-espacios-verdes quality` (escribe en `data/calidad_src/`) y los mapas con `caba-espacios-verdes maps --only quality`. Los CSV y JSON se generan en `results/` y no se versionan. Los mapas están en `figures/`. La metodología y las cifras son las del análisis original.

Scripts originales: `quality_composite.py` arma el compuesto S2 (`data/calidad_src/`), `quality.py` hace los cálculos y escribe `results/resumen_calidad.json`, y `maps_calidad.py` arma los mapas. Todas las cifras salen de `resumen_calidad.json`, `espacios_verdes_calidad.csv` y los CSV `*_vegetado*`. El cálculo de calidad no reescribe las salidas de cobertura ni de población: verifica que esos archivos no cambien de fecha mientras corre.

## Datos
- **Sentinel-2 L2A**: Element84 Earth Search STAC v1 (`sentinel-2-l2a`, COGs en AWS, sin autenticación), tile 21HUB, del 2025-12-01 al 2026-03-31, nubosidad del tile < 10%. Son 16 escenas, del 2025-12-03 al 2026-03-18; la lista completa está en `data/calidad_src/escenas.json`. Se descartan los píxeles cuya SCL no es 4, 5 o 6. Mediana por píxel de B04 y B08 a 10 m, y NDVI calculado sobre esa mediana. Cada píxel tiene una mediana de 15 observaciones válidas; 0,08% de los píxeles no tenían ninguna y usan la mediana de todas sus observaciones.
  - Nota técnica: Earth Search marca `boa_offset_applied=True`, es decir, los DN ya vienen corregidos. Aplicar además el offset −0,1 de `raster:bands` deja 30% de los píxeles con rojo negativo, así que no se aplicó.
- **Copa arbórea** (control, barato): ESA WorldCover 2021 v200 (clase 10 = árboles, 10 m) y Meta/WRI Canopy Height 1 m (2 tiles de unos 530 MB; % de píxeles ≥ 3 m y ≥ 5 m; imágenes mayormente de 2009–2020).

## Clases (NDVI medio por polígono, ponderado por la fracción de cada píxel dentro del polígono)
Límites: seca/dura < 0,3 · intermedia 0,3–0,5 · verde/arbolada ≥ 0,5. Ver `calidad.todos` y `calidad.min05ha` en el JSON.

## Advertencias
- NDVI no equivale a copa arbórea: el césped regado en verano también supera 0,5. La correlación del NDVI con el % de árboles de WorldCover es 0,78; con el % de píxeles ≥ 3 m del CHM de Meta, 0,55.
- Los píxeles de 10 m mezclan los bordes (calles, veredas, agua). Si se calcula sólo sobre el interior (erosión de 10 m), el NDVI medio sube de 0,506 a 0,537 y 119 de 817 polígonos cambian de clase. Los paseos costeros tienen píxeles de agua, que dan NDVI negativo.
- El arbolado de calle y los pulmones de manzana fuera de los polígonos OSM no se cuentan.
- Es la estación de máximo verdor (verano). En invierno, o en un verano seco, los valores serían menores.
- Umbral de 0,5 ha: varios polígonos de 0,5–0,6 ha quedan apenas debajo por efecto borde (por ejemplo Plaza Italia, 0,53 ha brutas y 0,44 vegetadas). Esto explica saltos grandes en algunos barrios, como Núñez.
- Siguen valiendo las advertencias de `informe_poblacion.md`: distancia euclidiana, efecto borde con la Provincia, población uniforme por radio y 9 m²/hab como referencia, no como norma.
