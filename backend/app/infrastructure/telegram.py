"""Bot API client used by the API process to issue Stars invoice links."""

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.types import LabeledPrice

from app.core.config import Settings
from app.domain.enums import Asset
from app.infrastructure.db.models import Invoice
from app.services.stars import StarsError

# Bot API test environment: same host, `/test/` after the token.
TEST_SERVER = TelegramAPIServer(
    base="https://api.telegram.org/bot{token}/test/{method}",
    file="https://api.telegram.org/file/bot{token}/test/{path}",
)


def build_bot(settings: Settings) -> Bot | None:
    if settings.telegram_bot_token is None:
        return None
    session = AiohttpSession(api=TEST_SERVER) if settings.telegram_test_env else AiohttpSession()
    return Bot(settings.telegram_bot_token.get_secret_value(), session=session)


async def create_stars_link(bot: Bot, invoice: Invoice) -> str:
    stars = invoice.quote(Asset.STARS)
    if stars is None:
        raise StarsError("Stars are not accepted for this invoice")
    # provider_token stays empty for Stars.
    return await bot.create_invoice_link(
        title=invoice.description[:32],
        description=f"{invoice.merchant.name}, order {invoice.reference}",
        payload=invoice.id,
        currency=Asset.STARS.value,
        prices=[LabeledPrice(label=invoice.description[:32], amount=stars)],
    )
