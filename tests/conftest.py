from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pos_service.auth import hash_password
from pos_service.clients.sentry import SentryClient, get_sentry_client
from pos_service.clients.windcave import WindcaveClient, get_windcave_client
from pos_service.config import Settings, get_settings
from pos_service.db import Base, get_db, get_engine, get_session_factory
from pos_service.main import create_app
from pos_service.models import POSUser


@pytest.fixture
def settings() -> Settings:
    return Settings(
        sentry_base_url="http://sentry.test",
        sentry_api_token="test-token",
        windcave_base_url="http://windcave.test",
        windcave_user="test",
        windcave_key="test",
        windcave_station="test",
        windcave_mode="mock",
        tax_rate=0.0810,
        session_secret_key="test-key-32-bytes-long-padding-pad",
        session_ttl_hours=1,
        database_url="sqlite:///:memory:",
        allowed_origins="http://localhost:5173",
    )


@pytest.fixture
def engine() -> Generator[Engine, None, None]:
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def db(db_factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    sess = db_factory()
    try:
        yield sess
    finally:
        sess.close()


@pytest.fixture
def cashier(db: Session) -> POSUser:
    user = POSUser(
        username="mike",
        password_hash=hash_password("supersecret"),
        display_name="Mike Hightower",
        must_change_password=False,
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def admin(db: Session) -> POSUser:
    user = POSUser(
        username="admin",
        password_hash=hash_password("admin"),
        display_name="Administrator",
        must_change_password=True,
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def client(
    settings: Settings,
    engine: Engine,
    db_factory: sessionmaker[Session],
) -> Generator[TestClient, None, None]:
    app = create_app(settings=settings)

    def override_settings() -> Settings:
        return settings

    def override_get_db() -> Generator[Session, None, None]:
        sess = db_factory()
        try:
            yield sess
        finally:
            sess.close()

    def override_get_engine() -> Engine:
        return engine

    def fast_sentry_client() -> SentryClient:
        return SentryClient(
            base_url=settings.sentry_base_url,
            api_token=settings.sentry_api_token,
            mock=settings.sentry_mock,
            timeout_s=2.0,
            initial_backoff_s=0.0,
        )

    def fast_windcave_client() -> WindcaveClient:
        return WindcaveClient(
            base_url=settings.windcave_base_url,
            user=settings.windcave_user,
            key=settings.windcave_key,
            station=settings.windcave_station,
            vendor_id=settings.windcave_vendor_id,
            pos_name=settings.windcave_pos_name,
            device_id=settings.windcave_device_id,
            pos_version=settings.windcave_pos_version,
            currency=settings.windcave_currency,
            mock=settings.windcave_mock,
            timeout_s=2.0,
            initial_backoff_s=0.0,
        )

    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_engine] = override_get_engine
    app.dependency_overrides[get_sentry_client] = fast_sentry_client
    app.dependency_overrides[get_windcave_client] = fast_windcave_client
    get_session_factory.cache_clear()
    get_engine.cache_clear()
    get_settings.cache_clear()

    with TestClient(app) as c:
        yield c
