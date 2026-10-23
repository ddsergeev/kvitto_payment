from fastapi.testclient import TestClient

# standard в копейках и standard со скидкой 10%
STANDARD_PRICE = 1_990_000
STANDARD_PROMO_AMOUNT = 1_791_000
STANDARD_PROMO_DISCOUNT = 199_000


def make_payment(
    client: TestClient,
    headers: dict[str, str] | None = None,
    **overrides,
):
    """Создаёт платёж со значениями по умолчанию (standard, card)."""
    payload = {"tariff_id": 2, "email": "student@example.com", "method": "card"}
    payload.update(overrides)
    return client.post("/payments", json=payload, headers=headers or {})


def test_tariffs_list(client):
    """Вывод тарифов"""
    resp = client.get("/tariffs")
    assert resp.status_code == 200
    tariffs = resp.json()
    assert [t["title"] for t in tariffs] == ["Basic", "Standard", "Premium"]
    assert [t["price"] for t in tariffs] == [990_000, 1_990_000, 2_990_000]


def test_amount_without_promo(client):
    """Тест создания платежа без промокода"""
    resp = make_payment(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["amount"] == STANDARD_PRICE
    assert body["discount"] == 0
    assert body["status"] == "pending"
    assert body["schedule"] is None
    assert body["installment_months"] is None
    assert body["method"] == "card"
    assert body["tariff_id"] == 2
    assert body["email"] == "student@example.com"
    assert body["created_at"]


def test_amount_with_promo_case_insensitive(client):
    """Тест промокода"""
    for promo in ("KVITTO10", "kvitto10", " KvItTo10 "):
        resp = make_payment(client, promo_code=promo)
        assert resp.status_code == 201
        body = resp.json()
        assert body["discount"] == STANDARD_PROMO_DISCOUNT
        assert body["amount"] == STANDARD_PROMO_AMOUNT


def test_unknown_promo_422(client):
    """Тест несуществующего промокода"""
    resp = make_payment(client, promo_code="SALE2026")
    assert resp.status_code == 422
    assert client.get("/payments").json() == []


def test_installment_schedule_sum_is_exact(client):
    """Тест правильной цены рассрочки"""
    for months in (3, 6, 12):
        resp = make_payment(client, method="installment", installment_months=months)
        assert resp.status_code == 201
        body = resp.json()
        schedule = body["schedule"]
        assert body["amount"] == STANDARD_PRICE
        assert len(schedule) == months
        assert sum(schedule) == STANDARD_PRICE
        assert schedule[0] >= schedule[-1]
        assert schedule[0] - schedule[-1] <= 1


def test_installment_example_from_task(client):
    """Тест из примера"""
    resp = make_payment(client, method="installment", installment_months=3)
    assert resp.json()["schedule"] == [663_334, 663_333, 663_333]


def test_installment_validation(client):
    """Тест правильной работы рассрочки"""
    # рассрочка без installment_months
    assert make_payment(client, method="installment").status_code == 422
    # недопустимый срок (только 3, 6 или 12)
    assert (
        make_payment(client, method="installment", installment_months=5).status_code
        == 422
    )
    # installment_months при способе оплаты card
    assert make_payment(client, method="card", installment_months=3).status_code == 422


def test_idempotency_key_reuse(client):
    """Повторный запрос с тем же ключом не создаёт второй платёж."""
    body = {"tariff_id": 2, "email": "student@example.com", "method": "card"}
    first = client.post("/payments", json=body, headers={"Idempotency-Key": "order-123"})
    assert first.status_code == 201

    second = client.post("/payments", json=body, headers={"Idempotency-Key": "order-123"})
    assert second.status_code == 200  # не 201: платёж уже существовал
    assert second.json() == first.json()  # вернулся тот же платёж

    payments = client.get("/payments").json()
    assert len(payments) == 1  # дубля нет

    # другой ключ — это новый платёж
    third = client.post("/payments", json=body, headers={"Idempotency-Key": "order-456"})
    assert third.status_code == 201
    assert third.json()["id"] != first.json()["id"]


def test_get_missing_payment_404(client):
    """Несуществующий платеж"""
    resp = client.get("/payments/9999")
    assert resp.status_code == 404


def test_webhook_allowed_transitions(client):
    """Переходы статусов банка"""
    payment_id = make_payment(client).json()["id"]

    resp = client.post(
        "/webhooks/bank", json={"payment_id": payment_id, "status": "succeeded"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"result": "ok"}
    assert client.get(f"/payments/{payment_id}").json()["status"] == "succeeded"

    resp = client.post(
        "/webhooks/bank", json={"payment_id": payment_id, "status": "refunded"}
    )
    assert resp.status_code == 200
    assert client.get(f"/payments/{payment_id}").json()["status"] == "refunded"


def test_webhook_forbidden_transition(client):
    """Запрещённый переход возвращает 409 и не меняет статус"""
    payment_id = make_payment(client).json()["id"]

    resp = client.post(
        "/webhooks/bank", json={"payment_id": payment_id, "status": "refunded"}
    )
    assert resp.status_code == 409
    assert resp.json() == {"error": "invalid_transition"}
    assert client.get(f"/payments/{payment_id}").json()["status"] == "pending"


def test_webhook_same_status_forbidden(client):
    """Повторный вебхук с тем же статусом — тоже запрещённый переход."""
    payment_id = make_payment(client).json()["id"]
    resp = client.post(
        "/webhooks/bank", json={"payment_id": payment_id, "status": "pending"}
    )
    assert resp.status_code == 409
    assert resp.json() == {"error": "invalid_transition"}


def test_webhook_failed_is_terminal(client):
    """Вебхук failed -> succeeded"""
    payment_id = make_payment(client).json()["id"]
    assert (
        client.post(
            "/webhooks/bank", json={"payment_id": payment_id, "status": "failed"}
        ).status_code
        == 200
    )
    resp = client.post(
        "/webhooks/bank", json={"payment_id": payment_id, "status": "succeeded"}
    )
    assert resp.status_code == 409
    assert client.get(f"/payments/{payment_id}").json()["status"] == "failed"


def test_webhook_unknown_payment_404(client):
    """Вебхук несуществующего платежа"""
    resp = client.post("/webhooks/bank", json={"payment_id": 9999, "status": "succeeded"})
    assert resp.status_code == 404


def test_unknown_tariff_422(client):
    """Тест платежа по несуществующему тарифу"""
    assert make_payment(client, tariff_id=999).status_code == 422


def test_invalid_email_422(client):
    """Создание платежа с невалидным email"""
    assert make_payment(client, email="not-an-email").status_code == 422
