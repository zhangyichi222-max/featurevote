from pydantic import BaseModel, Field


class SuggestionDraftRequest(BaseModel):
    idea: str = Field(min_length=20, max_length=12000)


class SuggestionDraftResponse(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=1, max_length=5000)
