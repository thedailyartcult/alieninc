"""
Sims Suite proxy + War Ontology bridge — forwards Kriegspiel war-simulation
requests to the standalone Alien Inc Sims Gateway service
(sims-gateway.service, port 8090) and emits Palantir-style ontology objects
into the Spinal Cracker semantic layer after every run.

Read-only research endpoints + battle execution are available to any
authenticated user; the self-improvement endpoint (POST research/improve),
which mutates the learning state, is gated to editor role and above.

Explicit routes (kriegspiel run/campaign, ontology bootstrap/graph) are
declared BEFORE the catch-all so they win route matching.
"""
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from panteon.core.auth import SupabaseUser, get_current_user
from panteon.core.database import get_db
from panteon.war_ontology import emit_battle_report, graph_snapshot

router = APIRouter(prefix="/sims", tags=["Sims Suite"])

GATEWAY_URL = "http://localhost:8090"
ROLE_LEVELS = {"viewer": 0, "editor": 1, "admin": 2, "superadmin": 3}

# Paths under this prefix may mutate learning state.
MUTATING_PATHS = ("research/improve",)

HOP_BY_HOP = {"content-length", "transfer-encoding", "connection", "keep-alive"}


async def _gateway(method: str, path: str, request: Request | None = None,
                   json_body=None) -> dict:
    """Call the sims gateway and return parsed JSON (raises 502 on failure)."""
    url = f"{GATEWAY_URL}/api/{path}"
    headers = {"Content-Type": "application/json"}
    params = dict(request.query_params) if request is not None else {}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=5.0)) as client:
            resp = await client.request(method, url, headers=headers,
                                        params=params, json=json_body)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Sims gateway unreachable: {exc}") from exc
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text[:500])
    return resp.json()


async def _emit_ontology(db: AsyncSession, report: dict, user: SupabaseUser,
                         mode: str, source_event: dict | None = None,
                         battlefield: str | None = None) -> dict:
    try:
        real_context = None
        try:
            from panteon.real_world import resolve_baselines
            real_context = await resolve_baselines(db, battlefield or report.get("battlefield") or "")
        except Exception:
            real_context = None
        summary = await emit_battle_report(db, report, mode=mode, source_event=source_event,
                                           real_context=real_context)
        if real_context and (real_context.get("red_personnel") or real_context.get("blue_personnel")):
            summary["real_anchored"] = {
                "red": {"iso3": real_context.get("red_iso"),
                        "personnel": real_context.get("red_personnel")},
                "blue": {"iso3": real_context.get("blue_iso"),
                         "personnel": real_context.get("blue_personnel")},
            }
            try:
                from panteon.real_world import estimate_absolute_casualties
                summary["est_casualties_soldiers"] = estimate_absolute_casualties(
                    report, real_context)
            except Exception:
                pass
        await graph_action_record(db, summary, report, user)
        return summary
    except Exception as exc:  # ontology must never break a sim response
        return {"emitted": False, "error": str(exc)[:300]}


async def graph_action_record(db: AsyncSession, summary: dict, report: dict,
                              user: SupabaseUser) -> None:
    from panteon.war_ontology import record_action_execution
    objects = summary.get("objects") or {}
    await record_action_execution(
        db, theater_object_id=objects.get("theater"),
        parameters={"battlefield": report.get("battlefield"),
                    "scenarios": report.get("scenarios_run") or report.get("campaigns"),
                    "seed": report.get("seed")},
        result={"assessment_pk": (summary.get("primary_keys") or {}).get("assessment"),
                "dominant_winner": summary.get("dominant_winner")},
        executed_by=user.email)


# --------------------------------------------------------------------------
# Ontology endpoints (Palantir-style semantics over sc_* tables)
# --------------------------------------------------------------------------

@router.post("/ontology/bootstrap")
async def sims_ontology_bootstrap(user: SupabaseUser = Depends(get_current_user),
                                  db: AsyncSession = Depends(get_db)):
    from panteon.war_ontology import ensure_war_ontology
    return await ensure_war_ontology(db)


@router.get("/ontology/graph")
async def sims_ontology_graph(limit: int = 600,
                              user: SupabaseUser = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    limit = max(1, min(limit, 3000))
    return await graph_snapshot(db, limit=limit)


@router.post("/ontology/ingest-real")
async def sims_ingest_real(request: Request,
                           user: SupabaseUser = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    """
    Manual refresh of REAL-WORLD data: pulls official World Bank statistics
    (population, armed forces personnel, military expenditure) + capital
    coordinates for theater parties and upserts world_country ontology objects.
    Editor+ role (writes to the semantic layer).
    """
    if ROLE_LEVELS.get(user.role, 0) < ROLE_LEVELS["editor"]:
        raise HTTPException(status_code=403, detail="Editor role required for real-data ingestion")
    from panteon.real_world import ALL_PARTIES, ingest_real_countries
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    isos = body.get("countries") or ALL_PARTIES
    try:
        return await ingest_real_countries(db, isos=isos)
    except Exception as exc:
        raise HTTPException(status_code=502,
                            detail=f"Real-world ingestion failed: {exc}") from exc


@router.get("/ontology/real")
async def sims_real_summary(user: SupabaseUser = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    """Summary of ingested REAL nations currently in the ontology."""
    from sqlalchemy import select as _select
    from panteon.spinal_craker.models import Object, ObjectType
    from panteon.real_world import THEATER_PARTIES

    row = (await db.execute(
        _select(ObjectType.id).where(ObjectType.name == "world_country")
    )).scalar_one_or_none()
    if row is None:
        return {"ingested": False, "countries": []}
    objs = (await db.execute(
        _select(Object).where(Object.object_type_id == str(row))
    )).scalars().all()
    countries = []
    for o in objs:
        p = o.properties or {}
        parties_to = [t for t, cs in THEATER_PARTIES.items()
                      if (p.get("iso3") or "").upper() in {c.upper() for c in cs}]
        countries.append({
            "iso3": p.get("iso3"), "name": p.get("name"),
            "population": p.get("population"), "population_year": p.get("population_year"),
            "armed_forces_personnel": p.get("armed_forces_personnel"),
            "military_expenditure_usd": p.get("military_expenditure_usd"),
            "lat": p.get("lat"), "lng": p.get("lng"),
            "parties_to": parties_to, "ingested_at": p.get("ingested_at"),
        })
    countries.sort(key=lambda c: -(c.get("armed_forces_personnel") or 0))
    return {"ingested": True, "count": len(countries), "countries": countries}


@router.get("/ontology/arsenal")
async def sims_arsenal_query(country: str | None = None, category: str | None = None,
                             q: str | None = None, limit: int = 30, offset: int = 0,
                             user: SupabaseUser = Depends(get_current_user)):
    """
    LIVE read-only query into Alien Inc's proprietary a-san weapon catalog.
    Nothing is copied or logged; results are served only to authenticated users.
    """
    from panteon import arsenal
    return arsenal.query_entries(country=country, category=category, q=q,
                                 limit=limit, offset=offset)


@router.post("/ontology/arsenal/link-flagships")
async def sims_arsenal_link_flagships(request: Request,
                                      user: SupabaseUser = Depends(get_current_user),
                                      db: AsyncSession = Depends(get_db)):
    """
    Materialize curated flagship weapon systems per ingested nation as
    ontology objects linked via ks_operates. Editor+ role.
    """
    if ROLE_LEVELS.get(user.role, 0) < ROLE_LEVELS["editor"]:
        raise HTTPException(status_code=403, detail="Editor role required")
    from panteon.war_ontology import link_arsenal_flagships
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    return await link_arsenal_flagships(
        db, per_category=int(body.get("per_category", 3)),
        only_isos=body.get("countries"))


@router.post("/ontology/flashpoint")
async def sims_ontology_flashpoint(request: Request,
                                   user: SupabaseUser = Depends(get_current_user),
                                   db: AsyncSession = Depends(get_db)):
    """
    REAL-WORLD COUPLING: run a battle triggered by live intel.
    Body: {battlefield, scenarios?, seed?, source_event?: {id,title,country}}
    The assessment object records provenance back to the triggering event.
    """
    body = await request.json()
    payload = {
        "battlefield": body.get("battlefield", "random"),
        "scenarios": int(body.get("scenarios", 1000)),
        "seed": body.get("seed", 42),
    }
    report = await _gateway("POST", "kriegspiel/run", request, payload)
    if not report.get("error"):
        report["ontology"] = await _emit_ontology(
            db, report, user, mode="flashpoint",
            source_event=body.get("source_event"),
            battlefield=payload["battlefield"])
    return report


# --------------------------------------------------------------------------
# Explicit kriegspiel runs (proxy + ontology writeback)
# --------------------------------------------------------------------------

@router.post("/kriegspiel/run")
async def sims_kriegspiel_run(request: Request,
                              user: SupabaseUser = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    body = await request.json()
    payload = {
        "battlefield": body.get("battlefield", "random"),
        "scenarios": min(int(body.get("scenarios", 1000)), 50000),
        "seed": body.get("seed", 42),
    }
    report = await _gateway("POST", "kriegspiel/run", request, payload)
    if not report.get("error"):
        report["ontology"] = await _emit_ontology(db, report, user, mode="battle",
                                                  battlefield=payload["battlefield"])
    return report


@router.post("/kriegspiel/campaign/simulate")
async def sims_kriegspiel_campaign(request: Request,
                                   user: SupabaseUser = Depends(get_current_user),
                                   db: AsyncSession = Depends(get_db)):
    body = await request.json()
    campaign = await _gateway("POST", "kriegspiel/campaign/simulate", request, body)
    if not campaign.get("error"):
        sample = campaign.get("sample_campaign") or {}
        report = {
            "battlefield": sample.get("battlefield") or body.get("battlefield"),
            "campaigns": campaign.get("campaigns"),
            "red_wins": (campaign.get("campaign_wins") or {}).get("red", 0),
            "blue_wins": (campaign.get("campaign_wins") or {}).get("blue", 0),
            "stalemates": (campaign.get("campaign_wins") or {}).get("stalemate", 0),
            "avg_duration_hours": (campaign.get("avg_engagements") or 0)
                                  * (body.get("engagement_hours") or 24),
            "duration_ms": None, "seed": body.get("seed"),
            "_red_doctrine": body.get("red_doctrine"),
            "_blue_doctrine": body.get("blue_doctrine"),
            "reinforcement": campaign.get("reinforcement"),
            "collapses": campaign.get("collapses"),
            "avg_red_remaining_pct": campaign.get("avg_red_remaining_pct"),
            "avg_blue_remaining_pct": campaign.get("avg_blue_remaining_pct"),
            "avg_engagements": campaign.get("avg_engagements"),
            "avg_front_final_pct": campaign.get("avg_front_final_pct"),
        }
        campaign["ontology"] = await _emit_ontology(
            db, report, user, mode="campaign",
            battlefield=report.get("battlefield"))
    return campaign


# --------------------------------------------------------------------------
# Catch-all proxy for remaining read endpoints
# --------------------------------------------------------------------------

@router.api_route("/{path:path}", methods=["GET", "POST"])
async def proxy_to_gateway(path: str, request: Request, user: SupabaseUser = Depends(get_current_user)):
    if request.method == "POST" and path.rstrip("/") in MUTATING_PATHS:
        if ROLE_LEVELS.get(user.role, 0) < ROLE_LEVELS["editor"]:
            raise HTTPException(status_code=403, detail="Editor role required for self-improvement")

    url = f"{GATEWAY_URL}/api/{path}"
    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in ("host", "authorization", "content-length")}
    if request.method == "GET":
        json_body = None
    else:
        try:
            json_body = await request.json()
        except Exception:
            json_body = {}

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=5.0)) as client:
            resp = await client.request(request.method, url, headers=headers,
                                        params=dict(request.query_params), json=json_body)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Sims gateway unreachable: {exc}") from exc

    resp_headers = {k: v for k, v in resp.headers.items() if k.lower() not in HOP_BY_HOP}
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=resp_headers,
        media_type=resp.headers.get("content-type", "application/json"),
    )
