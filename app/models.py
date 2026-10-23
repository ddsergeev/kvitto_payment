from collections.abc import Generator
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    sessionmaker,
)

DATABASE_URL = "sqlite:///./kvitto.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Базовый класс всех ORM-моделей."""


class Tariff(Base):
    """Тариф онлайн-школы. 'price' — цена курса в копейках."""

    __tablename__ = "tariffs"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(100))
    price: Mapped[int] = mapped_column(Integer)


class Payment(Base):
    """Платёж за тариф.
    amount — сумма к оплате (цена тарифа минус скидка),
    discount — размер скидки (0, если промокода не было),
    schedule — график рассрочки (список сумм в копейках) или None,
    idempotency_key — значение заголовка Idempotency-Key. Уникальный
    индекс защищает от дублей, при этом NULL (запрос без ключа)
    может встречаться сколько угодно раз.
    """

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    tariff_id: Mapped[int] = mapped_column(ForeignKey("tariffs.id"))
    amount: Mapped[int] = mapped_column(Integer)
    discount: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(20))
    installment_months: Mapped[int | None] = mapped_column(Integer)
    schedule: Mapped[list[int] | None] = mapped_column(JSON)
    idempotency_key: Mapped[str | None] = mapped_column(String(200), unique=True)
    email: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


def get_db() -> Generator[Session, None, None]:
    """Отдаёт сессию БД на время запроса и закрывает её после ответа."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
