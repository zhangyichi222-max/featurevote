from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clients.feishu import FeishuClient, FeishuProfile
from app.core.config import settings
from app.models.post import UserModel
from app.repositories.posts import DEFAULT_TENANT_ID


@dataclass(frozen=True)
class AuthenticatedSession:
    user: UserModel
    token: str


class AuthService:
    def __init__(self, session: Session, feishu_client: FeishuClient | None = None) -> None:
        self.session = session
        self.feishu_client = feishu_client or FeishuClient()

    def build_browser_authorization_url(self, state: str) -> str:
        return self.feishu_client.build_authorization_url(state)

    def authenticate_feishu_code(self, code: str) -> UserModel:
        profile = self.feishu_client.authenticate_code(code)
        return self.upsert_feishu_user(profile)

    def upsert_feishu_user(self, profile: FeishuProfile) -> UserModel:
        user = self.session.scalar(
            select(UserModel).where(
                UserModel.tenant_id == DEFAULT_TENANT_ID,
                UserModel.feishu_open_id == profile.open_id,
            )
        )
        if user is None:
            user = UserModel(
                id=uuid4().hex,
                tenant_id=DEFAULT_TENANT_ID,
                external_id=profile.open_id,
                feishu_open_id=profile.open_id,
                name=profile.name,
                role="visitor",
            )
        user.external_id = profile.open_id
        user.feishu_open_id = profile.open_id
        user.feishu_union_id = profile.union_id
        user.name = profile.name
        user.email = profile.email
        user.avatar_url = profile.avatar_url
        user.department_ids = ",".join(profile.department_ids)
        user.group_ids = ",".join(profile.group_ids)
        if settings.feishu_admin_user_names:
            user.role = "admin" if profile.name in settings.feishu_admin_user_names else "visitor"
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user
