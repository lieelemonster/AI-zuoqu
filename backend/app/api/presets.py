from fastapi import APIRouter

from app.presets import Presets, load_presets

router = APIRouter()


@router.get("/presets", response_model=Presets, tags=["presets"])
def get_presets() -> Presets:
    return load_presets()
