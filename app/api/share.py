from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.cv import _get_candidate
from app.core.auth import AuthUser, get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.services.referral import (
    IMPULSO_SHARE_THRESHOLD,
    advance_tier,
    get_or_create_tier,
    new_ref_token,
    share_text,
)
from app.models import Share

router = APIRouter()


class TierResponse(BaseModel):
    tier: str
    share_count: int
    referral_count: int
    donated_total: float


@router.get("/tier", response_model=TierResponse)
def get_tier(
    user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> TierResponse:
    candidate = _get_candidate(db, user)
    tier = get_or_create_tier(db, candidate.id)
    return TierResponse(
        tier=tier.tier,
        share_count=tier.share_count,
        referral_count=tier.referral_count,
        donated_total=float(tier.donated_total),
    )


class ShareRequest(BaseModel):
    channel: Literal["linkedin", "x", "whatsapp", "facebook", "copy", "other"]


class ShareResponse(BaseModel):
    ref_token: str
    url: str


@router.post("/share", response_model=ShareResponse)
def create_share(
    body: ShareRequest,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ShareResponse:
    candidate = _get_candidate(db, user)

    ref_token = new_ref_token()
    db.add(Share(candidate_id=candidate.id, ref_token=ref_token, channel=body.channel))

    # RF-08: al tercer share, desbloqueo inmediato a "impulso", sin
    # verificar nada -- la fricción de verificar cuesta más que la trampa
    # (ver doc técnico §8).
    tier = get_or_create_tier(db, candidate.id)
    tier.share_count += 1
    if tier.share_count >= IMPULSO_SHARE_THRESHOLD:
        advance_tier(tier, "impulso", "share")

    db.flush()
    return ShareResponse(
        ref_token=ref_token, url=f"{settings.frontend_url}/a/{candidate.slug}?ref={ref_token}"
    )


class ShareTextResponse(BaseModel):
    text: str


@router.get("/share/text", response_model=ShareTextResponse)
def get_share_text(
    channel: str,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ShareTextResponse:
    candidate = _get_candidate(db, user)
    text = share_text(channel, candidate.agent_language)
    if text is None:
        raise HTTPException(status_code=400, detail="Unknown channel")
    return ShareTextResponse(text=text)
