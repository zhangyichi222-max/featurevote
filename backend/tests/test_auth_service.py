from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.clients.feishu import FeishuProfile
from app.db.base import Base
from app.models.post import UserModel
from app.repositories.posts import DEFAULT_TENANT_ID, seed_default_data
from app.services.auth import AuthService


def test_feishu_login_updates_existing_user() -> None:
    session = _session()
    seed_default_data(session)
    session.add(
        UserModel(
            id="existing-user",
            tenant_id=DEFAULT_TENANT_ID,
            external_id="old-open-id",
            feishu_open_id="existing-open-id",
            name="Old Name",
        )
    )
    session.commit()

    user = AuthService(session).upsert_feishu_user(_profile("existing-open-id", "New Name"))

    assert user.name == "New Name"
    assert user.external_id == "existing-open-id"


def test_feishu_login_creates_new_users() -> None:
    session = _session()
    seed_default_data(session)

    user = AuthService(session).upsert_feishu_user(_profile("new-open-id", "New User"))

    assert user.name == "New User"


def test_feishu_login_without_name_preserves_existing_name() -> None:
    session = _session()
    seed_default_data(session)
    session.add(
        UserModel(
            id="existing-user",
            tenant_id=DEFAULT_TENANT_ID,
            external_id="existing-open-id",
            feishu_open_id="existing-open-id",
            name="Existing Name",
        )
    )
    session.commit()

    user = AuthService(session).upsert_feishu_user(_profile("existing-open-id", None))

    assert user.name == "Existing Name"


def test_feishu_login_with_name_replaces_fallback_name() -> None:
    session = _session()
    seed_default_data(session)
    session.add(
        UserModel(
            id="existing-user",
            tenant_id=DEFAULT_TENANT_ID,
            external_id="existing-open-id",
            feishu_open_id="existing-open-id",
            name="Feishu User",
        )
    )
    session.commit()

    user = AuthService(session).upsert_feishu_user(_profile("existing-open-id", "Recovered Name"))

    assert user.name == "Recovered Name"


def test_feishu_login_without_name_uses_fallback_for_new_user() -> None:
    session = _session()
    seed_default_data(session)

    user = AuthService(session).upsert_feishu_user(_profile("new-open-id", None))

    assert user.name == "Feishu User"


def _session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)()


def _profile(open_id: str, name: str | None) -> FeishuProfile:
    return FeishuProfile(
        open_id=open_id,
        union_id=None,
        name=name,
        email=None,
        avatar_url=None,
        department_ids=[],
        group_ids=[],
    )
