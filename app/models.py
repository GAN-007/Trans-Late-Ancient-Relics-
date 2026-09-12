from pydantic import BaseModel, Field
from typing import Literal, Optional

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

class ProgressRequest(BaseModel):
    learner: str = Field(min_length=1, max_length=80)
    item_type: str = Field(min_length=1, max_length=40)
    item_id: str = Field(min_length=1, max_length=80)
    score: float = Field(ge=0, le=1)
