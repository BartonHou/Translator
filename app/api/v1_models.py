from fastapi import APIRouter

from app.core.routing import (
    MODEL_REGISTRY,
    PIVOT_LANG,
    SUPPORTED_LANGUAGES,
    all_supported_pairs,
)

router = APIRouter(prefix="/v1", tags=["models"])


@router.get("/models")
def list_models():
    return {
        "registry": {f"{k[0]}->{k[1]}": v for k, v in MODEL_REGISTRY.items()},
        "supported_languages": SUPPORTED_LANGUAGES,
        "pivot_language": PIVOT_LANG,
        "supports_multi_to_multi_via_pivot": True,
        # Every combination that will actually resolve (direct or via pivot),
        # so clients can present only valid source/target options.
        "pairs": all_supported_pairs(),
    }
