from fastapi import APIRouter
from ..controllers.apus_controller import router as apus_router
from ..controllers.extractor_controller import router as extractor_router
from ..controllers.chat_controller import router as chat_router

api_router = APIRouter()

api_router.include_router(apus_router)
api_router.include_router(extractor_router)
api_router.include_router(chat_router)