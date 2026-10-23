from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.models import Base, Payment, SessionLocal, Tariff, engine, get_db
from app.schemas import BankWebhook, PaymentCreate, PaymentOut, Status, TariffOut

PROMO_CODE = "KVITTO10"
PROMO_DISCOUNT_PERCENT = 10

# Тарифы, создаваемые при старте (название и цена в копейках)
STARTER_TARIFFS = [
    ("Basic", 990_000),
    ("Standard", 1_990_000),
    ("Premium", 2_990_000),
]

# Разрешённые переходы статусов: pending -> succeeded | failed, succeeded -> refunded
# Любой другой переход запрещён
ALLOWED_TRANSITIONS = {
    ("pending", "succeeded"),
    ("pending", "failed"),
    ("succeeded", "refunded"),
}

def calc_discount(price: int, promo_code: str | None) -> int:
    """Размер скидки в копейках.
    Промокод сравнивается без учёта регистра и без пробелов по краям.
    Пустое значение означает «без промокода». Неизвестный непустой код —
    ValueError, который эндпоинт превращает в ответ 422.
    """
    promo = (promo_code or "").strip().upper()
    if not promo:
        return 0
    if promo != PROMO_CODE:
        raise ValueError(f"unknown promo code: {promo_code!r}")
    return price * PROMO_DISCOUNT_PERCENT // 100

def build_schedule(amount: int, months: int) -> list[int]:
    """График рассрочки: 'months' платежей суммой ровно 'amount' копеек.
    Деление идёт в копейках; остаток от деления распределяется по одной
    лишней копейке в самые первые платежи.
    """
    base, extra = divmod(amount, months)
    return [base + 1] * extra + [base] * (months - extra)

def seed_tariffs(db: Session) -> None:
    """Создаёт тарифы если их ещё нет"""
    if db.query(Tariff).first() is not None:
        return
    db.add_all(Tariff(title=title, price=price) for title, price in STARTER_TARIFFS)
    db.commit()

@asynccontextmanager
async def lifespan(_: FastAPI):
    """При старте создаём таблицы и сидируем тарифы."""
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_tariffs(db)
    yield

app = FastAPI(title="Kvitto Payments", version="1.0.0", lifespan=lifespan)

@app.get("/tariffs", response_model=list[TariffOut])
def list_tariffs(db: Session = Depends(get_db)) -> list[Tariff]:
    """Список тарифов"""
    return db.query(Tariff).order_by(Tariff.id).all()

@app.post("/payments", response_model=PaymentOut, status_code=201)
def create_payment(
    payload: PaymentCreate,
    response: Response,
    idempotency_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Создаёт платёж (201).
    Если передан заголовок Idempotency-Key и платёж с таким ключом уже
    существует — возвращается тот же платёж с кодом 200, дубль не создаётся.
    """
    tariff = db.get(Tariff, payload.tariff_id)
    if tariff is None:
        raise HTTPException(status_code=422, detail="tariff not found")

    if idempotency_key:
        existing = (
            db.query(Payment).filter(Payment.idempotency_key == idempotency_key).first()
        )
        if existing is not None:
            response.status_code = 200
            return existing

    try:
        discount = calc_discount(tariff.price, payload.promo_code)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    amount = tariff.price - discount
    schedule = (
        build_schedule(amount, payload.installment_months)
        if payload.method == "installment"
        else None
    )

    payment = Payment(
        tariff_id=tariff.id,
        amount=amount,
        discount=discount,
        method=payload.method,
        installment_months=payload.installment_months,
        schedule=schedule,
        idempotency_key=idempotency_key,
        email=payload.email,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


@app.get("/payments", response_model=list[PaymentOut])
def list_payments(
    email: str | None = None,
    status: Status | None = None,
    db: Session = Depends(get_db),
) -> list[Payment]:
    """Список платежей; опционально фильтрует по email и status"""
    query = db.query(Payment)
    if email is not None:
        query = query.filter(Payment.email == email)
    if status is not None:
        query = query.filter(Payment.status == status)
    return query.order_by(Payment.id).all()


@app.get("/payments/{payment_id}", response_model=PaymentOut)
def get_payment(payment_id: int, db: Session = Depends(get_db)) -> Payment:
    """Один платёж; 404, если платежа нет"""
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="payment not found")
    return payment


@app.post("/webhooks/bank")
def bank_webhook(payload: BankWebhook, db: Session = Depends(get_db)):
    """Уведомление банка о смене статуса платежа.
    Платежа нет -> 404; запрещённый переход -> 409 {"error": "invalid_transition"}
    (статус не меняется); успех → 200 {"result": "ok"}.
    """
    payment = db.get(Payment, payload.payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="payment not found")

    if (payment.status, payload.status) not in ALLOWED_TRANSITIONS:
        return JSONResponse(status_code=409, content={"error": "invalid_transition"})

    payment.status = payload.status
    db.commit()
    return {"result": "ok"}
