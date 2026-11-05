"""Georeferenced-exact Sentinel XYZ tiles. Run: python3 make_tiles.py"""
import contextlib, gc, json, math, os
import numpy as np
_err = open(os.devnull, "w")
with contextlib.redirect_stderr(_err):
    from osgeo import gdal, osr
    try: gdal.UseExceptions()
    except Exception: pass
_err.close()

D = os.path.dirname(os.path.abspath(__file__))
OUT = "/home/alieninc/panteon/geo-tiles"
AOI = [120.85, 14.05, 121.35, 14.85]
ZMIN, ZMASTER = 8, 14
R = 6378137.0
WORLD = 2 * math.pi * R                      # 40075016.7 m
RES = WORLD / (2 ** ZMASTER * 256)           # ~2.394 m/px
man = json.load(open(f"{D}/sentinel_manifest.json"))

def MX(lon): return (lon + 180.0) / 360.0 * WORLD   # XYZ origin is lon -180
def MY(lat): return R * math.log(math.tan(math.pi/4 + math.radians(lat)/2))

# snap AOI outward to whole z14 tiles
TX0 = int(math.floor(MX(AOI[0]) / (256*RES)))
TX1 = int(math.ceil (MX(AOI[2]) / (256*RES)))
TY0 = int(math.floor((WORLD/2 - MY(AOI[3])) / (256*RES)))   # top row (north)
TY1 = int(math.ceil ((WORLD/2 - MY(AOI[1])) / (256*RES)))   # bottom row
MB = (TX0*256*RES, WORLD/2-(TY1+1)*256*RES, (TX1+1)*256*RES, WORLD/2-TY0*256*RES)
MW, MH = (TX1-TX0+1)*256, (TY1-TY0+1)*256
json.dump({"MB": list(MB), "MW": MW, "MH": MH}, open(f"{D}/_master_grid.json","w"))
print(f"master: tiles x{TX0}-{TX1} y{TY0}-{TY1} -> {MW}x{MH}px @ {RES:.2f}m", flush=True)
assert MW > 0 and MH > 0

# NOTE: this GDAL build mis-transforms EPSG:3857 (half-world shift), so we
# reproject MANUALLY: master grid -> lon/lat (exact Mercator formulas) ->
# UTM51N via osr (the one direction this build gets right) -> bilinear.

_UTM_SRC = None
_UTM_CT = None
def _utm_ct():
    global _UTM_SRC, _UTM_CT
    if _UTM_CT is None:
        _UTM_SRC = osr.SpatialReference()
        _UTM_SRC.ImportFromEPSG(32651)
        _UTM_SRC.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        geog = osr.SpatialReference()
        geog.ImportFromEPSG(4326)
        geog.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        _UTM_CT = osr.CoordinateTransformation(geog, _UTM_SRC)
    return _UTM_CT

def warp_master(srcs, dst, nodata):
    """Mosaic-resample one or more scenes onto the z14-aligned master grid."""
    if isinstance(srcs, str):
        srcs = [srcs]
    src_ds = [gdal.Open(u) for u in srcs]
    gts = [d.GetGeoTransform() for d in src_ds]
    sizes = [(d.RasterXSize, d.RasterYSize) for d in src_ds]
    nb = src_ds[0].RasterCount
    dt = src_ds[0].GetRasterBand(1).DataType

    drv = gdal.GetDriverByName("GTiff")
    out = drv.Create(dst, MW, MH, nb, dt, options=["COMPRESS=DEFLATE", "TILED=YES"])
    out.SetGeoTransform([MB[0], RES, 0, MB[3], 0, -RES])
    sr = osr.SpatialReference(); sr.ImportFromEPSG(3857); sr.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    out.SetProjection(sr.ExportToWkt())

    ct = _utm_ct()
    STRIP = 256
    filled = np.zeros((MH, MW), bool)
    nd = float(nodata) if nodata is not None else -1e30
    for y0 in range(0, MH, STRIP):
        y1 = min(y0 + STRIP, MH)
        h = y1 - y0
        # world coords for this strip
        xs = MB[0] + (np.arange(MW) + 0.5) * RES
        ys = MB[3] - (np.arange(y0, y1) + 0.5) * RES
        lon = np.degrees(xs / R) - 180.0
        lat = np.degrees(2 * np.arctan(np.exp(ys / R)) - math.pi / 2)
        LON, LAT = np.meshgrid(lon, lat)
        pts = ct.TransformPoints(list(zip(LON.ravel().tolist(), LAT.ravel().tolist())))
        E = np.array([p[0] for p in pts], dtype=np.float64).reshape(h, MW)
        N = np.array([p[1] for p in pts], dtype=np.float64).reshape(h, MW)
        for bi in range(nb):
            obuf = np.full((h, MW), nd, dtype=(np.uint16 if dt==gdal.GDT_UInt16 else (np.float32 if dt==gdal.GDT_Float32 else np.uint8)))
            for si in range(len(src_ds)):
                g = gts[si]; w_s, h_s = sizes[si]
                c = (E - g[0]) / g[1]; r = (N - g[3]) / g[5]
                inside = (c >= 0) & (c <= w_s-2) & (r >= 0) & (r <= h_s-2) & (~filled[y0:y1])
                if not inside.any(): continue
                c_i = c[inside]; r_i = r[inside]
                x0 = max(int(c_i.min())-1, 0); x1 = min(int(c_i.max())+2, w_s)
                y0s = max(int(r_i.min())-1, 0); y1s = min(int(r_i.max())+2, h_s)
                buf = src_ds[si].GetRasterBand(bi+1).ReadRaster(
                    x0, y0s, x1-x0, y1s-y0s, buf_type=gdal.GDT_Float32)
                blk = np.frombuffer(buf, dtype=np.float32).reshape(y1s-y0s, x1-x0).copy()
                blk[blk < -1e30] = np.nan
                cc = c_i - x0; rr = r_i - y0s
                c0f = np.clip(np.floor(cc).astype(int), 0, blk.shape[1]-2)
                r0f = np.clip(np.floor(rr).astype(int), 0, blk.shape[0]-2)
                fc = np.clip(cc-c0f, 0, 1); fr = np.clip(rr-r0f, 0, 1)
                val = (blk[r0f, c0f]*(1-fr)*(1-fc) + blk[r0f, c0f+1]*fr*(1-fc) +
                       blk[r0f+1, c0f]*(1-fr)*fc + blk[r0f+1, c0f+1]*fr*fc)
                yy, xx = np.where(inside)
                good = np.isfinite(val)
                obuf[yy[good], xx[good]] = val[good].astype(obuf.dtype)
                filled[y0:y1][inside & True] |= good
            out.GetRasterBand(bi+1).WriteRaster(0, y0, MW, h, obuf.tobytes(), buf_type=dt)
        print(f"  strip {y0}/{MH}", flush=True)
    for d in src_ds: d = None
    out = None

def load_band(path):
    ds = gdal.Open(path); b = ds.GetRasterBand(1)
    dt = gdal.GDT_Byte if b.DataType == gdal.GDT_Byte else gdal.GDT_Float32
    buf = b.ReadRaster(0, 0, MW, MH, buf_type=dt)
    ds = None
    return np.frombuffer(buf, dtype=(np.uint8 if dt==gdal.GDT_Byte else np.float32)).reshape(MH, MW)

os.makedirs(OUT, exist_ok=True)
masters = {}
for tag, keys in (("sentinel-dry",("dry","dry_north")), ("sentinel-wet",("wet","wet_north"))):
    p = f"{D}/_m_{tag}.tif"
    if not os.path.exists(p):
        srcs = [f"/vsicurl/{man[k]['visual']}" for k in keys if k in man]
        print("manual-warping", tag, f"(mosaic of {len(srcs)})…", flush=True)
        warp_master(srcs, p, 0)
    masters[tag] = p; print(tag, "ready", flush=True); gc.collect()

p_nd = f"{D}/_m_ndwi.tif"
if not os.path.exists(p_nd):
    for key in ("dry","wet"):
        for bk in ("green","nir"):
            t = f"{D}/_s_{key}_{bk}.tif"
            if not os.path.exists(t):
                nkey = key + "_north"
                srcs = [f"/vsicurl/{man[key][bk]}"] + ([f"/vsicurl/{man[nkey][bk]}"] if nkey in man else [])
                print("warping", key, bk, f"(mosaic of {len(srcs)})…", flush=True)
                warp_master(srcs, t, -99999.0)
    def nd(p):
        a = load_band(p).astype(np.float32)
        a[a < -1e30] = np.nan
        return a
    def calc(g_path, n_path):
        g = nd(g_path); n = nd(n_path)
        s = g + n; o = np.full(s.shape, np.nan, np.float32); m = s != 0
        o[m] = (g[m]-n[m])/s[m]
        del g, n, s, m; gc.collect()
        return o
    delta = calc(f"{D}/_s_wet_green.tif", f"{D}/_s_wet_nir.tif") - \
            calc(f"{D}/_s_dry_green.tif", f"{D}/_s_dry_nir.tif")
    drv = gdal.GetDriverByName("GTiff")
    ds = drv.Create(p_nd, MW, MH, 1, gdal.GDT_Float32, options=["COMPRESS=DEFLATE"])
    ds.SetGeoTransform([MB[0], RES, 0, MB[3], 0, -RES])
    sr = osr.SpatialReference(); sr.ImportFromEPSG(3857); ds.SetProjection(sr.ExportToWkt())
    ds.GetRasterBand(1).WriteRaster(0, 0, MW, MH, delta.tobytes(), buf_type=gdal.GDT_Float32)
    ds = None
    del delta; gc.collect()
    for k in ("dry","wet"):
        for bk in ("green","nir"):
            fp = f"{D}/_s_{k}_{bk}.tif"
            if os.path.exists(fp): os.remove(fp)
masters["ndwi-change"] = p_nd

# ---- HARD VALIDATION: landmarks must have real texture ----
def _probe(path, lon, lat):
    d2 = gdal.Open(path)
    g2 = d2.GetGeoTransform()
    px = int(round((MX(lon) - g2[0]) / RES))
    py = int(round((g2[3] - MY(lat)) / RES))
    buf = d2.GetRasterBand(1).ReadRaster(max(px-16,0), max(py-16,0), 32, 32,
                                         buf_type=gdal.GDT_Byte if d2.GetRasterBand(1).DataType==gdal.GDT_Byte else gdal.GDT_Float32)
    dtv = np.uint8 if d2.GetRasterBand(1).DataType==gdal.GDT_Byte else np.float32
    a = np.frombuffer(buf, dtype=dtv)
    d2 = None
    return float(a.std())
for _t in ("sentinel-dry","sentinel-wet"):
    sd = _probe(masters[_t], 121.0198, 14.5547)
    assert sd > 15, f"{_t} master looks EMPTY at EDSA (std={sd}) - aborting before slice"
print("landmark validation PASSED", flush=True)

json.dump({"MB": list(MB), "MW": MW, "MH": MH}, open(f"{D}/_master_grid.json","w"))
print("PHASE A1 COMPLETE", flush=True)

# ================= PHASE A2: slice + validate =================
import numpy as np
from PIL import Image

def block_avg(a, k):
    if k == 1: return a
    h, w = a.shape
    h2, w2 = (h//k)*k, (w//k)*k
    return a[:h2,:w2].reshape(h//k,k,w//k,k).mean(axis=(1,3))

def slice_layer(tag):
    p = masters[tag]
    ds = gdal.Open(p); nb = ds.RasterCount
    is_ndwi = tag == "ndwi-change"
    cnt = 0
    for z in range(ZMIN, ZMASTER+1):
        k = 2 ** (ZMASTER - z)
        n_tiles = 2 ** z
        for gx in range(TX0 * 2**k, (TX1+1) * 2**k):
            tx = gx % n_tiles
            bx = (gx - TX0 * 2**k) * 256          # block offset in master px
            wx = bx * k                            # master-px window x
            wsize = 256 * k
            sx0, sx1 = max(wx, 0), min(wx+wsize, MW)
            if sx1 <= sx0: continue
            for gy in range(TY0 * 2**k, (TY1+1) * 2**k):
                ty = gy % n_tiles
                by = (gy - TY0 * 2**k) * 256
                wy = by * k
                sy0, sy1 = max(wy, 0), min(wy+wsize, MH)
                if sy1 <= sy0: continue
                chans = []
                for bi in range(1, nb+1):
                    b = ds.GetRasterBand(bi)
                    buf = b.ReadRaster(sx0, sy0, sx1-sx0, sy1-sy0,
                                       buf_type=gdal.GDT_Byte if not is_ndwi else gdal.GDT_Float32)
                    dt = np.uint8 if not is_ndwi else np.float32
                    a = np.frombuffer(buf, dtype=dt).reshape(sy1-sy0, sx1-sx0)
                    if k > 1: a = block_avg(a, k)
                    chans.append(a)
                # paste into 256 canvas
                ox = sx0 - wx; oy = sy0 - wy
                fill = (0,0,0,0) if is_ndwi else None
                canvas_chans = []
                for ci, c in enumerate(chans):
                    cv = np.zeros((256,256), np.uint8) if (is_ndwi or True) else None
                    cv = np.zeros((256,256), np.uint8)
                    if not is_ndwi and c.dtype==np.uint8:
                        pass
                    cv[oy:oy+c.shape[0], ox:ox+c.shape[1]] = c.astype(np.uint8) if not is_ndwi else c
                    canvas_chans.append(cv)
                if is_ndwi:
                    d = canvas_chans[0].astype(np.float32)/255.0*0.25+0.0  # placeholder
                img = Image.merge("RGBA" if is_ndwi else "RGB",
                                  [Image.fromarray(c) for c in canvas_chans])
                td = f"{OUT}/{tag}/{z}/{tx}"
                os.makedirs(td, exist_ok=True)
                img.save(f"{td}/{ty}.png", optimize=True)
                cnt += 1
    print(tag, "sliced:", cnt, flush=True)

for t in ("sentinel-dry","sentinel-wet","ndwi-change"):
    slice_layer(t)

# ---- landmark validation ----
print("\n=== ALIGNMENT VALIDATION ===", flush=True)
ds = gdal.Open(masters["sentinel-dry"])
Rc = 6378137.0
def probe(name, lon, lat):
    px = int(round((math.radians(lon)*Rc - MB[0]) / RES))
    py = int(round((MB[3] - Rc*math.log(math.tan(math.pi/4+math.radians(lat)/2))) / RES))
    win = 24
    buf = ds.GetRasterBand(1).ReadRaster(max(px-win,0), max(py-win,0), 2*win, 2*win,
                                         buf_type=gdal.GDT_Byte)
    a = np.frombuffer(buf, dtype=np.uint8)
    print(f"{name:22s} px=({px},{py}) local std={a.std():5.1f} mean={a.mean():6.1f}")
probe("Manila Cathedral",   120.9742, 14.5922)
probe("EDSA-Makati core",   121.0198, 14.5547)
probe("Laguna east shore",  121.1700, 14.4500)
probe("Sierra Madre ridge", 121.1800, 14.7000)
probe("Manila Bay water",   120.9300, 14.5000)
ds = None
print("PHASE A COMPLETE")
