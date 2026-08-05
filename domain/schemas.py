from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class TranslateOptions(BaseModel):
    # None -> fall back to the server default (settings.default_beam_size).
    beam_size: int | None = None
    max_new_tokens: int = 256
    split_long: bool = True
    glossary_id: str | None = None  # apply this glossary's forced terms

class TranslateRequest(BaseModel):
    source_lang: str = Field(min_length=2, max_length=10)
    target_lang: str = Field(min_length=2, max_length=10)
    texts: list[str] = Field(min_length=1)
    options: TranslateOptions | None = None

class StreamTranslateRequest(BaseModel):
    source_lang: str = Field(min_length=2, max_length=10)
    target_lang: str = Field(min_length=2, max_length=10)
    text: str = Field(min_length=1)
    options: TranslateOptions | None = None


class TranslateResponse(BaseModel):
    model: str
    translations: list[str]
    latency_ms: float
    cache_hit_rate: float
    detected_source_lang: str | None = None  # set when source_lang="auto"
    confidence: list[float] | None = None     # per-translation quality estimate

class JobCreateRequest(BaseModel):
    source_lang: str
    target_lang: str
    texts: list[str] = Field(min_length=1)
    options: TranslateOptions | None = None
    callback_url: str | None = None  # reserved for future

class JobStatusResponse(BaseModel):
    job_id: str
    status: Literal["PENDING", "RUNNING", "SUCCEEDED", "FAILED"]
    model: str | None = None
    created_at: str
    updated_at: str
    error_message: str | None = None

class JobResultResponse(BaseModel):
    job_id: str
    status: Literal["PENDING", "RUNNING", "SUCCEEDED", "FAILED"]
    translations: list[str] | None = None
    model: str | None = None
    latency_ms: float | None = None
    error_message: str | None = None


# --- auth / account --------------------------------------------------------
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: str
    email: str
    role: str
    created_at: str


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(default="default", max_length=128)
    rpm_limit: int | None = None
    monthly_quota_chars: int | None = None


class ApiKeyResponse(BaseModel):
    id: str
    name: str
    key_prefix: str
    rpm_limit: int
    monthly_quota_chars: int | None = None
    is_active: bool
    created_at: str
    last_used_at: str | None = None


class ApiKeyCreatedResponse(ApiKeyResponse):
    # The full plaintext key, returned only once at creation time.
    api_key: str


class UsageDayResponse(BaseModel):
    day: str
    requests: int
    chars_in: int
    chars_out: int


class UsageResponse(BaseModel):
    month_to_date_chars: int
    days: list[UsageDayResponse]


class GlossaryCreateRequest(BaseModel):
    name: str = Field(default="default", max_length=128)
    entries: dict[str, str] = Field(default_factory=dict)


class GlossaryResponse(BaseModel):
    id: str
    name: str
    entries: dict[str, str]
    created_at: str
