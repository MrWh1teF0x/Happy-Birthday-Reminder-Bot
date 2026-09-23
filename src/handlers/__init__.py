from aiogram import Router

from src.handlers.birthdays import router as birthdays_router
from src.handlers.start import router as start_router
from src.handlers.start import start_handler
from src.handlers.timezone import router as timezone_router

router = Router(name="root")
router.include_router(start_router)
router.include_router(timezone_router)
router.include_router(birthdays_router)

__all__ = ["router", "start_handler"]
