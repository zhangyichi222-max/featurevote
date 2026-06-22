from pydantic import BaseModel, Field


class FeishuImportRunResponse(BaseModel):
    fetched: int = 0
    skipped: int = 0
    created: int = 0
    voted: int = 0
    already_voted: int = 0
    failed: int = 0
    created_titles: list[str] = Field(default_factory=list)

    def add(self, key: str, amount: int = 1) -> None:
        current = getattr(self, key)
        setattr(self, key, current + amount)

    def add_created_title(self, title: str) -> None:
        cleaned = title.strip()
        if cleaned:
            self.created_titles.append(cleaned)
