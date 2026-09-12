from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class TextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


class ESHBEncodeRequest(TextRequest):
    language: Literal["auto","english","swahili"] = "auto"


class DictionaryQuery(BaseModel):
    q: str = ""
    language: Literal["all","english","swahili","egyptian","transliteration"] = "all"
    pos: Optional[str] = None
    limit: int = Field(default=50, ge=1, le=500)


class TranslationRequest(TextRequest):
    source: Literal["english","swahili","egyptian"]
    target: Literal["english","swahili","egyptian"] = "egyptian"


class ContextualTranslationRequest(TranslationRequest):
    model_config = ConfigDict(populate_by_name=True)
    context: str = Field(default="", max_length=4000)
    translation_register: Literal["literal","natural","scholarly","learner"] = Field(default="natural", alias="register")
    use_ai: bool = True
    max_alternatives: int = Field(default=4, ge=1, le=10)
    save_history: bool = False


class ProgressRequest(BaseModel):
    learner: str = Field(min_length=1, max_length=80)
    item_type: str = Field(min_length=1, max_length=40)
    item_id: str = Field(min_length=1, max_length=80)
    score: float = Field(ge=0, le=1)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=40)
    display_name: str = Field(default="", max_length=80)
    password: str = Field(min_length=10, max_length=200)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=200)


class RoleUpdateRequest(BaseModel):
    role: Literal["learner","contributor","reviewer","admin"]


class VisionRequest(BaseModel):
    image_data_url: str = Field(min_length=20, max_length=8_000_000)
    target_language: Literal["english","swahili"] = "english"
    context: str = Field(default="", max_length=2000)
    detail: Literal["low","auto","high"] = "high"


class KnowledgeProposalRequest(BaseModel):
    kind: Literal["lexicon","translation","sign","pronunciation","grammar"]
    payload: dict[str, Any]
    evidence: str = Field(default="", max_length=5000)
    source_url: str = Field(default="", max_length=2000)
    confidence: float | None = Field(default=None, ge=0, le=1)


class KnowledgeReviewRequest(BaseModel):
    status: Literal["approved","rejected"]
    note: str = Field(default="", max_length=3000)


class KnowledgeRunRequest(BaseModel):
    limit: int = Field(default=5, ge=1, le=20)
    force: bool = True


class FeedbackRequest(BaseModel):
    kind: Literal["translation","vision","dictionary","lesson","pronunciation"] = "translation"
    source_text: str = Field(default="", max_length=5000)
    source_language: str = Field(default="", max_length=40)
    target_language: str = Field(default="", max_length=40)
    rating: Literal[-1,0,1] = 0
    correction: str = Field(default="", max_length=5000)
    context: str = Field(default="", max_length=4000)
    note: str = Field(default="", max_length=3000)


class KnowledgeEvidenceRequest(BaseModel):
    evidence: str = Field(default="", max_length=5000)
    source_url: str = Field(default="", max_length=2000)
