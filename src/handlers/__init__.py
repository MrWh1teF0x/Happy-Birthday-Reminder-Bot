from aiogram import Router

from src.handlers.start import router as start_router
from src.handlers.start import start_handler

router = Router(name="root")
router.include_router(start_router)

__all__ = ["router", "start_handler"]
