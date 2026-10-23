import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app, seed_tariffs
from app.models import Base, get_db

# In-memory SQLite: StaticPool держит одно соединение, чтобы все потоки
# (TestClient обрабатывает запросы в своих потоках) видели одну базу.
test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def client():
    """Клиент API с чистой базой, в которой уже сидированы тарифы."""
    Base.metadata.create_all(bind=test_engine)
    with TestSession() as db:
        seed_tariffs(db)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)
