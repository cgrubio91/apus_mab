# Backend APU Module

Módulo backend organizado para Análisis de Precios Unitarios (APU).

## Estructura

```
backend-apu/
├── __init__.py          # Exportaciones principales
├── app.py               # Aplicación FastAPI
├── api/
│   └── __init__.py      # Rutas API
├── models/
│   ├── __init__.py
│   └── apu.py           # Modelos Pydantic
├── services/
│   └── apu_service.py   # Lógica de negocio
└── controllers/
    ├── __init__.py
    ├── apus_controller.py
    └── extractor_controller.py
```

## Uso

```python
from backend_apu import create_app

app = create_app()
```

## Endpoints

- `GET /api/projects` - Lista de proyectos
- `GET /api/apus` - Consulta de APUs con filtros
- `DELETE /api/projects` - Eliminar proyecto
- `POST /api/extract-file` - Extraer APUs de archivo
- `POST /api/save-extracted` - Guardar APUs extraídos