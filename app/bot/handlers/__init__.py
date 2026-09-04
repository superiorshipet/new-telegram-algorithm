from app.bot.handlers.accounts import create_accounts_router
from app.bot.handlers.opportunities import create_opportunities_router
from app.bot.handlers.registration import create_registration_router

__all__ = [
    "create_accounts_router",
    "create_opportunities_router",
    "create_registration_router",
]
