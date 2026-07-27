import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from panteon.core.config import settings
from panteon.core.database import init_db
from panteon.core.security import (
    SecurityHeadersMiddleware, RateLimitMiddleware, AuditMiddleware, ALLOWED_ORIGINS,
    api_rate_limit,
)
from panteon.api.routes_auth import router as auth_router
from panteon.api.routes_spinal_craker import router as spinal_craker_router
from panteon.api.routes_ono import router as ono_router
from panteon.api.routes_tdac import router as tdac_router
from panteon.api.routes_webhooks import router as webhooks_router
from panteon.api.routes_apollo import router as apollo_router
from panteon.api.routes_admin import router as admin_router
from panteon.api.routes_lineage import router as lineage_router
from panteon.api.routes_monitoring import router as monitoring_router
from panteon.api.routes_workspaces import router as workspaces_router
from panteon.api.routes_group import router as group_router
from panteon.api.routes_babel import router as babel_router
from panteon.api.routes_contour import router as contour_router
from panteon.api.routes_aip import router as aip_router

PANTEON_SITE = Path(os.path.dirname(__file__)).parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


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
app.include_router(ono_router, prefix="/api/v1")
app.include_router(apollo_router, prefix="/api/v1")
app.include_router(tdac_router, prefix="/api/v1")
app.include_router(webhooks_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(lineage_router, prefix="/api/v1")
app.include_router(monitoring_router, prefix="/api/v1")
app.include_router(workspaces_router, prefix="/api/v1")
app.include_router(group_router, prefix="/api/v1")
app.include_router(babel_router, prefix="/api/v1")
app.include_router(contour_router, prefix="/api/v1")
app.include_router(aip_router, prefix="/api/v1")


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
            "ono": "/api/v1/ono",
            "apollo": "/api/v1/apollo",
        },
    }


@app.get("/admin")
@app.get("/admin/")
async def admin():
    admin_file = PANTEON_SITE / "admin.html"
    if admin_file.exists():
        return FileResponse(admin_file)
    return {"detail": "Admin dashboard not found"}


@app.get("/ono-forge")
@app.get("/ono-forge/")
async def ono_forge():
    forge_file = PANTEON_SITE / "ono-forge.html"
    if forge_file.exists():
        return FileResponse(forge_file)
    return {"detail": "ONO Forge not found"}


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
