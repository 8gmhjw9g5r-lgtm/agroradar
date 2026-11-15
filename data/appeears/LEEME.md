# Series de AppEEARS precargadas

Un archivo por zona piloto, con el nombre de `config/umbrales.yaml` (`san_miguel.csv`, `la_union.csv`, `chalatenango.csv`):

```
fecha,capa,valor,calidad_ok
2024-06-10,ndvi,0.61,1
2024-06-26,ndvi,0.12,0
2024-06-10,smap,0.31,1
2000-02-11,pendiente,14.2,1
```

- `capa` puede ser `ndvi` (HLS 30 m o MODIS 250 m), `smap` (humedad superficial, m³/m³) o `pendiente` (% derivado de NASADEM; una fila por píxel del polígono).
- `calidad_ok` vale 1 si el píxel pasa la máscara de calidad o de nubes de AppEEARS, y 0 si no. Los 0 se descartan; si quedan menos del 30% válidos, la evidencia baja a C.
- Los nombres exactos de producto y capa en AppEEARS (por ejemplo, la banda NDVI y su capa de calidad) se confirman al bajar el primer archivo; aquí solo se normaliza.

Las parcelas fuera de las zonas piloto se anotan en `cola.jsonl` para pedirlas después.
