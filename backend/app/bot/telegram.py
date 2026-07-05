"""Demo bot: opens the shop Mini App and takes Stars payments for digital goods."""

import structlog
from aiogram import Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    PreCheckoutQuery,
    WebAppInfo,
)

from app.container import Container
from app.infrastructure.db.models import Invoice
from app.services.stars import StarsCharge, StarsError, check_pre_checkout, record_charge

log = structlog.get_logger()


def build_dispatcher(container: Container) -> Dispatcher:
    router = Router()
    shop_url = f"{container.settings.public_url}/shop?source=telegram"

    @router.message(CommandStart())
    async def start(message: Message) -> None:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Open the shop", web_app=WebAppInfo(url=shop_url))]
            ]
        )
        await message.answer(
            "Cellar Nine sells concert tickets and recordings.\n\n"
            "Tickets are paid in Gram or USDT on TON testnet, recordings in Telegram Stars. "
            "Nothing here costs real money.",
            reply_markup=keyboard,
        )

    @router.message(Command("paysupport"))
    async def pay_support(message: Message) -> None:
        await message.answer(
            "Payment questions: send the order code (it starts with TC-) and what went wrong. "
            "Stars payments for unused downloads are refunded within 7 days."
        )

    @router.pre_checkout_query()
    async def pre_checkout(query: PreCheckoutQuery) -> None:
        async with container.sessions() as session:
            try:
                await check_pre_checkout(
                    session, query.invoice_payload, query.total_amount, query.currency
                )
            except StarsError as exc:
                await query.answer(ok=False, error_message=str(exc))
                return
        await query.answer(ok=True)

    @router.message(F.successful_payment)
    async def paid(message: Message) -> None:
        payment = message.successful_payment
        if payment is None or message.from_user is None:
            return
        async with container.sessions() as session:
            invoice = await session.get(Invoice, payment.invoice_payload)
            if invoice is None:
                log.error("stars.unknown_invoice", payload=payment.invoice_payload)
                return
            result = await record_charge(
                container.processor(session),
                invoice,
                StarsCharge(
                    invoice_id=invoice.id,
                    amount=payment.total_amount,
                    charge_id=payment.telegram_payment_charge_id,
                    user_id=message.from_user.id,
                ),
            )
        log.info("stars.paid", invoice=payment.invoice_payload, outcome=result.outcome)
        if container.settings.stars_auto_refund and message.bot is not None:
            await message.bot.refund_star_payment(
                user_id=message.from_user.id,
                telegram_payment_charge_id=payment.telegram_payment_charge_id,
            )
            await message.answer(
                "Payment received, your download is waiting in the shop. "
                "This is a demo, so the Stars are already on their way back to you."
            )
            return
        await message.answer("Payment received. Your download is waiting in the shop.")

    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    return dispatcher
