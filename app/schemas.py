from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, model_validator

# Допустимые статусы платежа
Status = Literal["pending", "succeeded", "failed", "refunded"]
# Способы оплаты
PaymentMethod = Literal["card", "sbp", "installment"]
# Допустимые сроки рассрочки в месяцах
InstallmentMonths = Literal[3, 6, 12]


class TariffOut(BaseModel):
    """Тариф в ответе GET /tariffs. 'price' — в копейках"""

    id: int
    title: str
    price: int


class PaymentCreate(BaseModel):
    """Тело запроса POST /payments."""

    tariff_id: int
    email: EmailStr
    method: PaymentMethod
    installment_months: InstallmentMonths | None = None
    promo_code: str | None = None

    @model_validator(mode="after")
    def validate_installment_fields(self) -> "PaymentCreate":
        """Для рассрочки срок обязателен, для card/sbp — запрещён."""
        if self.method == "installment" and self.installment_months is None:
            raise ValueError(
                "installment_months (3, 6 or 12) is required for method 'installment'"
            )
        if self.method != "installment" and self.installment_months is not None:
            raise ValueError("installment_months is only allowed for method 'installment'")
        return self


class PaymentOut(BaseModel):
    """Платёж в ответах API"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    tariff_id: int
    amount: int
    discount: int
    method: str
    installment_months: int | None
    schedule: list[int] | None
    email: str
    created_at: datetime


class BankWebhook(BaseModel):
    """Тело запроса POST /webhooks/bank."""

    payment_id: int
    status: Status
