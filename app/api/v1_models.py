from fastapi import APIRouter
from app.core.routing import MODEL_REGISTRY, SUPPORTED_LANGUAGES, PIVOT_LANG

router = APIRouter(prefix="/v1", tags=["models"])

@router.get("/models")
def list_models():
    return {
        "registry": {f"{k[0]}->{k[1]}": v for k, v in MODEL_REGISTRY.items()},
        "supported_languages": SUPPORTED_LANGUAGES,
        "pivot_language": PIVOT_LANG,
        "supports_multi_to_multi_via_pivot": True,
    }
