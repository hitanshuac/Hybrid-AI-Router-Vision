from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional

class UsageRecord(BaseModel):
    request_id: str
    timestamp: datetime
    model_name: str
    provider: str
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    status: str
    latency_ms: Optional[float] = Field(None, ge=0)

    @field_validator('prompt_tokens', 'completion_tokens')
    @classmethod
    def must_be_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError('Token count must be non-negative')
        return v
