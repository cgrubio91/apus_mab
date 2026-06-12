from fastapi import APIRouter
from src.presentation.routers.apus import router as apus_router
from src.presentation.routers.extractor import router as extractor_router
from src.presentation.routers.chat import router as chat_router
from src.presentation.routers.analisis_apu import router as analisis_apu_router
from src.presentation.routers.auth import router as auth_router

api_router = APIRouter()

api_router.include_router(apus_router)
api_router.include_router(extractor_router)
api_router.include_router(chat_router)
api_router.include_router(analisis_apu_router)
api_router.include_router(auth_router)
