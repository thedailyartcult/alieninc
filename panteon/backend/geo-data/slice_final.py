"""
Final XYZ slicer. Masters are z14-aligned: master pixel == z14 world pixel.
For zoom z: crop AOI window from master, downsample by 2^(14-z), cut 256s.
Run: python3 slice_final.py
"""
import contextlib, json, math, os
import numpy as np
from PIL import Image

_err = open(os.devnull, "w")
with contextlib.redirect_stderr(_err):
    from osgeo import gdal
_err.close()

D    = os.path.dirname(os.path.abspath(__file__))
OUT  = "/home/alieninc/panteon/geo-tiles"
AOI  = [120.85, 14.05, 121.35, 14.85]
ZMIN, ZMASTER = 8, 14
R    = 6378137.0
WORLD= 2 * math.pi * R

grid = json.load(open(f"{D}/_master_grid.json"))
MB, MW, MH = grid["MB"], grid["MW"], grid["MH"]
RES = WORLD / (2**ZMASTER * 256)

def wpx(lon, lat, z):
    """world-pixel coords at zoom z"""
    n = 2**z * 256
    x = (lon + 180) / 360 * n
    y = (WORLD/2 - R*math.log(math.tan(math.pi/4 + math.radians(lat)/2))) / WORLD * n
    return x, y

def load_bands(path):
    ds = gdal.Open(path)
    out = []
    for i in range(1, ds.RasterCount+1):
        b = ds.GetRasterBand(i)
        dt = gdal.GDT_Float32 if b.DataType != gdal.GDT_Byte else gdal.GDT_Byte
        buf = b.ReadRaster(0, 0, MW, MH, buf_type=dt)
        arr = np.frombuffer(buf, dtype=(np.float32 if dt==gdal.GDT_Float32 else np.uint8)).reshape(MH, MW).copy()
        out.append(arr)
    ds = None
    return out

LAYER_SPECS = []
for tag in ("sentinel-dry", "sentinel-wet"):
    LAYER_SPECS.append((tag, load_bands(f"{D}/_m_{tag}.tif"), "RGB"))

delta = load_bands(f"{D}/_m_ndwi.tif",)[0]
thr = 0.15
strength = np.clip((np.abs(delta)-thr)/0.25, 0, 1)
alpha = np.where(np.abs(delta)>thr, (40+strength*215), 0).astype(np.uint8)
blue = np.where(delta>thr, (60+strength*195), 20).astype(np.uint8)
red  = np.where(delta<-thr, (230-strength*30), 30).astype(np.uint8)
grn  = np.full(blue.shape, 90, np.uint8)
LAYER_SPECS.append(("ndwi-change", [red, grn, blue, alpha], "RGBA"))
del delta, strength; gc.collect() if False else None

master_top_x = MB[0] / WORLD * (2**ZMASTER * 256)     # world px x of master left
master_top_y = (WORLD/2 - MB[3]) / WORLD * (2**ZMASTER * 256)

total = 0
for tag, bands, mode in LAYER_SPECS:
    src = Image.merge(mode, [Image.fromarray(b) for b in bands])
    del bands
    for z in range(ZMIN, ZMASTER+1):
        X0, Y0 = wpx(AOI[0], AOI[3], z)
        X1, Y1 = wpx(AOI[2], AOI[1], z)
        wpx_w, wpx_h = int(round(X1-X0)), int(round(Y1-Y0))
        im = src.resize((max(wpx_w,1), max(wpx_h,1)), Image.BILINEAR)
        tx0 = int(math.floor(X0/256)); ty0 = int(math.floor(Y0/256))
        tx1 = int(math.floor((X0+wpx_w-0.001)/256))
        ty1 = int(math.floor((Y0+wpx_h-0.001)/256))
        fill = (0,0,0,0) if mode=="RGBA" else (0,0,0)
        for tx in range(tx0, tx1+1):
            for ty in range(ty0, ty1+1):
                ox = int(round(X0) - tx*256); oy = int(round(Y0) - ty*256)
                t = Image.new(mode, (256,256), fill)
                t.paste(im, (ox, oy))
                td = f"{OUT}/{tag}/{z}/{tx}"
                os.makedirs(td, exist_ok=True)
                t.save(f"{td}/{ty}.png", optimize=True)
                total += 1
    print(tag, "done", flush=True)
print("TOTAL:", total)
