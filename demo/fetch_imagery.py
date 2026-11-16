"""Downloads NASA GIBS Blue Marble tiles and stitches two backdrops for the demo video."""
import io, sys, urllib.request
from pathlib import Path
from PIL import Image

LAYER = "BlueMarble_ShadedRelief_Bathymetry"
URL = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/{l}/default/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg"
OUT = Path(__file__).parent / "assets"

def mosaic(z, xs, ys, name):
    img = Image.new("RGB", (256 * len(xs), 256 * len(ys)))
    for i, x in enumerate(xs):
        for j, y in enumerate(ys):
            with urllib.request.urlopen(URL.format(l=LAYER, z=z, x=x, y=y), timeout=60) as r:
                img.paste(Image.open(io.BytesIO(r.read())).convert("RGB"), (256 * i, 256 * j))
    img.save(OUT / name, quality=92)
    print(name, img.size)

mosaic(8, range(62, 67), range(116, 120), "el_salvador.jpg")   # El Salvador and neighbours
mosaic(4, range(2, 8), range(5, 9), "americas.jpg")              # the Americas
