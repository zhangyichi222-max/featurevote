from pydantic import BaseModel, Field

from app.schemas.post import UserItem


class ClientCodeExchange(BaseModel):
    code: str = Field(min_length=1)


class AuthMeResponse(BaseModel):
    user: UserItem


class AuthActionResult(BaseModel):
    success: bool = True
    message: str
