# Roadmap

Estado al 2026-11-15. Detalle técnico y supuestos en `DECISIONES.md`.

## Fase actual: 3 de 7, validación y calibración (a mitad de camino)

| Área | Estado |
|---|---|
| Concepto y spec (éxito = rendimiento sobre el p25 histórico de la zona; 3 rotaciones; índice siempre con rango) | ✅ Hecho |
| Datos: NASA POWER con caché, ONI, Open-Meteo, cliente de SoilGrids | ✅ Construido |
| Modelo: Wilson, análogos, gamma, ENSO, índice por bootstrap, RUSLE, AUC | ✅ Construido |
| API, página y agente Gemini con verificador de reglas | ✅ Construido |
| Plan de pruebas de 12 capas y prueba de repo sin llaves | ✅ Escrito |
| Dejar un año fuera (Brier) | ✅ Hecho |
| Calibración MAG v2 | ⚠️ Primera AUC 0.90 (se publica); postrera AUC 0.33 (no se publica, solo riesgos) |
| AppEEARS (SMAP, NASADEM, HLS) | ❌ Sin descargar |
| SoilGrids | ❌ No responde; cliente sin probar con respuesta real |
| Fuentes de la tabla E, la tabla de nitrógeno y los umbrales | ❌ Todo SUPUESTO |

## Inmediato
1. Control de versiones (git) y primer commit.
2. Confirmar que el entorno corre: dependencias y `python -m unittest -v tests.test_mvp`.
3. Congelar la calibración v2 como línea base. Escribir las hipótesis de postrera en `DECISIONES.md` **antes** de probarlas (riesgo de sobreajuste: 2 cambios de diseño con 50 puntos).

## Fase 3 (ahora): cerrar validación y calibración
- Postrera: buscar qué explica los malos años. Opciones: estaciones locales (MARN), fecha de retiro de lluvias, reportes de daño del MAG o FEWS NET, plagas, la celda de 0.5° de POWER. El exceso de lluvia ya se descartó. Recalibrar con `python -m backend.validar mag`.
- Umbral de día seco: POWER casi no da días < 1 mm (canícula larga en 3 de 36 años). Contrastar con estaciones.
- **Listo cuando:** postrera llega a AUC ≥ 0.60 o queda formalmente como "solo riesgos", y primera se sostiene con más años.

## Fase 4: completar los datos
- Cuenta Earthdata, pedidos de AppEEARS para las 3 zonas piloto y conversión al CSV de `data/appeears/LEEME.md`.
- SoilGrids funcionando, o un K y un N locales.
- Fuentes para la tabla E, que es la parte más débil del índice.
- **Listo cuando:** pendiente, verdor y suelo salen de datos reales y la evidencia C queda solo donde de verdad falta algo.

## Fase 5: revisión experta y piloto de campo
- Un agrónomo (CENTA, CRS) revisa `config/umbrales.yaml` y cada arista de `config/grafo.yaml`.
- Prueba con agricultores de San Miguel, La Unión y Chalatenango: que el español se entienda, que las 3 preguntas de campo sirvan y que el rango se comprenda.
- **Listo cuando:** los umbrales están aprobados por un experto y hay notas de agricultores reales.

## Fase 6: robustez y despliegue
- CI que corra las pruebas, despliegue y decidir cómo se maneja la llave de Gemini en un servicio alojado.
- Revisar los términos de Open-Meteo (solo uso no comercial) antes de ampliar.
- Manejo de errores cuando una API no responde.
- **Listo cuando:** hay URL pública, el CI pasa y están publicadas las páginas sobre los datos y el método.

## Fase 7: ampliar
- Atender la cola de parcelas fuera del piloto (`data/appeears/cola.jsonl`).
- Agregar la prioridad de mercado (hoy sin datos).
- Recalibrar cuando salgan nuevos anuarios del MAG (restringidos desde 2026).
