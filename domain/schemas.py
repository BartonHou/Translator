from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal

class TranslateOptions(BaseModel):
    beam_size: int = 4
    max_new_tokens: int = 256
    split_long: bool = True

class TranslateRequest(BaseModel):
    source_lang: str = Field(min_length=2, max_length=10)
    target_lang: str = Field(min_length=2, max_length=10)
    texts: List[str] = Field(min_length=1)
    options: Optional[TranslateOptions] = None

class TranslateResponse(BaseModel):
    model: str
    translations: List[str]
    latency_ms: float
    cache_hit_rate: float

class JobCreateRequest(BaseModel):
    source_lang: str
    target_lang: str
    texts: List[str] = Field(min_length=1)
    options: Optional[TranslateOptions] = None
    callback_url: Optional[str] = None  # reserved for future

class JobStatusResponse(BaseModel):
    job_id: str
    status: Literal["PENDING", "RUNNING", "SUCCEEDED", "FAILED"]
    model: Optional[str] = None
    created_at: str
    updated_at: str
    error_message: Optional[str] = None

class JobResultResponse(BaseModel):
    job_id: str
    status: Literal["PENDING", "RUNNING", "SUCCEEDED", "FAILED"]
    translations: Optional[List[str]] = None
    model: Optional[str] = None
    latency_ms: Optional[float] = None
    error_message: Optional[str] = None
