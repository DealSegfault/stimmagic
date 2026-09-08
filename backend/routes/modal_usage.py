"""Modal account usage and generation tracking API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, SecretStr

from modal_usage_service import get_modal_usage_service

router = APIRouter(prefix="/api/modal", tags=["modal-usage"])


class ModalRoutingUpdate(BaseModel):
    mode: str = Field(pattern="^(auto|fixed)$")
    account_id: str | None = None


class ModalAccountCreate(BaseModel):
    label: str | None = Field(default=None, max_length=80)
    profile: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    modal_token_id: SecretStr
    modal_token_secret: SecretStr
    hf_token: SecretStr | None = None
    monthly_budget: float = Field(default=30.0, ge=0, le=1_000_000)
    force_redeploy: bool = False


@router.get("/usage")
async def get_modal_usage(limit: int = Query(default=50, ge=1, le=200)):
    """Return redacted account totals and recent generation usage."""
    return get_modal_usage_service().snapshot(limit=limit)


@router.get("/accounts")
async def get_modal_accounts():
    """Return account health/budget metadata without credentials."""
    return get_modal_usage_service().snapshot(limit=1)["accounts"]


@router.post("/accounts", status_code=202)
async def create_modal_account(payload: ModalAccountCreate):
    """Provision one isolated Modal workspace and add its gateway route."""
    token_id = payload.modal_token_id.get_secret_value().strip()
    token_secret = payload.modal_token_secret.get_secret_value().strip()
    hf_token = payload.hf_token.get_secret_value().strip() if payload.hf_token else None
    if not token_id.startswith("ak-") or not token_secret.startswith("as-"):
        raise HTTPException(status_code=400, detail="Clés API Modal invalides")
    if hf_token and not hf_token.startswith("hf_"):
        raise HTTPException(status_code=400, detail="Token Hugging Face invalide")
    try:
        return get_modal_usage_service().start_account_provisioning(
            modal_token_id=token_id,
            modal_token_secret=token_secret,
            profile=payload.profile,
            hf_token=hf_token,
            label=payload.label,
            monthly_budget=payload.monthly_budget,
            force_redeploy=payload.force_redeploy,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/provisioning")
async def get_modal_provisioning():
    """Return redacted progress for the latest account setup."""
    return get_modal_usage_service().provisioning_status()


@router.get("/routing")
async def get_modal_routing():
    """Return the live account-routing preference without credentials."""
    return get_modal_usage_service().get_routing()


@router.patch("/routing")
async def update_modal_routing(payload: ModalRoutingUpdate):
    """Set automatic or fixed-account routing for future generations."""
    try:
        return get_modal_usage_service().update_routing(payload.mode, payload.account_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/pricing")
async def get_modal_pricing():
    """Return the standard Modal resource rates used by cost estimates."""
    return get_modal_usage_service().snapshot(limit=1)["pricing"]


@router.get("/health")
async def get_modal_router_health():
    snapshot = get_modal_usage_service().snapshot(limit=1)
    return {
        "configured": snapshot["configured"],
        "accounts": [
            {"id": item["id"], "status": item["status"], "active_jobs": item["active_jobs"]}
            for item in snapshot["accounts"]
        ],
    }
