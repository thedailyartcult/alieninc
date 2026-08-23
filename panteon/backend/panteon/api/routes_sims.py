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
                         mode: str, source_event: dict | None = None) -> dict:
    try:
        summary = await emit_battle_report(db, report, mode=mode, source_event=source_event)
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
async def sims_ontology_graph(limit: int = 400,
                              user: SupabaseUser = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    limit = max(1, min(limit, 2000))
    return await graph_snapshot(db, limit=limit)


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
            source_event=body.get("source_event"))
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
        report["ontology"] = await _emit_ontology(db, report, user, mode="battle")
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
            db, report, user, mode="campaign")
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
