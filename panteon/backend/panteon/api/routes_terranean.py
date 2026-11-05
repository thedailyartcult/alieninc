"""
Terranean Engine proxy — forwards requests to the standalone Terranean Engine service.
"""
import httpx
from fastapi import APIRouter, Depends, Request, Response
from panteon.core.auth import SupabaseUser, get_current_user

router = APIRouter(prefix="/terranean", tags=["Terranean Engine"])

ENGINE_URL = "http://localhost:8100"


@router.api_route("/{path:path}", methods=["GET", "POST"])
async def proxy_to_engine(path: str, request: Request, user: SupabaseUser = Depends(get_current_user)):
    url = f"{ENGINE_URL}/{path}"
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "authorization")}

    async with httpx.AsyncClient(timeout=30.0) as client:
        if request.method == "GET":
            resp = await client.get(url, headers=headers, params=dict(request.query_params))
        else:
            body = await request.body()
            resp = await client.request(request.method, url, headers=headers, content=body)

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=dict(resp.headers),
        media_type=resp.headers.get("content-type", "application/json"),
    )
