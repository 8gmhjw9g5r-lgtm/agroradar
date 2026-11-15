# Riesgo de la milpa — MVP Space Apps 2026

El agricultor marca su parcela en el mapa, dice qué siembra y cuándo, y recibe para tres rotaciones
(maíz tras maíz, maíz con frijol, maíz con abono verde) un índice de éxito de 0 a 100 con su rango,
los riesgos por variable con su probabilidad e intervalo, y una explicación en español sencillo.

**Éxito** = rendimiento sobre el percentil 25 histórico de la zona. El índice nunca sale sin rango, y no
se publica hasta calibrarlo contra los rendimientos del MAG (ver `docs/DECISIONES.md`).

## Correr

```bash
pip install fastapi uvicorn pyyaml httpx
cp .env.example .env        # poner su GEMINI_API_KEY (opcional: sin ella no hay texto del agente)
uvicorn backend.api:app --reload
```
Abrir http://localhost:8000.

## Pruebas

```bash
python -m unittest -v tests.test_mvp
```
Las capas 5, 6 y 8 usan POWER real (la primera vez descargan unos 13 000 días por celda y luego leen de `data/cache`).
La capa 7 con Gemini real solo corre si hay `GEMINI_API_KEY`.

## Validación y calibración

```bash
python -m backend.validar
```
Deja un año fuera, calcula el Brier y escribe `data/validacion.json`.

```bash
python -m backend.validar mag
```
Calcula el AUC contra los rendimientos departamentales del MAG (`data/mag_rendimientos.csv`, 2001-2022) y escribe `data/calibracion.json`. Resultado actual: primera AUC 0.90 (se publica); postrera AUC 0.33 (no se publica, solo riesgos). Ver `docs/DECISIONES.md`.

## Datos declarados

| Fuente | Uso | Acceso |
|---|---|---|
| NASA POWER (diario, MERRA-2) | Lluvia, temperaturas y humedad relativa de 1991 al presente | Sin llave |
| NASA AppEEARS (SMAP, NASADEM, HLS, MODIS) | Humedad, pendiente y verdor; precargados por zona piloto | Cuenta Earthdata |
| NOAA CPC ONI | Fase de El Niño por año | Sin llave |
| ISRIC SoilGrids | Textura, carbono y nitrógeno (evidencia C) | Sin llave |
| Open-Meteo | Pronóstico de 7 días | Sin llave, uso no comercial |
| Google Gemini | Explicación en texto | Llave de cada usuario en `.env` |

## Estructura

```
config/umbrales.yaml   umbrales y tablas (todo supuesto salvo lo citado en DECISIONES.md)
config/grafo.yaml      relaciones causales que el agente puede usar
backend/clients/       POWER con caché; Open-Meteo, SoilGrids, ONI
backend/features.py    inicio de lluvias, racha seca, VPD, ET0, RUSLE
backend/models.py      Wilson, análogos, gamma, ENSO, índice por bootstrap, tendencia, AUC
backend/satelite.py    lector de AppEEARS precargado
backend/agent/         prompt y llamada a Gemini con verificador de reglas
backend/api.py         endpoint POST /api/finca y la página
backend/validar.py     dejar un año fuera y calibración MAG
frontend/index.html    mapa, formulario y tarjetas
tests/test_mvp.py      las 12 capas del plan de pruebas
```

Licencia MIT. Cada usuario pone su propia llave en `.env`; ninguna llave va al repositorio, y una prueba lo verifica.
