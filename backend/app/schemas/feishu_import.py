from pydantic import BaseModel


class FeishuImportRunResponse(BaseModel):
    fetched: int = 0
    skipped: int = 0
    created: int = 0
    voted: int = 0
    already_voted: int = 0
    failed: int = 0

    def add(self, key: str, amount: int = 1) -> None:
        current = getattr(self, key)
        setattr(self, key, current + amount)
