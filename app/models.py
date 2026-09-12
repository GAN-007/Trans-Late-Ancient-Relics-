from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, EmailStr, Field, field_validator


class TextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)


class ESHBEncodeRequest(TextRequest):
    language: Literal["auto", "english", "swahili"] = "auto"


class TranslationRequest(TextRequest):
    source: Literal["english", "swahili", "egyptian"]
    target: Literal["english", "swahili", "egyptian"] = "egyptian"
    context: str = Field(default="", max_length=4000)
    intent: str = Field(default="", max_length=500)
    mode: Literal["careful", "literal", "natural"] = "careful"
    use_ai: bool = True


class RegisterRequest(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=10, max_length=256)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class ProgressRequest(BaseModel):
    item_type: str = Field(min_length=1, max_length=40)
    item_id: str = Field(min_length=1, max_length=80)
    score: float = Field(ge=0, le=1)


class FeedbackRequest(BaseModel):
    translation_id: int | None = None
    rating: Literal["correct", "partly_correct", "wrong", "uncertain"]
    suggested_translation: str | None = Field(default=None, max_length=4000)
    context: str | None = Field(default=None, max_length=4000)
    notes: str | None = Field(default=None, max_length=4000)


class LexiconProposalRequest(BaseModel):
    transliteration: str = Field(min_length=1, max_length=200)
    english: list[str] = Field(min_length=1, max_length=20)
    swahili: list[str] = Field(min_length=1, max_length=20)
    pos: str = Field(min_length=1, max_length=120)
    hieroglyphs: str | None = Field(default=None, max_length=1000)
    gardiner: list[str] = Field(default_factory=list, max_length=50)
    mdc: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=4000)
    evidence: str | None = Field(default=None, max_length=4000)
    confidence: Literal["proposed", "medium", "high"] = "proposed"

    @field_validator("english", "swahili")
    @classmethod
    def nonempty_strings(cls, values: list[str]) -> list[str]:
        cleaned = [v.strip() for v in values if v.strip()]
        if not cleaned:
            raise ValueError("At least one non-empty gloss is required")
        return cleaned


class ProposalDecisionRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    notes: str | None = Field(default=None, max_length=4000)


class RoleChangeRequest(BaseModel):
    role: Literal["learner", "contributor", "reviewer", "admin"]


class UserDisableRequest(BaseModel):
    disabled: bool


class LiveVisionRequest(BaseModel):
    image_data_url: str = Field(min_length=20)
    target_language: Literal["english", "swahili"] = "english"
    context: str = Field(default="", max_length=4000)
    session_id: str | None = Field(default=None, max_length=120)


class LearningProposalRequest(BaseModel):
    min_frequency: int = Field(default=3, ge=1, le=1000)
    limit: int = Field(default=20, ge=1, le=100)
