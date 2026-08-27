"""
YONO geospatial decision tools — GDAL-backed physical ground truth.

Pilot region: Luzon, PH (Metro Manila / Laguna de Bay AOI).
Data (staged under backend/geo-data/):
  dem_luzon.tif            — terrain model, EPSG:4326, ~30m
  sentinel_manifest.json   — two cloud-free Sentinel-2 L2A COG scenes (dry/wet season)
  infra.geojson            — OSM critical infrastructure points (hospitals, power)

Every tool returns compact JSON statistics that a YONO agent can cite
directly, so decisions carry verifiable numbers instead of prose.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Optional

import os

import numpy as np
# Import GDAL with stderr muted: some builds emit noisy numpy-ABI tracebacks
# from their optional gdal_array half even when everything we use works fine.
import contextlib as _cl
with _cl.redirect_stderr(open(os.devnull, "w")):
    from osgeo import gdal, ogr, osr
    try:
        gdal.UseExceptions()
    except Exception:
        pass  # degraded builds without a working numpy interop still serve raw IO


def _band_array(band, buf_type=gdal.GDT_Float32):
    """ReadAsArray replacement that avoids gdal_array/_ARRAY_API entirely."""
    buf = band.ReadRaster(0, 0, band.XSize, band.YSize, buf_type=buf_type)
    return np.frombuffer(buf, dtype=np.float32).reshape(band.YSize, band.XSize)


def _window_array(ds, x_off, y_off, x_sz, y_sz, x_buf, y_buf,
                  buf_type=gdal.GDT_Float32):
    buf = ds.ReadRaster(x_off, y_off, max(x_sz, 1), max(y_sz, 1),
                        max(x_buf, 1), max(y_buf, 1), buf_type=buf_type)
    return np.frombuffer(buf, dtype=np.float32).reshape(max(y_buf, 1), max(x_buf, 1))

DATA_DIR = Path(__file__).resolve().parents[2] / "geo-data"
DEM_PATH = DATA_DIR / "dem_luzon.tif"
INFRA_PATH = DATA_DIR / "infra.geojson"
MANIFEST_PATH = DATA_DIR / "sentinel_manifest.json"

AOI_BBOX = [120.85, 14.30, 121.25, 14.80]  # lon_min, lat_min, lon_max, lat_max


def _normalize_bbox(bbox: list[float]) -> list[float]:
    """
    Tolerant AOI parsing: accepts WGS84 boxes as [lon_min,lat_min,lon_max,lat_max]
    (documented order), [lat_min,lon_min,lat_max,lon_max] (what LLMs sometimes emit),
    and any min/max ordering. Returns strict [lon_min,lat_min,lon_max,lat_max].
    """
    if len(bbox) != 4:
        raise ValueError("bbox must be exactly 4 numbers")
    b = [float(v) for v in bbox]
    # If the first value cannot be longitude but the second can, swap axes.
    if abs(b[0]) <= 90 and abs(b[1]) > 90:
        b = [b[1], b[0], b[3], b[2]]
    lons = sorted(b[0::2])
    lats = sorted(b[1::2])
    if not (-180 <= lons[0] and lons[1] <= 180):
        raise ValueError(f"longitudes out of range: {lons}")
    if not (-90 <= lats[0] and lats[1] <= 90):
        raise ValueError(f"latitudes out of range: {lats}")
    return [lons[0], lats[0], lons[1], lats[1]]


# ────────────────────────────────────────────────────────────────────
# Internals
# ────────────────────────────────────────────────────────────────────

def _open_dem() -> gdal.Dataset:
    if not DEM_PATH.exists():
        raise FileNotFoundError(f"DEM not staged: {DEM_PATH}")
    return gdal.Open(str(DEM_PATH))


def _haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _sample_elevations(ds: gdal.Dataset, lons: np.ndarray, lats: np.ndarray) -> np.ndarray:
    """Bilinear elevation samples at WGS84 coordinates."""
    gt = ds.GetGeoTransform()
    band = ds.GetRasterBand(1)
    cols = (lons - gt[0]) / gt[1]
    rows = (lats - gt[3]) / gt[5]
    arr = _band_array(band)
    h, w = arr.shape
    c0 = np.clip(np.floor(cols).astype(int), 0, w - 2)
    r0 = np.clip(np.floor(rows).astype(int), 0, h - 2)
    dc = np.clip(cols - c0, 0, 1)
    dr = np.clip(rows - r0, 0, 1)
    v00 = arr[r0, c0]
    v01 = arr[r0, c0 + 1]
    v10 = arr[r0 + 1, c0]
    v11 = arr[r0 + 1, c0 + 1]
    out = (v00 * (1 - dc) * (1 - dr) + v01 * dc * (1 - dr)
           + v10 * (1 - dc) * dr + v11 * dc * dr)
    out[out < -1e30] = np.nan   # raster NoData -> NaN (sea / unsampled)
    return out


def _read_band_window(url: str, bbox: list[float], max_px: int = 1100):
    """
    Read an AOI window from a remote COG via /vsicurl/.
    bbox is WGS84 [lon_min, lat_min, lon_max, lat_max]; the raster may be
    projected (Sentinel-2 COGs are UTM), so we transform first and clip.
    Returns (array, coverage_fraction_of_bbox).
    """
    ds = gdal.Open(f"/vsicurl/{url}")
    gt = ds.GetGeoTransform()

    src = osr.SpatialReference(); src.ImportFromEPSG(4326)
    src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    dst = osr.SpatialReference(wkt=ds.GetProjection())
    dst.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    ct = osr.CoordinateTransformation(src, dst)

    corners = [(bbox[0], bbox[1]), (bbox[0], bbox[3]),
               (bbox[2], bbox[1]), (bbox[2], bbox[3])]
    tp = [ct.TransformPoint(lon, lat) for lon, lat in corners]
    xs = [p[0] for p in tp]; ys = [p[1] for p in tp]

    inv = gdal.InvGeoTransform(gt)
    u0, v0 = gdal.ApplyGeoTransform(inv, min(xs), max(ys))
    u1, v1 = gdal.ApplyGeoTransform(inv, max(xs), min(ys))

    req_w, req_h = abs(u1 - u0), abs(v1 - v0)
    x_off = max(0, int(min(u0, u1)))
    y_off = max(0, int(min(v0, v1)))
    x_end = min(ds.RasterXSize, int(max(u0, u1)))
    y_end = min(ds.RasterYSize, int(max(v0, v1)))
    x_sz, y_sz = x_end - x_off, y_end - y_off
    if x_sz < 2 or y_sz < 2:
        # Build a WGS84 hint of what the scene actually covers so an agent can retry.
        back = osr.CoordinateTransformation(dst, src)
        c00 = back.TransformPoint(gt[0], gt[3])[:2]
        c11 = back.TransformPoint(gt[0]+gt[1]*ds.RasterXSize, gt[3]+gt[5]*ds.RasterYSize)[:2]
        ds = None
        lo_x, hi_x = sorted((c00[0], c11[0]))
        lo_y, hi_y = sorted((c00[1], c11[1]))
        raise RuntimeError(
            f"AOI {bbox} does not intersect scene footprint "
            f"[{lo_x:.2f}, {lo_y:.2f}, {hi_x:.2f}, {hi_y:.2f}] (lon_min, lat_min, lon_max, lat_max)"
        )

    step = max(1, max(x_sz, y_sz) // max_px)
    arr = _window_array(ds, x_off, y_off, x_sz, y_sz,
                        x_sz // step, y_sz // step)
    ds = None
    coverage = (x_sz * y_sz) / max(req_w * req_h, 1e-9)
    return arr, min(coverage, 1.0)


def _nd_index(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    denom = a + b
    out = np.full(a.shape, np.nan, dtype=np.float32)
    m = denom != 0
    out[m] = (a[m] - b[m]) / denom[m]
    return out


def _load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError("sentinel_manifest.json not staged")
    return json.load(open(MANIFEST_PATH))


# ────────────────────────────────────────────────────────────────────
# Public tool implementations
# ────────────────────────────────────────────────────────────────────

def terrain_profile(
    lat1: float, lon1: float, lat2: float, lon2: float, samples: int = 64
) -> dict:
    """Elevation profile between two WGS84 points over the staged DEM."""
    samples = max(8, min(int(samples), 256))
    lons = np.linspace(float(lon1), float(lon2), samples)
    lats = np.linspace(float(lat1), float(lat2), samples)

    seg = np.array([_haversine_m(lons[i], lats[i], lons[i + 1], lats[i + 1])
                    for i in range(samples - 1)])
    dist = np.concatenate([[0], np.cumsum(seg)])

    ds = _open_dem()
    elev = _sample_elevations(ds, lons, lats)
    ds = None

    land = ~np.isnan(elev)
    if not land.any():
        return {"error": "no land samples along line (open water / outside DEM)"}

    lelev = elev[land]
    ldist = dist[land]
    grades = np.diff(lelev) / np.maximum(np.diff(ldist), 1e-6) * 100.0
    series_idx = np.where(land)[0][:: max(1, samples // 32)]

    return {
        "start": [float(lon1), float(lat1)],
        "end": [float(lon2), float(lat2)],
        "distance_km": round(dist[-1] / 1000.0, 2),
        "land_samples": int(land.sum()),
        "water_or_nodata_samples": int((~land).sum()),
        "min_elev_m": round(float(lelev.min()), 1),
        "max_elev_m": round(float(lelev.max()), 1),
        "mean_elev_m": round(float(lelev.mean()), 1),
        "max_grade_pct": round(float(np.abs(grades).max()), 1) if len(grades) else None,
        "elevation_series_m": [
            None if np.isnan(elev[i]) else round(float(elev[i]), 1) for i in series_idx],
        "source": "AWS Terrain Tiles (SRTM-derived)",
    }


def exposure_scan(elevation_threshold_m: float = 5.0, kinds: Optional[list[str]] = None) -> dict:
    """
    Scan critical-infrastructure points against terrain elevation.
    Returns counts and worst-exposed assets below the threshold.
    """
    thr = float(elevation_threshold_m)
    fc = json.load(open(INFRA_PATH))
    feats = fc["features"]
    if kinds:
        def _norm_kind(k):
            k = str(k).lower().strip()
            return k[:-1] if k.endswith("s") else k
        want = {_norm_kind(k) for k in kinds}
        feats = [f for f in feats if _norm_kind(f["properties"]["kind"]) in want]

    lons = np.array([f["geometry"]["coordinates"][0] for f in feats])
    lats = np.array([f["geometry"]["coordinates"][1] for f in feats])

    ds = _open_dem()
    elevs = _sample_elevations(ds, lons, lats)
    gt = ds.GetGeoTransform()
    band_arr = _band_array(ds.GetRasterBand(1))
    ds = None

    land = band_arr[band_arr > 0]
    aoi_below_pct = float((land <= thr).mean() * 100.0)

    exposed = []
    by_kind: dict[str, int] = {}
    unsampled = 0
    for f, e in zip(feats, elevs):
        if np.isnan(e):
            unsampled += 1
            continue
        if e <= thr:
            k = f["properties"]["kind"]
            by_kind[k] = by_kind.get(k, 0) + 1
            exposed.append({
                "name": f["properties"]["name"],
                "kind": k,
                "elev_m": round(float(e), 1),
                "lon": f["geometry"]["coordinates"][0],
                "lat": f["geometry"]["coordinates"][1],
            })
    exposed.sort(key=lambda x: x["elev_m"])

    return {
        "threshold_m": thr,
        "assets_checked": len(feats),
        "assets_below_threshold": len(exposed),
        "assets_unsampled_no_dem": unsampled,
        "by_kind": by_kind,
        "aoi_land_below_threshold_pct": round(aoi_below_pct, 1),
        "most_exposed": exposed[:12],
        "aoi_bbox": AOI_BBOX,
        "sources": ["OSM", "AWS Terrain Tiles (SRTM-derived)"],
    }


def change_detection(
    index: str = "NDWI",
    threshold: float = 0.15,
    bbox: Optional[list[float]] = None,
) -> dict:
    """
    Compare dry-season vs wet-season Sentinel-2 scenes over an AOI and
    quantify surface change in NDWI (water) or NDVI (vegetation).
    """
    index = index.upper()
    if index not in ("NDWI", "NDVI"):
        return {"error": "index must be NDWI or NDVI"}
    man = _load_manifest()
    if "dry" not in man or "wet" not in man:
        return {"error": "manifest missing scenes"}
    try:
        bbox = _normalize_bbox(bbox) if bbox else list(AOI_BBOX)
    except ValueError as exc:
        return {"error": str(exc)}
    thr = float(threshold)

    coverages = []

    def pair(scene: dict):
        a, ca = _read_band_window(scene["green"] if index == "NDWI" else scene["red"], bbox)
        b, cb = _read_band_window(scene["nir"], bbox)
        for x in (a, b):
            x[x < -1e30] = np.nan
        coverages.append((ca + cb) / 2)
        return a, b

    ga, na = pair(man["dry"])
    gw, nw = pair(man["wet"])
    n = min(ga.size, gw.size)
    ia = _nd_index(ga.ravel()[:n], na.ravel()[:n])
    iw = _nd_index(gw.ravel()[:n], nw.ravel()[:n])

    valid = ~(np.isnan(ia) | np.isnan(iw))
    delta = iw[valid] - ia[valid]

    px_area_km2 = None
    try:
        src = osr.SpatialReference(); src.ImportFromEPSG(4326)
        lin = _haversine_m(bbox[0], bbox[1], bbox[0], bbox[3])
        wid = _haversine_m(bbox[0], bbox[1], bbox[2], bbox[1])
        px_area_km2 = (lin * wid) / n / 1e6
    except Exception:
        pass

    changed = int((np.abs(delta) > thr).sum())
    result = {
        "index": index,
        "threshold": thr,
        "dry_scene": {"id": man["dry"]["item_id"], "date": man["dry"]["datetime"][:10],
                      "cloud_pct": round(man["dry"]["cloud_cover"], 1)},
        "wet_scene": {"id": man["wet"]["item_id"], "date": man["wet"]["datetime"][:10],
                      "cloud_pct": round(man["wet"]["cloud_cover"], 1)},
        "samples_compared": int(valid.sum()),
        "mean_dry": round(float(np.nanmean(ia[valid])), 4),
        "mean_wet": round(float(np.nanmean(iw[valid])), 4),
        "mean_change": round(float(delta.mean()), 4),
        "changed_px_beyond_threshold": changed,
        "changed_fraction_pct": round(changed / max(valid.sum(), 1) * 100.0, 2),
        "aoi_bbox": bbox,
        "aoi_coverage_in_scene_pct": round(min(coverages) * 100.0, 1),
        "interpretation": (
            "surface-water increase" if index == "NDWI" and delta.mean() > 0
            else "surface-water decrease" if index == "NDWI"
            else "vegetation increase" if delta.mean() > 0 else "vegetation loss"
        ),
        "source": "Sentinel-2 L2a via Element84 EarthSearch (AWS open data)",
    }
    if px_area_km2:
        result["approx_changed_area_km2"] = round(changed * px_area_km2, 1)
    return result


# ────────────────────────────────────────────────────────────────────
# Viewshed / line-of-sight (terrain physics, curvature-corrected)
# ────────────────────────────────────────────────────────────────────

_EARTH_R = 6_371_000.0
_K_REFRAC = 4.0 / 3.0          # standard atmospheric refraction factor


def _dem_window(lat, lon, radius_m, cap_px=420):
    """Read a square DEM window centred on the observer; return arr + geotransform."""
    ds = _open_dem()
    gt = ds.GetGeoTransform()
    dlat = radius_m / 111_320.0
    dlon = radius_m / (111_320.0 * max(math.cos(math.radians(lat)), 0.2))
    x0 = int((lon - dlon - gt[0]) / gt[1]); x1 = int((lon + dlon - gt[0]) / gt[1])
    # rows grow southward: smaller row index == more north
    yr_a = int((lat - dlat - gt[3]) / gt[5]); yr_b = int((lat + dlat - gt[3]) / gt[5])
    sx0, sx1 = max(min(x0, x1), 0), min(max(x0, x1), ds.RasterXSize)
    sy0, sy1 = max(min(yr_a, yr_b), 0), min(max(yr_a, yr_b), ds.RasterYSize)
    if sx1 <= sx0 or sy1 <= sy0:
        ds = None
        raise RuntimeError("observer outside staged DEM coverage")
    w, h = sx1 - sx0, sy1 - sy0
    step = max(1, max(w, h) // cap_px)
    buf = ds.GetRasterBand(1).ReadRaster(sx0, sy0, w, h,
                                         w // step, h // step,
                                         buf_type=gdal.GDT_Float32)
    arr = np.frombuffer(buf, dtype=np.float32).reshape(h//step, w//step).copy()
    arr[arr < -1e30] = np.nan
    # exact sub-window geotransform
    gt2 = (gt[0] + sx0*gt[1], gt[1]*step, 0,
           gt[3] + sy0*gt[5], 0, gt[5]*step)
    ds = None
    return arr, gt2


def _los_polygon(lat, lon, alt_agl_m, radius_m, n_bearings=90, n_steps=140):
    """Ray-cast visibility; returns (visible-range polygon, stats)."""
    dem, gt = _dem_window(lat, lon, radius_m)
    h, w = dem.shape
    px_size = abs(gt[1]) * 111_320.0 * math.cos(math.radians(lat))   # m per px (approx)

    obs_row = (lat - gt[3]) / gt[5]
    obs_col = (lon - gt[0]) / gt[1]

    def cell_elev(r, c):
        r = np.atleast_1d(r); c = np.atleast_1d(c)
        r0 = np.clip(np.floor(r).astype(int), 0, h-2)
        c0 = np.clip(np.floor(c).astype(int), 0, w-2)
        fr = np.clip(r - r0, 0, 1)
        fc = np.clip(c - c0, 0, 1)
        return (dem[r0, c0]*(1-fr)*(1-fc) + dem[r0, c0+1]*fr*(1-fc) +
                dem[r0+1, c0]*(1-fr)*fc + dem[r0+1, c0+1]*fr*fc)

    steps = np.linspace(1, n_steps, n_steps)
    frac = steps / n_steps
    dist = frac * radius_m                                   # metres along ray
    curv = dist**2 / (2 * _EARTH_R * _K_REFRAC)              # curvature drop (refraction-adjusted)

    bearings = np.linspace(0, 360, n_bearings, endpoint=False)
    vis_angles = np.full(n_bearings, -999.0)
    max_range = np.zeros(n_bearings)
    poly_pts = []

    cosb = np.cos(np.radians(bearings))[:, None]
    sinb = np.sin(np.radians(bearings))[:, None]

    # metres-per-degree at this latitude
    mpd_lat = 111_320.0
    mpd_lon = 111_320.0 * math.cos(math.radians(lat))

    obs_elev_cell = cell_elev(np.array([[obs_row]]), np.array([[obs_col]]))[0, 0]
    obs_h = (0.0 if np.isnan(obs_elev_cell) else float(obs_elev_cell)) + alt_agl_m

    for si in range(n_steps):
        d = dist[si]
        dlat_si = math.radians(0)  # placeholder no-op
        rlats = lat + (sinb[:, 0] * d) / mpd_lat * (mpd_lat/111320.0)  # keep degrees correct below
        # correct degree conversion:
        rlats = lat + (sinb[:, 0] * d) / 111_320.0
        rlons = lon + (cosb[:, 0] * d) / (111_320.0 * math.cos(math.radians(lat)))
        rr = obs_row + (sinb[:, 0] * d) / px_size
        rc = obs_col + (cosb[:, 0] * d) / px_size
        inside = (rr >= 0) & (rr <= h-1) & (rc >= 0) & (rc <= w-1)
        terr = cell_elev(rr, rc)
        terr = np.where(np.isnan(terr), np.nanmax(dem)+500, terr)
        target_angle = (terr + curv[si] - obs_h) / np.maximum(d, 1.0)
        newly_visible = inside & (target_angle > vis_angles) & (target_angle >= -50)
        max_range[newly_visible] = d
        vis_angles = np.where(newly_visible, target_angle, vis_angles)

    vis_frac = float((max_range > 0).mean())
    # polygon: centre -> per-bearing outer edge (use max_range, min 50 m)
    pts = [[lon, lat]]
    for b_idx, br in enumerate(bearings):
        r_m = max(max_range[b_idx], 30.0)
        rad = math.radians(br)
        pts.append([lon + math.sin(rad)*r_m/(111_320.0*math.cos(math.radians(lat))),
                    lat + math.cos(rad)*r_m/111_320.0])
    pts.append(pts[1])
    stats = {
        "observer": {"lat": lat, "lon": lon, "alt_agl_m": alt_agl_m},
        "radius_m": radius_m,
        "visible_area_pct": round(vis_frac * 100.0, 1),
        "terrain_limited_coverage_pct": round(float(max_range.mean())/float(max_range.max())*100.0, 1) if max_range.max() > 0 else 0.0,
        "max_visibility_km": round(float(max_range.max())/1000.0, 2),
        "mean_visibility_km": round(float(max_range.mean())/1000.0, 2),
        "blocked_sectors": [
            {"from_deg": round(float(bearings[i]), 0), "to_deg": round(float(bearings[(i+1) % n_bearings]), 0)}
            for i in range(n_bearings) if max_range[i] <= 30.0
        ][:12],
        "physics": f"DEM terrain occlusion, earth-curvature corrected (k={_K_REFRAC})",
        "source": "SRTM-derived DEM",
    }
    return pts, stats


def viewshed(lat: float, lon: float, alt_agl_m: float = 1.7,
             radius_m: float = 5000) -> dict:
    """
    Terrain visibility from an observer point (ground person, ship mast,
    rooftop, aircraft). alt_agl_m = observer height ABOVE local ground;
    for aircraft pass altitude-above-terrain estimate (or MSL minus ground).
    Returns visibility polygon + statistics.
    """
    lat, lon = float(lat), float(lon)
    alt_agl_m = float(alt_agl_m)
    radius_m = max(300.0, min(float(radius_m), 30_000.0))
    try:
        pts, stats = _los_polygon(lat, lon, alt_agl_m, radius_m)
    except RuntimeError as exc:
        return {"error": str(exc)}
    stats["polygon"] = [[round(a, 5), round(b, 5)] for a, b in pts[1:-1]][::2]
    stats["directive"] = {"op": "viewshed", "center": [lon, lat],
                          "polygon": stats["polygon"]}
    return stats


def line_of_sight(lat1, lon1, alt1_m, lat2, lon2, alt2_m=1.7) -> dict:
    """Point-to-point line-of-sight with obstruction report."""
    lat1, lon1, lat2, lon2 = map(float, (lat1, lon1, lat2, lon2))
    dist = _haversine_m(lon1, lat1, lon2, lat2)
    if dist < 1:
        return {"error": "identical points"}
    n = max(32, min(int(dist / 25), 400))
    lats = np.linspace(lat1, lat2, n)
    lons = np.linspace(lon1, lon2, n)
    ds = _open_dem()
    terr = _sample_elevations(ds, lons, lats)
    ds = None
    d = np.linspace(0, dist, n)
    curv = d**2 / (2*_EARTH_R*_K_REFRAC)
    h1 = terr[0] + alt1_m
    h2 = terr[-1] + alt2_m
    line = h1 + (h2-h1)*(d/dist) + curv
    clear = line >= (np.nan_to_num(terr, nan=1e9))
    first_block = None
    if not bool(clear[1:-1].all()):
        idx = int(np.argmax(~clear[1:-1])) + 1
        first_block = {"at_km": round(float(d[idx])/1000.0, 2),
                       "terrain_m": round(float(terr[idx]), 1)}
    return {
        "from": [lon1, lat1, round(float(terr[0]), 1)],
        "to": [lon2, lat2, round(float(terr[-1]), 1)],
        "distance_km": round(dist/1000.0, 2),
        "line_of_sight": bool(clear.all()),
        "first_obstruction": first_block,
        "clearance_margin_m": round(float(min(line - np.nan_to_num(terr, nan=-1e9))), 1),
        "physics": "curvature + refraction corrected",
        "source": "SRTM-derived DEM",
    }

# ────────────────────────────────────────────────────────────────────
# Flood-zone exposure (cross-reference infra against extracted polygons)
# ────────────────────────────────────────────────────────────────────

_FLOOD_ZONES_PATH = DATA_DIR / "flood_zones.geojson"


def _pip(lon, lat, rings):
    outer = rings[0]
    inside = False
    n = len(outer)
    j = n - 1
    for i in range(n):
        xi, yi = outer[i][0], outer[i][1]
        xj, yj = outer[j][0], outer[j][1]
        if (yi > lat) != (yj > lat):
            xint = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lon < xint:
                inside = not inside
        j = i
    return inside


def flood_exposure(kinds=None) -> dict:
    """Which critical-infrastructure points fall inside extracted flood zones."""
    if not _FLOOD_ZONES_PATH.exists():
        return {"error": "flood_zones.geojson not generated yet"}
    fc = json.load(open(_FLOOD_ZONES_PATH))
    zones = []
    for f in fc["features"]:
        g = f["geometry"]
        if g["type"] != "Polygon":
            continue
        zones.append({"rings": g["coordinates"], "km2": f["properties"].get("area_km2", 0)})
    infra_fc = json.load(open(INFRA_PATH))
    feats = infra_fc["features"]
    if kinds:
        def _norm_kind(k):
            k = str(k).lower().strip()
            return k[:-1] if k.endswith("s") else k
        want = {_norm_kind(k) for k in kinds}
        feats = [f for f in feats if _norm_kind(f["properties"]["kind"]) in want]

    affected, by_kind = [], {}
    for f in feats:
        lon, lat = f["geometry"]["coordinates"]
        props = f["properties"]
        for z in zones:
            if z["rings"][0] and _pip(lon, lat, z["rings"]):
                by_kind[props["kind"]] = by_kind.get(props["kind"], 0) + 1
                affected.append({"name": props["name"], "kind": props["kind"],
                                 "lat": lat, "lon": lon,
                                 "zone_km2": z["km2"]})
                break
    affected.sort(key=lambda a: -a["zone_km2"])
    return {
        "zones_checked": len(zones),
        "assets_checked": len(feats),
        "assets_affected": len(affected),
        "by_kind": by_kind,
        "affected_assets": affected[:15],
        "note": "Zones = surface-water increase (NDWI dry→wet). Permanent water bodies included.",
        "source": "Sentinel-2 NDWI delta polygons",
    }

# ────────────────────────────────────────────────────────────────────
# YONO agent-tool registration (OpenAI function-calling format)
# ────────────────────────────────────────────────────────────────────

GEO_TOOLS: list[dict[str, Any]] = [
    {
        "name": "geo_terrain_profile",
        "description": (
            "Elevation profile between two WGS84 points over Luzon pilot DEM. "
            "Use for route feasibility, flood-prone segments, grade limits."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "lat1": {"type": "number"}, "lon1": {"type": "number"},
                "lat2": {"type": "number"}, "lon2": {"type": "number"},
                "samples": {"type": "integer", "default": 64},
            },
            "required": ["lat1", "lon1", "lat2", "lon2"],
        },
    },
    {
        "name": "geo_exposure_scan",
        "description": (
            "Scan critical infrastructure (hospitals, substations, aerodromes) "
            "against an elevation threshold inside the Luzon AOI. Returns counts, "
            "per-kind breakdown and the most-exposed named assets."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "elevation_threshold_m": {"type": "number", "default": 5.0},
                "kinds": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    {
        "name": "geo_flood_exposure",
        "description": (
            "Cross-reference critical infrastructure (hospitals, substations, "
            "aerodromes) with the extracted surface-water-change polygons. "
            "Returns which named assets sit inside newly flooded ground."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "kinds": {"type": "array", "items": {"type": "string"}}
            }
        },
    },
    {
        "name": "geo_viewshed",
        "description": (
            "Terrain visibility polygon from an observer (person, ship mast, "
            "rooftop, aircraft). alt_agl_m is height ABOVE local ground; for "
            "aircraft use altitude above terrain. Curvature-corrected."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "lat": {"type": "number"}, "lon": {"type": "number"},
                "alt_agl_m": {"type": "number", "default": 1.7},
                "radius_m": {"type": "number", "default": 5000}
            },
            "required": ["lat", "lon"]
        },
    },
    {
        "name": "geo_line_of_sight",
        "description": (
            "Point-to-point line-of-sight between two WGS84 points with "
            "obstruction report (first blocker location, clearance margin)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "lat1": {"type": "number"}, "lon1": {"type": "number"},
                "alt1_m": {"type": "number", "default": 1.7},
                "lat2": {"type": "number"}, "lon2": {"type": "number"},
                "alt2_m": {"type": "number", "default": 1.7}
            },
            "required": ["lat1", "lon1", "lat2", "lon2"]
        },
    },
    {
        "name": "geo_change_detection",
        "description": (
            "Compare dry vs wet season Sentinel-2 scenes over the Luzon AOI. "
            "NDWI quantifies surface-water change (flooding), NDVI vegetation change. "
            "Returns means, changed fraction and approximate affected area."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "index": {"type": "string", "enum": ["NDWI", "NDVI"], "default": "NDWI"},
                "threshold": {"type": "number", "default": 0.15},
                "bbox": {"type": "array", "items": {"type": "number"},
                         "minItems": 4, "maxItems": 4},
            },
        },
    },
]


async def execute_geo_tool(tool_name: str, arguments: dict) -> dict:
    """Dispatcher used by OntologyToolExecutor; sync work runs inline."""
    try:
        if tool_name == "geo_terrain_profile":
            return terrain_profile(**arguments)
        if tool_name == "geo_exposure_scan":
            return exposure_scan(**arguments)
        if tool_name == "geo_change_detection":
            return change_detection(**arguments)
        if tool_name == "geo_flood_exposure":
            return flood_exposure(**arguments)
        if tool_name == "geo_viewshed":
            return viewshed(**arguments)
        if tool_name == "geo_line_of_sight":
            return line_of_sight(**arguments)
        return {"error": f"Unknown geo tool: {tool_name}"}
    except Exception as e:  # surfaced into LLM context like other tools
        return {"error": f"Geo tool failed: {e}"}
