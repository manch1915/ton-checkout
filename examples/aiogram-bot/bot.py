"""Ticket bot on aiogram 3 that takes payments through TON Checkout.

/buy creates an invoice through the merchant API and sends the payment link.
A small web server receives the signed webhook and sends the ticket when the invoice is paid.
"""

import asyncio
import os
import secrets

import httpx
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
from aiohttp import web
from standardwebhooks import Webhook, WebhookVerificationError

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHECKOUT_URL = os.environ.get("CHECKOUT_URL", "http://localhost:8010")
CHECKOUT_KEY = os.environ["CHECKOUT_API_KEY"]  # sk_test_... from the dashboard
WEBHOOK_SECRET = os.environ["CHECKOUT_WEBHOOK_SECRET"]  # whsec_... of your endpoint
PORT = int(os.environ.get("PORT", "8081"))

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
checkout = httpx.AsyncClient(
    base_url=CHECKOUT_URL, headers={"Authorization": f"Bearer {CHECKOUT_KEY}"}, timeout=15
)
# A real bot keeps orders in its database; fulfilment must be idempotent because
# webhooks can arrive more than once.
fulfilled: set[str] = set()


@dp.message(Command("buy"))
async def buy(message: Message) -> None:
    assert message.from_user is not None
    response = await checkout.post(
        "/v1/invoices",
        json={
            "amount": "18.00",
            "description": "Friday Jazz Night, 14 Nov",
            "product_kind": "offline_service",
            "channel": "telegram_mini_app",
            "order_id": f"tg-{message.from_user.id}-{secrets.token_hex(3)}",
            "metadata": {"chat_id": message.chat.id},
        },
    )
    response.raise_for_status()
    invoice = response.json()
    url = invoice["pay_url"]
    # Mini App buttons need HTTPS; a local checkout gets a normal link.
    button = (
        InlineKeyboardButton(text="Pay with Gram or USDT", web_app=WebAppInfo(url=url))
        if url.startswith("https://")
        else InlineKeyboardButton(text="Pay with Gram or USDT", url=url)
    )
    await message.answer(
        f"Ticket reserved for 30 minutes. Payment code: {invoice['reference']}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[button]]),
    )


async def ton_webhook(request: web.Request) -> web.Response:
    body = await request.read()
    try:
        event = Webhook(WEBHOOK_SECRET).verify(body, dict(request.headers))
    except WebhookVerificationError:
        return web.Response(status=401)

    if event["type"] == "invoice.paid":
        invoice = event["data"]["invoice"]
        if invoice["id"] not in fulfilled:
            fulfilled.add(invoice["id"])
            chat_id = invoice["metadata"].get("chat_id")
            if chat_id:
                code = secrets.token_hex(4).upper()
                await bot.send_message(chat_id, f"Paid, thank you. Your door code: {code}")
    return web.json_response({"ok": True})


async def main() -> None:
    app = web.Application()
    app.router.add_post("/webhooks/ton", ton_webhook)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()  # noqa: S104
    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()
        await checkout.aclose()


if __name__ == "__main__":
    asyncio.run(main())
