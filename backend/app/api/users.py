from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.services.image_service import ImageService
from app.services.user_service import UserService
from app.utils.auth import get_current_user
from app.utils.signed_urls import sign_image_url

router = APIRouter(prefix="/users/me", tags=["Users"])


class OnboardingCompleteResponse(BaseModel):
    onboarding_completed: bool


class UserProfileResponse(BaseModel):
    id: str
    email: str
    display_name: str
    avatar_url: str | None = None
    timezone: str
    location_lat: float | None = None
    location_lon: float | None = None
    location_name: str | None = None
    family_id: str | None = None
    role: str
    onboarding_completed: bool
    tryon_model_image_url: str | None = None


class UserProfileUpdate(BaseModel):
    display_name: str | None = None
    timezone: str | None = None
    location_lat: Decimal | None = None
    location_lon: Decimal | None = None
    location_name: str | None = None


def to_user_profile_response(current_user: User) -> UserProfileResponse:
    tryon_model_image_url = None
    if current_user.tryon_model_image_path:
        tryon_model_image_url = sign_image_url(current_user.tryon_model_image_path)

    return UserProfileResponse(
        id=str(current_user.id),
        email=current_user.email,
        display_name=current_user.display_name,
        avatar_url=current_user.avatar_url,
        timezone=current_user.timezone,
        location_lat=float(current_user.location_lat) if current_user.location_lat else None,
        location_lon=float(current_user.location_lon) if current_user.location_lon else None,
        location_name=current_user.location_name,
        family_id=str(current_user.family_id) if current_user.family_id else None,
        role=current_user.role,
        onboarding_completed=current_user.onboarding_completed,
        tryon_model_image_url=tryon_model_image_url,
    )


@router.get("", response_model=UserProfileResponse)
async def get_profile(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserProfileResponse:
    return to_user_profile_response(current_user)


@router.patch("", response_model=UserProfileResponse)
async def update_profile(
    data: UserProfileUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserProfileResponse:
    # Build update dict from non-None values
    update_data = data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(current_user, field, value)

    await db.flush()
    await db.refresh(current_user)
    await db.commit()

    return to_user_profile_response(current_user)


@router.post("/onboarding/complete", response_model=OnboardingCompleteResponse)
async def complete_onboarding(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> OnboardingCompleteResponse:
    user_service = UserService(db)
    await user_service.complete_onboarding(current_user)
    await db.commit()

    return OnboardingCompleteResponse(onboarding_completed=True)


@router.post("/tryon-model-image", response_model=UserProfileResponse)
async def upload_tryon_model_image(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    image: UploadFile = File(...),
) -> UserProfileResponse:
    image_service = ImageService()
    content = await image.read()
    content_type = image.content_type or "application/octet-stream"

    if not image_service.validate_image(content, content_type):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image file. Supported formats: JPEG, PNG, WebP, HEIC",
        )

    try:
        stored = await image_service.process_and_store(
            user_id=current_user.id,
            image_data=content,
            original_filename=image.filename or "tryon-model.jpg",
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None

    if current_user.tryon_model_image_path:
        image_service.delete_images({"old": current_user.tryon_model_image_path})

    current_user.tryon_model_image_path = stored["image_path"]
    await db.flush()
    await db.refresh(current_user)
    await db.commit()
    return to_user_profile_response(current_user)


@router.delete("/tryon-model-image", response_model=UserProfileResponse)
async def delete_tryon_model_image(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserProfileResponse:
    if current_user.tryon_model_image_path:
        ImageService().delete_images({"old": current_user.tryon_model_image_path})
        current_user.tryon_model_image_path = None
        await db.flush()
        await db.refresh(current_user)
        await db.commit()

    return to_user_profile_response(current_user)
