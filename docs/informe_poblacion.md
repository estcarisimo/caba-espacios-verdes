# CABA: espacios verdes × población (Censo 2022)

> En el repositorio, estos cálculos se corren con `caba-espacios-verdes population` y los mapas con `caba-espacios-verdes maps --only population`. Los CSV y JSON que cita este informe se generan en `results/` y no se versionan. Los mapas están en `figures/`. La metodología y las cifras son las del análisis original (módulos que siguen a `population.py` y `maps_poblacion.py`).

Scripts originales: `population.py` (cálculos) → `resumen_poblacion.json`; `maps_poblacion.py` (mapas/gráfico). Todos los números salen de `resumen_poblacion.json` y de los CSV.

## Fuente de población
- **Censo 2022 (INDEC, resultados definitivos)**, población en viviendas particulares por radio censal (3.820 radios, con geometría), publicada por el IECBA/GCBA en IDECBA: WFS `geonube:total_pob_vivp_radio_censal2022` (visor https://ideec.estadisticaciudad.gob.ar/visualizador/cnphyv_2022).
- Suma de los radios: **3.095.454** = 3.121.707 (población total publicada) − 23.850 (viviendas colectivas) − 2.403 (vía pública). Hogares 1.406.735 (coincide con el informe del IECBA).
- No se usó el GeoJSON 2010 de GCBA (`caba_radios_censales.geojson`, 3.554 radios, suma 2.890.151); se bajó sólo para verificar.

## Resultados
Ver `results/resumen_poblacion.json`, `results/barrios_poblacion_500m_min05ha.csv`, `results/barrios_poblacion_500m_todos.csv`, `results/barrios_2sfca_500m.csv`, `results/barrios_2sfca_1000m.csv`, `results/barrios_m2_verde_por_habitante.csv`.

## Cómo podría agregarse "calidad" más adelante
- Cobertura arbórea/vegetación: NDVI de Sentinel-2 (10 m) o cobertura de copa por parque. Sirve para ponderar la oferta, por ejemplo m² "verdes reales" en lugar de m² de polígono.
- Equipamiento desde OSM: juegos infantiles, bancos, bebederos, canchas, baños, iluminación, perros, etc. Con esto se arma un índice de amenidades por parque.
- Dataset de espacios verdes del GCBA (categorías: parque, plaza, plazoleta, jardín, cantero central…) para depurar los tags de OSM y excluir canteros o espacios no utilizables.
- Accesibilidad por red peatonal (isócronas reales) en lugar de distancia euclidiana, y un 2SFCA con decaimiento por distancia (Gaussiano / E2SFCA).

## Advertencias
- La población se asume uniforme dentro de cada radio. Una versión dasimétrica, que la saca de la superficie verde, da casi lo mismo (26,49% vs 26,50%).
- Se usa la población en viviendas particulares: faltan unas 26 mil personas, en viviendas colectivas y en la vía pública.
- Efecto borde: no se cuentan los parques de la Provincia ni sus residentes, que también usan parques de CABA. Esto sobreestima la oferta en el borde sur y en Puerto Madero y la Costanera.
- Los polígonos de OSM incluyen superficies no verdes (solados, playones, landuse=recreation_ground como polideportivos). La superficie no es lo mismo que la calidad.
- 2SFCA con cuenca binaria (≤ d) y distancia euclidiana desde el perímetro. Polígonos solapados o contiguos ≥ 0,5 ha se fusionan en 404 unidades.
- 9 m²/hab: valor citado con frecuencia y atribuido a la OMS. No es una norma formal de la OMS; se usa sólo como referencia.
