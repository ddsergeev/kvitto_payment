# Квитто — платёжный сервис (тестовое задание)

Небольшой API, через который онлайн-школа принимает оплату курса: список тарифов,
создание платежа с промокодом и рассрочкой, уведомления от банка о смене статуса.

## Запуск

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

API: http://127.0.0.1:8000

Интерактивная документация: http://127.0.0.1:8000/docs

## Тесты и линтер

```bash
pytest -v
ruff check app tests
```

## Эндпоинты

| Метод | Путь | Назначение |
|-|-|-|
| GET | `/tariffs` | Вывод списка тарифов |
| POST | `/payments` | Создание платежа с кодом 201; с заголовком `Idempotency-Key` повторный запрос возвращает существующий платёж с кодом 200 |
| GET | `/payments` | Вывод списка платежей с фильтрами `email` и `status` |
| GET | `/payments/{id}` | Вывод одного платежа; код 404, если платежа не существует |
| POST | `/webhooks/bank` | Уведомление банка о смене статуса |

## Примеры запросов

```bash
# Список тарифов
curl http://127.0.0.1:8000/tariffs

# Оплата картой с промокодом: amount = 1791000, discount = 199000
curl -X POST http://127.0.0.1:8000/payments \
  -H "Content-Type: application/json" \
  -d '{"tariff_id": 2, "email": "student@example.com", "method": "card", "promo_code": "kvitto10"}'

# Рассрочка Standard на 3 месяца с защитой от повторов:
# schedule = [663334, 663333, 663333] — сумма ровно 1990000
curl -X POST http://127.0.0.1:8000/payments \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: order-123" \
  -d '{"tariff_id": 2, "email": "student@example.com", "method": "installment", "installment_months": 3}'

# Повтор с тем же ключом — вернётся тот же платёж (200), дубль не создастся
curl -X POST http://127.0.0.1:8000/payments \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: order-123" \
  -d '{"tariff_id": 2, "email": "student@example.com", "method": "installment", "installment_months": 3}'

# Вебхук банка: платёж оплачен
curl -X POST http://127.0.0.1:8000/webhooks/bank \
  -H "Content-Type: application/json" \
  -d '{"payment_id": 1, "status": "succeeded"}'

# Запрещённый переход (pending → refunded) — 409 {"error": "invalid_transition"}, статус не изменится
curl -X POST http://127.0.0.1:8000/webhooks/bank \
  -H "Content-Type: application/json" \
  -d '{"payment_id": 1, "status": "refunded"}'

# Список платежей с фильтрами
curl "http://127.0.0.1:8000/payments?email=student@example.com&status=pending"
```