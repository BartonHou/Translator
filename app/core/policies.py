from dataclasses import dataclass
from app.settings import settings

@dataclass(frozen=True)
class PolicyDecision:
    use_async: bool
    reason: str

def decide_sync_or_async(texts: list[str]) -> PolicyDecision:
    # Heuristic: too many texts or too many chars => async
    if len(texts) > settings.max_sync_texts:
        return PolicyDecision(True, f"too many texts (> {settings.max_sync_texts})")
    total_chars = sum(len(t) for t in texts)
    if total_chars > settings.max_sync_chars:
        return PolicyDecision(True, f"payload too large (> {settings.max_sync_chars} chars)")
    return PolicyDecision(False, "within sync budget")
