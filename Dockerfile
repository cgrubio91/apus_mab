# === ETAPA 1: Compilar el Frontend de Angular ===
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend

# Copiar archivos de dependencias de Angular
COPY frontend/package*.json ./
RUN npm ci

# Copiar el código del frontend y compilarlo para producción
COPY frontend/ ./
RUN npm run build -- --configuration=production


# === ETAPA 2: Configurar el Backend de Python ===
FROM python:3.11-slim
WORKDIR /app

# Instalar dependencias del sistema (como libmagic para detectar tipos de archivos)
RUN apt-get update && apt-get install -y --no-install-recommends libmagic1 && rm -rf /var/lib/apt/lists/*

# Instalar dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar todo el código del backend y del proyecto
COPY . .

# Copiar los archivos compilados de Angular desde la Etapa 1 a una carpeta llamada 'static'
# NOTA: Asegúrate de si tu Angular compila directamente en "dist" o "dist/nombre-de-tu-app" 
# (Normalmente en Angular 17+ es dist/nombre-de-tu-app/browser o similar. Si no te funciona, revisamos esta ruta)
COPY --from=frontend-builder /app/frontend/dist/ /app/static/

EXPOSE 10000

CMD uvicorn src.presentation.main:app --host 0.0.0.0 --port ${PORT:-10000}