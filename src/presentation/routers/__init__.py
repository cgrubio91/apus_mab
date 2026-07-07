from fastapi import APIRouter, Depends

from src.presentation.auth import get_current_user_flexible
from src.presentation.routers.apus import router as apus_router
from src.presentation.routers.extractor import router as extractor_router
from src.presentation.routers.chat import router as chat_router
from src.presentation.routers.analisis_apu import router as analisis_apu_router
from src.presentation.routers.notificaciones import router as notificaciones_router
from src.presentation.routers.auth import router as auth_router

api_router = APIRouter()

# Todos los routers de negocio requieren usuario autenticado. Se usa la
# variante "flexible" (header o ?token=) porque EventSource/SSE no puede
# enviar headers. El router de auth queda público (login/register).
_authenticated = [Depends(get_current_user_flexible)]

api_router.include_router(apus_router, dependencies=_authenticated)
api_router.include_router(extractor_router, dependencies=_authenticated)
api_router.include_router(chat_router, dependencies=_authenticated)
api_router.include_router(analisis_apu_router, dependencies=_authenticated)
api_router.include_router(notificaciones_router, dependencies=_authenticated)
api_router.include_router(auth_router)
