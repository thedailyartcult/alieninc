from fastapi import APIRouter, Depends
from panteon.core.auth import SupabaseUser, get_current_user

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.get("/me")
async def whoami(current_user: SupabaseUser = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "role": current_user.role,
    }
