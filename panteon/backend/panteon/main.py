import logging
import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from panteon.core.config import settings
from panteon.core.auth import verify_supabase_token
from panteon.core.database import init_db
from panteon.core.security import (
    SecurityHeadersMiddleware, RateLimitMiddleware, AuditMiddleware, ALLOWED_ORIGINS,
    api_rate_limit,
)
from panteon.api.routes_auth import router as auth_router
from panteon.api.routes_spinal_craker import router as spinal_craker_router
from panteon.api.routes_gdelt import router as gdelt_router
from panteon.api.routes_opensky import router as opensky_router
from panteon.api.routes_gkg import router as gkg_router, start_autopull, stop_autopull
from panteon.api.routes_yono import router as yono_router
from panteon.api.routes_tdac import router as tdac_router
from panteon.api.routes_webhooks import router as webhooks_router
from panteon.api.routes_statham import router as statham_router
from panteon.api.routes_admin import router as admin_router
from panteon.api.routes_lineage import router as lineage_router
from panteon.api.routes_monitoring import router as monitoring_router
from panteon.api.routes_workspaces import router as workspaces_router
from panteon.api.routes_group import router as group_router
from panteon.api.routes_crackerbox import router as crackerbox_router
from panteon.api.routes_contour import router as contour_router
from panteon.api.routes_aip import router as aip_router
from panteon.api.routes_terranean import router as terranean_router
from panteon.api.routes_yono_functions import router as yono_functions_router
from panteon.api.routes_research import router as research_router
from panteon.api.routes_ngram import router as ngram_router
from panteon.api.routes_actor_graph import router as actor_graph_router
from panteon.api.routes_smm import router as smm_router
from panteon.api.routes_sims import router as sims_router
from panteon.api.routes_maven import router as maven_router
from panteon.api.routes_arsenal import router as arsenal_store_router

PANTEON_SITE = Path(os.path.dirname(__file__)).parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    start_autopull()
    # Idempotent bootstrap of the Spinal Cracker YONO panel agent.
    # (on_event handlers are ignored because this app passes an explicit
    # lifespan — seeding must live here.)
    try:
        from panteon.core.database import async_session
        from panteon.yono.sc_agent_seed import ensure_sc_yono_agent

        async with async_session() as db:
            await ensure_sc_yono_agent(db)
            await db.commit()
    except Exception as exc:  # noqa: BLE001 — boot must never depend on seeding
        logging.getLogger("panteon.yono.sc_seed").warning(
            "YONO panel agent seed skipped: %s", exc)
    yield
    await stop_autopull()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Panteon - Enterprise Data & AI Operating System",
    lifespan=lifespan,
    docs_url=None if not settings.debug else "/docs",
    redoc_url=None if not settings.debug else "/redoc",
)

app.add_middleware(AuditMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)


@app.middleware("http")
async def mimi_scope_guard(request: Request, call_next):
    """MiMi-only operators are fenced to auth + SMM endpoints; everything
    else under /api/v1 returns 403 for that role."""
    path = request.url.path
    if path.startswith("/api/v1") and not path.startswith(("/api/v1/auth", "/api/v1/smm")):
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            user = await verify_supabase_token(auth_header[7:].strip())
            if user is not None and user.role == "mimi":
                return JSONResponse(
                    status_code=403,
                    content={"detail": "This account is scoped to the MiMi Panel only"},
                )
    return await call_next(request)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
    max_age=600,
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(spinal_craker_router, prefix="/api/v1")
app.include_router(gdelt_router, prefix="/api/v1")
app.include_router(opensky_router, prefix="/api/v1")
app.include_router(gkg_router, prefix="/api/v1")
app.include_router(yono_router, prefix="/api/v1")
app.include_router(statham_router, prefix="/api/v1")
app.include_router(tdac_router, prefix="/api/v1")
app.include_router(webhooks_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(lineage_router, prefix="/api/v1")
app.include_router(monitoring_router, prefix="/api/v1")
app.include_router(workspaces_router, prefix="/api/v1")
app.include_router(group_router, prefix="/api/v1")
app.include_router(crackerbox_router, prefix="/api/v1")
app.include_router(contour_router, prefix="/api/v1")
app.include_router(aip_router, prefix="/api/v1")
app.include_router(terranean_router, prefix="/api/v1")
app.include_router(yono_functions_router, prefix="/api/v1")
app.include_router(research_router, prefix="/api/v1")
app.include_router(ngram_router, prefix="/api/v1")
app.include_router(actor_graph_router, prefix="/api/v1")
app.include_router(smm_router, prefix="/api/v1")
app.include_router(sims_router, prefix="/api/v1")
app.include_router(maven_router, prefix="/api/v1")
app.include_router(arsenal_store_router, prefix="/api/v1")


@app.get("/")
async def root():
    index = PANTEON_SITE / "index.html"
    if index.exists():
        return FileResponse(index)
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "platforms": {
            "spinal_craker": "/api/v1/spinal-craker",
            "yono": "/api/v1/yono",
            "statham": "/api/v1/statham",
        },
    }


@app.get("/admin")
@app.get("/admin/")
async def admin():
    admin_file = PANTEON_SITE / "admin.html"
    if admin_file.exists():
        # no-cache: browsers must revalidate every load — stale dashboards
        # have shipped broken UI silently before (arsenal icons incident).
        return FileResponse(admin_file, headers={
            "Cache-Control": "no-cache",
        })
    return {"detail": "Admin dashboard not found"}


@app.get("/yono-forge")
@app.get("/yono-forge/")
async def yono_forge():
    forge_file = PANTEON_SITE / "yono-forge.html"
    if forge_file.exists():
        return FileResponse(forge_file)
    return {"detail": "YONO Forge not found"}


@app.get("/pipeline-builder")
@app.get("/pipeline-builder/")
async def pipeline_builder():
    pb_file = PANTEON_SITE / "pipeline-builder.html"
    if pb_file.exists():
        return FileResponse(pb_file)
    return {"detail": "Pipeline Builder not found"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


app.mount("/static", StaticFiles(directory=str(PANTEON_SITE)), name="panteon-site")
