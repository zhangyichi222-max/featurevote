from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.clients.feishu import FeishuProfile
from app.core.config import settings
from app.db.base import Base
from app.models.post import UserModel
from app.repositories.posts import DEFAULT_TENANT_ID, seed_default_data
from app.services.auth import AuthService


def test_feishu_login_without_admin_allowlist_demotes_existing_admin() -> None:
    previous_admin_open_ids = list(settings.feishu_admin_open_ids)
    settings.feishu_admin_open_ids = []
    session = _session()
    seed_default_data(session)
    try:
        session.add(
            UserModel(
                id="admin-user",
                tenant_id=DEFAULT_TENANT_ID,
                external_id="old-open-id",
                feishu_open_id="admin-open-id",
                name="Old Name",
                role="admin",
            )
        )
        session.commit()

        user = AuthService(session).upsert_feishu_user(_profile("admin-open-id", "New Name"))

        assert user.name == "New Name"
        assert user.role == "visitor"
    finally:
        settings.feishu_admin_open_ids = previous_admin_open_ids


def test_feishu_login_creates_new_users_as_visitors() -> None:
    session = _session()
    seed_default_data(session)

    user = AuthService(session).upsert_feishu_user(_profile("new-open-id", "New User"))

    assert user.role == "visitor"


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
            role="visitor",
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
            role="visitor",
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


def test_configured_admin_open_ids_are_authoritative() -> None:
    previous_admin_open_ids = list(settings.feishu_admin_open_ids)
    settings.feishu_admin_open_ids = ["configured-open-id"]
    try:
        session = _session()
        seed_default_data(session)
        session.add(
            UserModel(
                id="old-admin-user",
                tenant_id=DEFAULT_TENANT_ID,
                external_id="old-admin-open-id",
                feishu_open_id="old-admin-open-id",
                name="Old Admin",
                role="admin",
            )
        )
        session.commit()

        configured = AuthService(session).upsert_feishu_user(_profile("configured-open-id", "Configured Admin"))
        removed = AuthService(session).upsert_feishu_user(_profile("old-admin-open-id", "Old Admin"))

        assert configured.role == "admin"
        assert removed.role == "visitor"
    finally:
        settings.feishu_admin_open_ids = previous_admin_open_ids


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
