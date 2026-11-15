# Decisiones, fuentes y supuestos

Registro del bucle de trabajo: cada umbral o fórmula, con su fuente o la marca **SUPUESTO**.
Todo lo numérico vive en `config/umbrales.yaml`; el grafo en `config/grafo.yaml`.

## APIs verificadas con llamada real (2026-11-15)

| Fuente | Resultado |
|---|---|
| NASA POWER diario | `https://power.larc.nasa.gov/api/temporal/daily/point`, `community=AG`. Parámetros: `PRECTOTCORR` (mm/día), `T2M_MAX`, `T2M_MIN` (°C), `RH2M` (%). `fill_value` = -999. 1991-01-01 a 2026-11-12 sin ningún -999 en las dos celdas piloto. La respuesta repite el punto pedido en `geometry.coordinates`. |
| NOAA ONI | `https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt` responde (columnas SEAS YR TOTAL ANOM). Último dato: ASO 2026 = +2.46 (Niño fuerte). |
| Open-Meteo | `/v1/forecast` con `daily=precipitation_sum,temperature_2m_max` responde. |
| SoilGrids | **No respondió** (timeout de 90 s y luego HTTP 503). El cliente está escrito de memoria; unidades a confirmar. Si falla, K y N usan valores por defecto con evidencia C y el reporte lo dice. |
| AppEEARS | **No probado**: requiere cuenta Earthdata. El lector usa un CSV normalizado (ver `data/appeears/LEEME.md`). |
| POWER climatología | No se usa: la normal 1991-2020 se calcula de la serie diaria. |
| CMR, GIBS, IRI | Fuera del MVP. |

## Caché de POWER
- Clave: `round(lat/0.5)*0.5`, `round(lon/0.625)*0.625` + parámetros. Una solicitud por celda, sin expiración (borrar el archivo para refrescar).
- San Miguel y La Unión caen en la misma celda (13.5, -88.125); comparten clima y se diferencian por pendiente, verdor y suelo.

## Fórmulas con fuente
- e_s y VPD: ecuación de Tetens en la forma de FAO-56 (Allen et al., 1998). VPD(30 °C, 50%) = 2.12 kPa (prueba 1).
- ET0: Hargreaves (FAO-56 ec. 52) con radiación extraterrestre de FAO-56 ec. 21. Se usa Hargreaves porque solo pide temperaturas.
- R (erosividad): Renard y Freimund (1994), J. Hydrology 157: R = 0.0483·P^1.61 si P < 850 mm; si no, 587.8 − 1.219·P + 0.004105·P².
- K (erodabilidad): Williams (1995), modelo EPIC, desde arena, limo, arcilla y carbono orgánico; ×0.1317 a unidades SI.
- LS: factor S de McCool et al. (1987); L = 1 porque se supone una longitud de 22.13 m (**SUPUESTO**).
- C desde NDVI: van der Knijff et al. (2000): C = exp(−2·NDVI/(1−NDVI)).
- Wilson al 80% con z = 1.2816.
- Gamma: estimador de Thom; CDF por gamma incompleta regularizada.

## Supuestos (todos en `config/umbrales.yaml`)
- Límites lat/lon del piloto; zonas piloto (San Miguel, La Unión, Chalatenango) y radio de 15 km.
- Inicio de lluvias (20 mm en 3 días, sin racha de 7 días en los 21 siguientes, contados desde el día 4).
- Canícula: 15/07–31/08, riesgo si > 10 días; día seco < 1 mm. En postrera, la racha y el estrés se miden de la siembra al fin de la floración (la canícula ya pasó y el final del ciclo cae en la estación seca esperada).
- Calor: > 35 °C, riesgo si > 3 días en floración. Ciclo y floración: maíz 120 d (55–75), frijol 75 d (35–50).
- Inicio tardío = más de 15 días después de la mediana histórica.
- Estrés hídrico: fracción de bloques de 10 días con lluvia/ET0 < 0.5.
- Época deducida del mes: enero–julio primera; agosto–diciembre postrera.
- Pendiente por defecto 10%; K por defecto 0.03; C por cobertura declarada (desnudo 0.45, rastrojo 0.2, abono verde 0.1); `erosion_ref` = 200.
- Nitrógeno: N de referencia 3 g/kg; tabla de fijación y extracción por cultivo **sin fuente**; la salida es solo una dirección.
- **Tabla de efectos de rotación (E)**: todas las celdas son supuesto. Es la parte más débil del índice y el índice hereda esa debilidad.
- Pesos: base 1 por variable; ×2 si el agricultor marca esa prioridad; nitrógeno ×0.25 sin análisis de suelo. "Mercado" no tiene datos en el MVP.
- Cortes de publicación: AUC ≥ 0.70 normal; 0.60–0.70 confianza baja; < 0.60 no se publica.
- Tendencia de erosión: "sin tendencia clara" si el IC del 80% de la pendiente incluye 0 (p ≈ 0.2). Es un criterio flojo y por eso solo se habla de tendencia, nunca de magnitud.
- ENSO: la fase de cada año se toma del ONI de JJA (la estación de la canícula), con umbral ±0.5.

## Decisiones de diseño del modelo
- **Umbral u del modelo 5**: se fija por parcela como el percentil 25 del puntaje de la rotación base, así maíz tras maíz da 75 por construcción. Filtrar por fase ENSO mantiene ese u, por eso el índice base cambia. La prueba 10 calcula u con la serie sin sequía y lo aplica a la serie con sequía.
- **Aporte al índice**: puntos que subiría el índice base si esa variable fuera siempre como en su mejor año observado (contrafactual). Una variable constante (sin datos) aporta 0.
- **Ranking de parcelas**: solo usa variables con datos reales. Un riesgo neutral supuesto, como verdor sin satélite, no ordena parcelas.
- El índice evalúa el ciclo del cultivo planeado (maíz o frijol; si es abono verde, el de maíz). Las rotaciones difieren solo por la tabla E.
- El grafo agrega la arista `canicula_larga → lluvia_baja` (evidencia A, por definición) para conectar la canícula con la cadena del agua. El verdor no tiene arista en el borrador y se explica sin cadena.
- Si el índice no es publicable, el backend borra `indice`, `rango_80` y `aporte_al_indice` antes de responder y antes de llamar al agente; además, el verificador marca cualquier "índice … número" en el texto.

## Hallazgos de la validación (2026-11-15, `python -m backend.validar`)
- La spec dice que Wilson con k=13, n=35 da "28 a 47%". El cálculo exacto da **27.5–48.0%**, y la prueba usa ese valor.
- Brier por dejar un año fuera, canícula larga: frecuencia sin ajuste 0.0830; ajuste por análogos 0.0804 (San Miguel). El ajuste gana por muy poco, así que queda activo, pero la diferencia está dentro del ruido.
- La canícula larga sale poco frecuente (3 de 36 años en San Miguel). POWER (MERRA-2 a 0.5°) tiende a llovizna diaria y casi nunca da días < 1 mm en temporada. **Hay que revisar el umbral de día seco con un técnico o con estaciones locales.**
- Inicio de lluvias 2025: día 150 (30 de mayo) contra una mediana de 136.5 en San Miguel. Es más tardío que la mediana, pero unas 2 semanas, no casi un mes como reporta FEWS NET, y no cruza el umbral de "inicio tardío" (+15 días). Se reporta sin forzarlo.

## Rendimientos del MAG y calibración (2026-11-15)

**Datos** (`data/mag_rendimientos.csv`): rendimiento total de maíz (qq/mz) de los 14 departamentos en 20 temporadas, 2001-02 a 2022-23. Es el Cuadro 3 de cada Anuario de Estadísticas Agropecuarias (DGEA-MAG).
- **Origen de los PDF:** 2018-19 a 2022-23 vienen de mag.gob.sv; los anteriores, de copias en Internet Archive de `mag.gob.sv/download/anuario-de-estadisticas-agropecuarias-*`.
- **Años faltantes:** 2007-08 y 2008-09 no están archivados. El de 1996-97 no tiene la tabla por departamento en texto.
- **Años posteriores:** no hay anuarios después de 2022-23. Según la prensa, en 2026 el MAG restringió los anuarios recientes alegando secreto estadístico.
- **Extracción:** 15 años salieron del texto del PDF (`pdftotext -layout`). Como la maquetación desalinea los nombres, las filas se toman en el orden fijo del cuadro y se aceptan solo si cada región suma sus departamentos.
- **Transcripción a mano:** 2002, 2006, 2019, 2020 y 2022 se transcribieron desde la imagen de la página (columna `extraccion`).
- **Validación:** las 280 filas cumplen producción/superficie = rendimiento (±0.3). Los totales nacionales coinciden con la retrospectiva del MAG, salvo 2004 y 2005, donde se usa la cifra del propio anuario (la retrospectiva posterior parece revisada). 2005 se verificó también a ojo contra la página.
- **Errores del propio MAG:** el cuadro 2020-21 tiene pequeñas incoherencias internas; por ejemplo, el total de Ahuachapán no es la suma de sus épocas.
- **Sanidad:** los peores años coinciden con sequías conocidas. En 2001, La Unión dio 7.4 y San Miguel 16.2. En 2014, Chalatenango dio 28.9. En 2009, San Miguel dio 27.4.

**Rendimientos por época** (filas con `epoca` = primera o postrera): de 2013-14 a 2022-23 solo para Chalatenango, San Miguel y La Unión. Se transcribieron de la página y el rendimiento se recalculó como producción/superficie. El rendimiento total mezcla dos cosechas que pueden ir en sentido contrario. En 2014 (El Niño), San Miguel dio 19.9 en primera y 40.1 en postrera, con un total de 30.0. Además, la mezcla cambia con el tiempo: en San Miguel había más primera que postrera en 2013, y la postrera domina desde 2015.

### Calibración v1 (descartada)
Rendimiento total contra la época dominante (San Miguel y La Unión en postrera, Chalatenango en primera), con 60 departamento-años. AUC 0.61 (0.51–0.71). Por departamento: Chalatenango 0.92 · La Unión 0.66 · San Miguel 0.46.

### Calibración v2 (vigente, `data/calibracion.json`)
**Cambios decididos por diagnóstico y razones agronómicas, antes de ver el AUC:**
1. **Ventana de postrera.** La racha seca y el estrés hídrico se medían de la siembra a la cosecha (agosto→diciembre), así que incluían la estación seca normal. La racha salía de 15 a 48 días todos los años y el riesgo quedaba saturado, sin señal. Ahora en postrera se miden de la siembra al fin de la floración (día 75; con siembra el 25/08, hasta inicios de noviembre). En San Miguel la racha pasa a variar entre 2 y 16 días. La primera no cambia.
2. **Cada rendimiento contra su época.**
   - Chalatenango: total 2001–2022 contra primera (más del 97% es invierno en todos los cuadros).
   - San Miguel: primera contra primera y postrera contra postrera, 2013–2022.
   - La Unión: solo postrera, porque su primera tiene menos de 2 000 mz casi todos los años.
   - Los totales del oriente anteriores a 2013 salen, porque su mezcla de épocas es desconocida.
3. **El corte de publicación se aplica por época:** son dos modelos distintos (ventanas distintas) y cada uno debe ganarse su publicación.

**Resultado:**
| Serie | AUC | n | fracasos |
|---|---|---|---|
| Chalatenango / total (primera) | 0.92 | 20 | 6 |
| San Miguel / primera | 1.00 | 10 | 3 |
| San Miguel / postrera | 0.38 | 10 | 3 |
| La Unión / postrera | 0.29 | 10 | 3 |
| **Primera (conjunto)** | **0.90** (IC80 0.81–0.99) | 30 | → **normal, se publica** |
| **Postrera (conjunto)** | **0.33** (IC80 0.13–0.57) | 20 | → **no se publica**, solo riesgos |
| Todo junto (referencia) | 0.67 (0.54–0.79) | 50 | |

**Lectura honesta:**
- **Primera:** el modelo funciona en primera, que es donde actúan la canícula y el calor en floración. Aun así, la muestra es pequeña: el AUC de 1.00 en San Miguel sale de 10 años con 3 fracasos.
- **Postrera:** el modelo no explica la postrera. El AUC por debajo de 0.5 en las dos series sugiere que lo que daña la postrera no es lo que medimos.
- **Hipótesis del exceso de lluvia:** se probó solo como diagnóstico, sin cambiar el modelo, y **no se confirma**. La correlación con la lluvia de septiembre y octubre fue −0.19 en San Miguel y −0.33 en La Unión; con el máximo de 3 días, +0.26 y +0.05.
- **Explicaciones a investigar:** plagas, precios, el retiro de las lluvias según estaciones locales, o que la celda de 0.5° de POWER no capte la lluvia del oriente.
- **Riesgo de sobreajuste:** se usaron 2 cambios de diseño con 50 puntos. Ninguno se eligió por el AUC, pero conviene repetir la calibración cuando haya más años.

## Pendiente para confiar en el índice
1. Postrera: buscar qué explica sus malos años (estaciones locales, fecha de retiro de lluvias, reportes de daño del MAG o de FEWS NET) y recalibrar con `python -m backend.validar mag`.
2. Descargas de AppEEARS para las zonas piloto (SMAP, NASADEM, HLS/MODIS) convertidas al CSV normalizado.
3. Fuentes para la tabla E, la tabla de nitrógeno y todos los umbrales.
4. Que SoilGrids vuelva a responder, o un K y un N locales.
