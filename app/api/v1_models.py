from fastapi import APIRouter
from app.core.routing import MODEL_REGISTRY

router = APIRouter(prefix="/v1", tags=["models"])

@router.get("/models")
def list_models():
    return {
        "registry": {f"{k[0]}->{k[1]}": v for k, v in MODEL_REGISTRY.items()}
    }
