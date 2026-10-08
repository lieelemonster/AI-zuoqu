from fastapi import APIRouter, Depends

from app.api.errors import AppError
from app.lyrics.generator import PROMPT_VERSION, generate_lyrics
from app.presets import UnknownPresetError, validate_creative_input
from app.providers import TextModelProvider, get_provider
from app.schemas.base import ApiModel
from app.schemas.input import CreativeInput
from app.schemas.lyrics import LyricVariant

router = APIRouter()


class LyricsResponse(ApiModel):
    variants: list[LyricVariant]
    model_id: str
    prompt_version: str


def validated_input(data: CreativeInput) -> CreativeInput:
    try:
        return validate_creative_input(data)
    except UnknownPresetError as exc:
        raise AppError(422, "INVALID_INPUT", str(exc), fields=[str(exc)]) from exc


@router.post("/lyrics", response_model=LyricsResponse, tags=["lyrics"])
def create_lyrics(data: CreativeInput = Depends(validated_input),
                  provider: TextModelProvider = Depends(get_provider)) -> LyricsResponse:
    result = generate_lyrics(data, provider)
    return LyricsResponse(variants=result.variants, model_id=provider.model_id, prompt_version=PROMPT_VERSION)
