import httpx
from sqlalchemy import select

from app.container import Container
from app.demo_shop.models import ShopOrder
from app.domain.enums import DeliveryState, Mode
from app.infrastructure.db.models import Merchant, WebhookDelivery, WebhookEndpoint
from app.services.auth import ApiKeyService
from app.services.webhooks import WebhookDispatcher


async def _api_key(container: Container, merchant: Merchant, mode: Mode = Mode.TEST) -> str:
    async with container.sessions() as s:
        return (await ApiKeyService(s).issue(merchant.id, mode, "backend")).secret


async def test_merchant_api_requires_key(client: httpx.AsyncClient) -> None:
    response = await client.post("/v1/invoices", json={"amount": "5.00", "description": "Poster"})
    assert response.status_code == 401


async def test_create_and_read_invoice_with_api_key(
    client: httpx.AsyncClient, container: Container, merchant: Merchant
) -> None:
    key = await _api_key(container, merchant)
    headers = {"Authorization": f"Bearer {key}"}
    created = await client.post(
        "/v1/invoices",
        headers=headers,
        json={
            "amount": "24.00",
            "description": "Neon Harbor live",
            "order_id": "A-1042",
            "product_kind": "offline_service",
            "metadata": {"seat": "standing"},
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "pending"
    assert body["mode"] == "test"
    assert {q["asset"] for q in body["quotes"]} == {"TON", "USDT"}
    assert body["pay_url"].endswith(body["id"])

    fetched = await client.get(f"/v1/invoices/{body['id']}", headers=headers)
    assert fetched.json()["metadata"] == {"seat": "standing"}

    listed = await client.get("/v1/invoices", headers=headers, params={"status": "pending"})
    assert listed.json()["total"] == 1


async def test_revoked_key_stops_working(
    client: httpx.AsyncClient, container: Container, merchant: Merchant
) -> None:
    async with container.sessions() as s:
        issued = await ApiKeyService(s).issue(merchant.id, Mode.TEST, "old")
        await ApiKeyService(s).revoke(merchant.id, issued.key.id)
    response = await client.get(
        "/v1/invoices", headers={"Authorization": f"Bearer {issued.secret}"}
    )
    assert response.status_code == 401


async def test_payment_page_and_sandbox_flow(
    client: httpx.AsyncClient, container: Container, merchant: Merchant
) -> None:
    key = await _api_key(container, merchant)
    invoice = (
        await client.post(
            "/v1/invoices",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "amount": "18.00",
                "description": "Friday Jazz Night",
                "product_kind": "offline_service",
            },
        )
    ).json()

    page = (await client.get(f"/api/pay/{invoice['id']}")).json()
    ton = next(o for o in page["options"] if o["asset"] == "TON")
    assert ton["deeplink"].startswith("ton://transfer/0Q")
    assert f"text={page['reference']}" in ton["deeplink"]
    assert ton["payload"]  # comment BOC for TON Connect

    half = await client.post(
        f"/api/pay/{invoice['id']}/simulate", json={"asset": "TON", "fraction": "0.5"}
    )
    assert half.json()["status"] == "partially_paid"
    page = (await client.get(f"/api/pay/{invoice['id']}")).json()
    assert [o["asset"] for o in page["options"]] == ["TON"]
    assert int(page["options"][0]["due_units"]) == int(ton["units"]) - int(ton["units"]) // 2

    rest = await client.post(f"/api/pay/{invoice['id']}/simulate", json={"asset": "TON"})
    assert rest.json()["status"] == "paid"


async def test_dashboard_needs_session_and_demo_login_works(
    client: httpx.AsyncClient, merchant: Merchant
) -> None:
    assert (await client.get("/api/dashboard/me")).status_code == 401
    login = await client.post("/api/auth/demo")
    assert login.status_code == 200
    me = await client.get("/api/dashboard/me")
    assert me.json()["name"] == "Cellar Nine"
    assert me.json()["demo"] is True


async def test_demo_store_cannot_change_wallet(
    client: httpx.AsyncClient, merchant: Merchant
) -> None:
    await client.post("/api/auth/demo")
    payload = (await client.post("/api/auth/ton-proof/payload")).json()["payload"]
    proof = {
        "address": "0:" + "aa" * 32,
        "network": "-3",
        "proof": {
            "timestamp": 1,
            "domain": {"lengthBytes": 13, "value": "checkout.test"},
            "payload": payload,
            "signature": "AA==",
        },
    }
    response = await client.post("/api/dashboard/wallet", json=proof)
    assert response.status_code == 403


async def test_csv_export_escapes_formulas(
    client: httpx.AsyncClient, container: Container, merchant: Merchant
) -> None:
    await client.post("/api/auth/demo")
    await client.post(
        "/api/dashboard/invoices",
        json={"amount": "3.00", "description": '=HYPERLINK("http://x")', "mode": "test"},
    )
    csv = await client.get("/api/dashboard/invoices/export.csv")
    assert csv.status_code == 200
    assert csv.headers["content-type"].startswith("text/csv")
    assert "'=HYPERLINK" in csv.text


async def test_shop_order_is_fulfilled_by_signed_webhook(
    client: httpx.AsyncClient, container: Container, merchant: Merchant
) -> None:
    async with container.sessions() as s:
        s.add(
            WebhookEndpoint(
                merchant_id=merchant.id,
                url=container.settings.shop_webhook_url,
                secret="whsec_c2VjcmV0LXNlY3JldC1zZWNyZXQ=",
            )
        )
        await s.commit()

    order = (await client.post("/api/shop/orders", json={"product_id": "ticket-jazz-nov14"})).json()
    await client.post(f"/api/pay/{order['invoice_id']}/simulate", json={"asset": "USDT"})

    # Deliver through the real dispatcher, routed back into the app instead of the network.
    transport = httpx.ASGITransport(app=client._transport.app)  # type: ignore[attr-defined]
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as loopback:
        dispatcher = WebhookDispatcher(
            container.sessions,
            loopback,
            trusted_urls=frozenset({container.settings.shop_webhook_url}),
        )
        assert await dispatcher.run_due() == 2  # invoice.created and invoice.paid

    fulfilled = (await client.get(f"/api/shop/orders/{order['id']}")).json()
    assert fulfilled["status"] == "fulfilled"
    assert fulfilled["access_code"]
    async with container.sessions() as s:
        states = set(await s.scalars(select(WebhookDelivery.state)))
        stored = await s.get_one(ShopOrder, order["id"])
    assert states == {DeliveryState.SUCCEEDED}
    assert stored.fulfilled_at is not None


async def test_shop_rejects_unsigned_webhook(client: httpx.AsyncClient, merchant: Merchant) -> None:
    response = await client.post("/api/shop/webhook", json={"type": "invoice.paid", "data": {}})
    assert response.status_code == 401


async def test_stars_are_simulated_in_demo_mode(
    client: httpx.AsyncClient, container: Container, merchant: Merchant
) -> None:
    order = (
        await client.post(
            "/api/shop/orders",
            json={"product_id": "rec-jazz-oct", "channel": "telegram_mini_app"},
        )
    ).json()
    page = (await client.get(f"/api/pay/{order['invoice_id']}")).json()
    assert page["stars_demo"] is True
    assert [o["asset"] for o in page["options"]] == ["XTR"]

    real = await client.post(f"/api/pay/{order['invoice_id']}/stars-link")
    assert real.status_code == 503

    paid = await client.post(
        f"/api/pay/{order['invoice_id']}/simulate", json={"asset": "XTR", "fraction": "0.5"}
    )
    assert paid.json()["status"] == "paid"  # Stars ignore partial amounts
