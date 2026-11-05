import hashlib
import hmac
import time

from fastapi import HTTPException, Request
import structlog

from panteon.core.config import settings

logger = structlog.get_logger()

SIGNATURE_HEADER = "X-YONO-Signature"
TIMESTAMP_HEADER = "X-YONO-Timestamp"
MAX_TIMESTAMP_SKEW = 300


def compute_signature(body: bytes, secret: str, timestamp: str) -> str:
    payload = timestamp.encode("utf-8") + b"." + body
    return hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()


def verify_spinal_craker_signature(body: bytes, signature: str, timestamp: str) -> bool:
    secret = settings.ono_function_shared_secret
    if not secret:
        logger.error("ono_function_shared_secret_not_configured")
        return False
    try:
        ts = int(timestamp)
    except (ValueError, TypeError):
        return False
    now = int(time.time())
    if abs(now - ts) > MAX_TIMESTAMP_SKEW:
        logger.warning(
            "yono_function_timestamp_skew",
            provided_ts=ts,
            server_ts=now,
            skew=abs(now - ts),
        )
        return False
    expected = compute_signature(body, secret, timestamp)
    return hmac.compare_digest(expected, signature)


async def require_spinal_craker_auth(request: Request) -> dict:
    signature = request.headers.get(SIGNATURE_HEADER)
    timestamp = request.headers.get(TIMESTAMP_HEADER)
    if not signature or not timestamp:
        logger.warning("yono_function_missing_auth", path=str(request.url.path))
        raise HTTPException(
            status_code=401,
            detail="Missing signature or timestamp. "
            f"Required headers: {SIGNATURE_HEADER}, {TIMESTAMP_HEADER}",
        )
    body = await request.body()
    if not verify_spinal_craker_signature(body, signature, timestamp):
        logger.warning(
            "yono_function_invalid_signature",
            path=str(request.url.path),
            client=request.client.host if request.client else "unknown",
        )
        raise HTTPException(status_code=401, detail="Invalid signature or expired timestamp")
    return {"verified": True}
