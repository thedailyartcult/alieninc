"""
Gotham Intelligence - OSINT and sanctions screening routes.
"""
from datetime import datetime
from typing import Optional, List
import httpx
import time
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from panteon.core.auth import SupabaseUser, get_current_user
from panteon.core.sanctions import sanctions_cache, SanctionEntry

router = APIRouter(prefix="/gotham", tags=["Gotham Intelligence"])

# CCTV Camera Cache (5 minutes)
_cctv_cache = {
    "cameras": [],
    "fetched_at": 0,
    "ttl": 300  # 5 minutes
}


class SanctionsSearchRequest(BaseModel):
    query: str
    schema: Optional[str] = None
    limit: int = 25


class SanctionsMatch(BaseModel):
    matched_value: str
    entries: List[dict]


class SanctionsResponse(BaseModel):
    query: str
    schema: Optional[str]
    total: int
    matches: List[dict]
    source: str
    timestamp: str


class IPGeoInfo(BaseModel):
    country: Optional[str] = None
    country_code: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    timezone: Optional[str] = None
    isp: Optional[str] = None
    org: Optional[str] = None
    as_number: Optional[str] = None
    as_name: Optional[str] = None
    is_mobile: Optional[bool] = None
    is_proxy: Optional[bool] = None
    is_hosting: Optional[bool] = None


class IPReputation(BaseModel):
    is_proxy: bool
    is_hosting: bool
    is_mobile: bool
    risk_level: str


class IPResponse(BaseModel):
    ip: str
    geo: Optional[IPGeoInfo] = None
    reputation: Optional[IPReputation] = None
    sanctions_match: Optional[dict] = None
    timestamp: str


class WHOISEntity(BaseModel):
    handle: Optional[str] = None
    roles: Optional[List[str]] = None
    name: Optional[str] = None
    org: Optional[str] = None


class RDAPInfo(BaseModel):
    handle: Optional[str] = None
    name: Optional[str] = None
    status: Optional[List[str]] = None
    events: Optional[List[dict]] = None
    nameservers: Optional[List[str]] = None
    entities: Optional[List[WHOISEntity]] = None


class HTTPInfo(BaseModel):
    status: Optional[int] = None
    headers: Optional[dict] = None
    redirected: Optional[bool] = None
    final_url: Optional[str] = None


class SecurityScore(BaseModel):
    score: int
    max: int
    grade: str


class WHOISResponse(BaseModel):
    domain: str
    rdap: Optional[RDAPInfo] = None
    registration: Optional[str] = None
    expiration: Optional[str] = None
    last_changed: Optional[str] = None
    http: Optional[HTTPInfo] = None
    security_score: Optional[SecurityScore] = None
    sanctions_match: Optional[dict] = None
    timestamp: str


@router.get("/sanctions", response_model=SanctionsResponse)
async def search_sanctions(
    query: str = Query(..., min_length=4, description="Search query"),
    schema: Optional[str] = Query(None, description="Filter by entity schema"),
    limit: int = Query(25, ge=1, le=100, description="Max results"),
    user: SupabaseUser = Depends(get_current_user)
):
    """
    Search OFAC SDN sanctions list.
    Returns entities matching the query with aliases and program details.
    """
    try:
        matches = await sanctions_cache.search(query, schema=schema, limit=limit)
        return SanctionsResponse(
            query=query,
            schema=schema,
            total=len(matches),
            matches=[m.to_dict() for m in matches],
            source="OpenSanctions / US OFAC SDN",
            timestamp=datetime.utcnow().isoformat()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sanctions lookup failed: {str(e)}")


@router.get("/ip", response_model=IPResponse)
async def lookup_ip(
    ip: str = Query(..., description="IP address to lookup"),
    user: SupabaseUser = Depends(get_current_user)
):
    """
    Lookup IP geolocation, reputation, and check against sanctions list.
    """
    import re
    
    # Validate IP format
    ipv4_pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
    ipv6_pattern = r'^[0-9a-fA-F:]+$'
    if not (re.match(ipv4_pattern, ip) or re.match(ipv6_pattern, ip)):
        raise HTTPException(status_code=400, detail="Invalid IP format")

    result = {"ip": ip, "timestamp": datetime.utcnow().isoformat()}

    # 1. Geolocation via ip-api.com (free, no key)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"http://ip-api.com/json/{ip}",
                params={
                    "fields": "status,message,continent,country,countryCode,region,regionName,"
                             "city,zip,lat,lon,timezone,isp,org,as,asname,mobile,proxy,hosting,query"
                }
            )
            if response.status_code == 200:
                geo = response.json()
                if geo.get("status") == "success":
                    result["geo"] = IPGeoInfo(
                        country=geo.get("country"),
                        country_code=geo.get("countryCode"),
                        region=geo.get("regionName"),
                        city=geo.get("city"),
                        lat=geo.get("lat"),
                        lon=geo.get("lon"),
                        timezone=geo.get("timezone"),
                        isp=geo.get("isp"),
                        org=geo.get("org"),
                        as_number=geo.get("as"),
                        as_name=geo.get("asname"),
                        is_mobile=geo.get("mobile"),
                        is_proxy=geo.get("proxy"),
                        is_hosting=geo.get("hosting"),
                    )
    except Exception as e:
        print(f"Warning: IP geolocation failed: {e}")

    # 2. Reputation assessment
    if "geo" in result:
        geo = result["geo"]
        result["reputation"] = IPReputation(
            is_proxy=geo.is_proxy or False,
            is_hosting=geo.is_hosting or False,
            is_mobile=geo.is_mobile or False,
            risk_level="HIGH" if geo.is_proxy else "MEDIUM" if geo.is_hosting else "LOW"
        )

    # 3. OFAC SDN cross-check on ASN/ISP/org
    try:
        candidates = set()
        if result.get("geo") and result["geo"].org:
            candidates.add(result["geo"].org)
        if result.get("geo") and result["geo"].isp:
            candidates.add(result["geo"].isp)
        if result.get("geo") and result["geo"].as_name:
            candidates.add(result["geo"].as_name)

        hits = []
        for value in candidates:
            entries = await sanctions_cache.match_exact(value)
            if entries:
                hits.append({
                    "matched_value": value,
                    "entries": [e.to_dict() for e in entries]
                })

        result["sanctions_match"] = {"source": "OFAC SDN", "hits": hits} if hits else None
    except Exception as e:
        print(f"Warning: Sanctions cross-check failed: {e}")
        result["sanctions_match"] = None

    return IPResponse(**result)


@router.get("/whois", response_model=WHOISResponse)
async def lookup_whois(
    domain: str = Query(..., description="Domain to lookup"),
    user: SupabaseUser = Depends(get_current_user)
):
    """
    Lookup domain WHOIS/RDAP info, HTTP headers, and check against sanctions list.
    """
    import re
    
    # Validate domain format
    if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', domain):
        raise HTTPException(status_code=400, detail="Invalid domain format")

    result = {"domain": domain, "timestamp": datetime.utcnow().isoformat()}

    # 1. RDAP lookup (free, standardized)
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(
                f"https://rdap.org/domain/{domain}",
                headers={"Accept": "application/json"}
            )
            if response.status_code == 200:
                data = response.json()
                entities = []
                for e in data.get("entities", []):
                    vcard = e.get("vcardArray", [None, []])[1] if e.get("vcardArray") else []
                    name = next((v[3] for v in vcard if v[0] == "fn"), None)
                    org = next((v[3] for v in vcard if v[0] == "org"), None)
                    if name or org:
                        entities.append(WHOISEntity(
                            handle=e.get("handle"),
                            roles=e.get("roles"),
                            name=name,
                            org=org
                        ))

                result["rdap"] = RDAPInfo(
                    handle=data.get("handle"),
                    name=data.get("ldhName"),
                    status=data.get("status"),
                    events=[{"action": e.get("eventAction"), "date": e.get("eventDate")} 
                            for e in data.get("events", [])],
                    nameservers=[ns.get("ldhName") for ns in data.get("nameservers", [])],
                    entities=entities
                )

                # Extract key dates
                events = result["rdap"].events or []
                result["registration"] = next((e["date"] for e in events if e["action"] == "registration"), None)
                result["expiration"] = next((e["date"] for e in events if e["action"] == "expiration"), None)
                result["last_changed"] = next((e["date"] for e in events if e["action"] == "last changed"), None)
    except Exception as e:
        print(f"Warning: RDAP lookup failed: {e}")

    # 2. HTTP headers for security scoring
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
            response = await client.head(f"https://{domain}")
            headers = {}
            for h in ["server", "x-powered-by", "x-frame-options", "strict-transport-security",
                      "content-security-policy", "x-content-type-options", "x-xss-protection",
                      "referrer-policy", "permissions-policy"]:
                if h in response.headers:
                    headers[h] = response.headers[h]

            result["http"] = HTTPInfo(
                status=response.status_code,
                headers=headers,
                redirected=response.history[0].status_code in (301, 302) if response.history else False,
                final_url=str(response.url)
            )

            # Security score
            score = 0
            if headers.get("strict-transport-security"):
                score += 2
            if headers.get("content-security-policy"):
                score += 2
            if headers.get("x-frame-options"):
                score += 1
            if headers.get("x-content-type-options"):
                score += 1
            if headers.get("referrer-policy"):
                score += 1

            grade = "A" if score >= 5 else "B" if score >= 3 else "C" if score >= 1 else "F"
            result["security_score"] = SecurityScore(score=score, max=7, grade=grade)
    except Exception as e:
        print(f"Warning: HTTP headers check failed: {e}")

    # 3. OFAC SDN cross-check on RDAP entities
    try:
        candidates = set()
        if result.get("rdap") and result["rdap"].entities:
            for ent in result["rdap"].entities:
                if ent.name:
                    candidates.add(ent.name)
                if ent.org:
                    candidates.add(ent.org)

        hits = []
        for value in candidates:
            entries = await sanctions_cache.match_exact(value)
            if entries:
                hits.append({
                    "matched_value": value,
                    "entries": [e.to_dict() for e in entries]
                })

        result["sanctions_match"] = {"source": "OFAC SDN", "hits": hits} if hits else None
    except Exception as e:
        print(f"Warning: Sanctions cross-check failed: {e}")
        result["sanctions_match"] = None

    return WHOISResponse(**result)


@router.get("/health")
async def health_check():
    """Health check endpoint for Gotham intelligence services."""
    try:
        size = await sanctions_cache.index_size()
        return {
            "status": "healthy",
            "sanctions_index_size": size,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "status": "degraded",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


class CCTVCamera(BaseModel):
    id: str
    lat: float
    lng: float
    name: str
    city: Optional[str] = None
    country: str
    feed_url: str
    source: str


class CCTVResponse(BaseModel):
    total: int
    cameras: List[CCTVCamera]
    timestamp: str


@router.get("/cctv", response_model=CCTVResponse)
async def get_cctv_cameras(
    region: Optional[str] = Query(None, description="Filter by region (uk, us, europe, asia, australia)"),
    lat: Optional[float] = Query(None, description="Latitude for proximity search"),
    lng: Optional[float] = Query(None, description="Longitude for proximity search"),
    radius: Optional[float] = Query(None, description="Radius in km for proximity search"),
    user: SupabaseUser = Depends(get_current_user)
):
    """
    Get worldwide CCTV traffic cameras.
    Supports filtering by region or proximity to coordinates.
    """
    global _cctv_cache
    
    try:
        # Check cache first
        now = time.time()
        if _cctv_cache["cameras"] and (now - _cctv_cache["fetched_at"]) < _cctv_cache["ttl"]:
            cameras = _cctv_cache["cameras"]
        else:
            # Fetch from external APIs
            cameras = []
            
            # UK: Transport for London JamCams
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get('https://api.tfl.gov.uk/Place/Type/JamCam')
                    if response.status_code == 200:
                        data = response.json()
                        for cam in (data or [])[:50]:
                            img_prop = next((p for p in cam.get('additionalProperties', []) if p.get('key') == 'imageUrl'), None)
                            cam_id = cam.get('id', '').replace('JamCams_', '')
                            if cam.get('lat') and cam.get('lon'):
                                cameras.append(CCTVCamera(
                                    id=f"tfl-{cam.get('id')}",
                                    lat=cam['lat'],
                                    lng=cam['lon'],
                                    name=cam.get('commonName', 'London JamCam'),
                                    city='London',
                                    country='UK',
                                    feed_url=img_prop.get('value') if img_prop else f"https://s3-eu-west-1.amazonaws.com/jamcams.tfl.gov.uk/{cam_id}.jpg",
                                    source='TfL'
                                ))
            except Exception as e:
                print(f"Warning: TfL cameras failed: {e}")

            # US: WSDOT Washington State
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get('https://data.wsdot.wa.gov/log/public/cameras.json')
                    if response.status_code == 200:
                        data = response.json()
                        for cam in (data or [])[:50]:
                            loc = cam.get('CameraLocation', {})
                            if loc.get('Latitude') and loc.get('Longitude') and cam.get('ImageURL'):
                                cameras.append(CCTVCamera(
                                    id=f"wsdot-{cam.get('CameraID')}",
                                    lat=loc['Latitude'],
                                    lng=loc['Longitude'],
                                    name=cam.get('Title', 'WSDOT Camera'),
                                    city='Washington',
                                    country='US',
                                    feed_url=cam['ImageURL'],
                                    source='WSDOT'
                                ))
            except Exception as e:
                print(f"Warning: WSDOT cameras failed: {e}")

            # US: Caltrans California
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(
                        'https://caltrans-gis.dot.ca.gov/arcgis/rest/services/CHhighway/CCTV/FeatureServer/0/query',
                        params={'where': '1=1', 'outFields': '*', 'f': 'json'}
                    )
                    if response.status_code == 200:
                        data = response.json()
                        for feature in (data.get('features') or [])[:50]:
                            attrs = feature.get('attributes', {})
                            if attrs.get('latitude') and attrs.get('longitude') and attrs.get('currentImageURL'):
                                cameras.append(CCTVCamera(
                                    id=f"cal-{attrs.get('OBJECTID')}",
                                    lat=attrs['latitude'],
                                    lng=attrs['longitude'],
                                    name=attrs.get('locationName', 'Caltrans'),
                                    city=attrs.get('nearbyPlace') or attrs.get('county') or 'California',
                                    country='US',
                                    feed_url=attrs['currentImageURL'],
                                    source='Caltrans'
                                ))
            except Exception as e:
                print(f"Warning: Caltrans cameras failed: {e}")

            # Cache the results
            _cctv_cache["cameras"] = cameras
            _cctv_cache["fetched_at"] = now
        
        # Filter by region if specified
        if region:
            region_lower = region.lower()
            if region_lower == 'uk':
                cameras = [c for c in cameras if c.country == 'UK']
            elif region_lower == 'us':
                cameras = [c for c in cameras if c.country == 'US']
            elif region_lower == 'europe':
                cameras = [c for c in cameras if c.country in ['UK']]
            elif region_lower == 'asia':
                cameras = [c for c in cameras if c.country in ['JP', 'HK', 'TW']]
            elif region_lower == 'australia':
                cameras = [c for c in cameras if c.country == 'AU']

        # Filter by proximity if coordinates provided
        if lat is not None and lng is not None and radius is not None:
            import math
            def distance(lat1, lon1, lat2, lon2):
                R = 6371
                dlat = math.radians(lat2 - lat1)
                dlon = math.radians(lon2 - lon1)
                a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
                c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
                return R * c
            
            cameras = [c for c in cameras if distance(lat, lng, c.lat, c.lng) <= radius]

        return CCTVResponse(
            total=len(cameras),
            cameras=cameras,
            timestamp=datetime.utcnow().isoformat()
        )
    except Exception as e:
        print(f"Error in CCTV endpoint: {e}")
        return CCTVResponse(
            total=0,
            cameras=[],
            timestamp=datetime.utcnow().isoformat()
        )
