from pydantic import BaseModel, Field


class SuggestionDraftRequest(BaseModel):
    idea: str = Field(min_length=20, max_length=12000)


class SuggestionDraftResponse(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=1, max_length=5000)


class SimilarRequirementsRequest(BaseModel):
    title: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=5000)
    limit: int = Field(default=3, ge=1, le=5)


class SimilarRequirementItem(BaseModel):
    id: str
    number: int
    title: str
    description: str
    status: str
    votes_count: int
    similarity: float = Field(ge=0, le=1)
    is_high_confidence: bool
    reason: str | None = None


class SimilarRequirementsResponse(BaseModel):
    items: list[SimilarRequirementItem]
    ai_enhanced: bool = False
