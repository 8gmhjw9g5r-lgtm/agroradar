# Preloaded AppEEARS series

One file per pilot zone, named as in `config/thresholds.yaml` (`san_miguel.csv`, `la_union.csv`, `chalatenango.csv`):

```
date,layer,value,quality_ok
2024-06-10,ndvi,0.61,1
2024-06-26,ndvi,0.12,0
2024-06-10,smap,0.31,1
2000-02-11,slope,14.2,1
```

- `layer` can be `ndvi` (HLS 30 m or MODIS 250 m), `smap` (surface moisture, m³/m³) or `slope` (% derived from NASADEM; one row per pixel of the polygon).
- `quality_ok` is 1 if the pixel passes the AppEEARS quality or cloud mask, and 0 if not. The 0 rows are dropped; if fewer than 30% remain valid, the evidence drops to C.
- The exact AppEEARS product and layer names (for example, the NDVI band and its quality layer) are confirmed when the first file is downloaded; here the data is only normalized.

Plots outside the pilot zones are written to `queue.jsonl` so they can be requested later.
