# Plan de Evolución y Cierre de Brechas — MAPUS

Este documento contiene la hoja de ruta y especificación detallada para la siguiente etapa de MAPUS, adaptada a la realidad operativa de la interventoría y obra civil en Colombia.

---

## Checklist de Implementación

- [x] **1. Schema de Base de Datos**
  - [x] Agregar columnas de AIU en tabla `proyectos` (`aiu_administracion`, `aiu_imprevistos`, `aiu_utilidad`, `aiu_iva_utilidad`).
  - [x] Agregar columnas para memoria técnica y aprobación de entidad en `solicitudes_apu` (`justificacion_tecnica`, `localizacion_obra`, `numero_acta_aprobacion`, `fecha_aprobacion_entidad`, `estado_incorporacion`).
- [x] **2. Parámetros de A.I.U. por Proyecto (Backend)**
  - [x] Actualizar DTOs y endpoints de proyectos (`GET/POST /proyectos-mapus`).
  - [x] Calcular cascada de AIU paramétrica en `constructor_apu.py` (Costo Directo + % Adm + % Imp + % Ut + % IVA).
- [x] **3. Flujo Unificado e Incorporación a Proyecto y Banco**
  - [x] Endpoint `PATCH /constructor-apu/{id}/justificacion` (datos de acta y justificación técnica).
  - [x] Endpoint `POST /constructor-apu/{id}/incorporar` (incorporar a `item_proyecto` y banco `apus`).
- [x] **4. Generador de Memoria Justificativa de Ítem No Previsto (PDF)**
  - [x] Módulo `src/infrastructure/reporting/memoria_pdf.py` con `reportlab`.
  - [x] Endpoint `GET /constructor-apu/{id}/memoria-pdf`.
- [x] **5. Exportación a Excel con Fórmulas Vivas**
  - [x] Módulo `src/infrastructure/reporting/apu_excel_formulado.py` con `openpyxl` (`=C*D`, `=SUM()`, etc.).
  - [x] Endpoint `GET /constructor-apu/{id}/export-excel`.
- [x] **6. Notificaciones en Tiempo Real (SSE)**
  - [x] Endpoint `GET /notificaciones/stream` (Server-Sent Events).
- [x] **7. Scheduler Automático en Background**
  - [x] Tarea en segundo plano en lifespan para refresco de índices DANE y contratos SECOP/ANI.
- [x] **8. Frontend (UI & UX)**
  - [x] Unificar menú lateral (retirar "Nuevos APU IA" legacy y redirigir).
  - [x] Indicador visual moderno de scraping web en vivo en el Constructor de APU.
  - [x] Sección de visto bueno de Entidad e incorporación formal al proyecto y banco.
  - [x] Botones de descarga de Memoria Técnica PDF y Excel formulado.
  - [x] Edición y visualización de AIU en proyectos.
  - [x] Consumo de notificaciones vía SSE en lugar de polling.
- [x] **9. Pruebas y Validación**
  - [x] Tests unitarios backend (`pytest`).
  - [x] Compilación frontend de producción (`ng build`).

---

## 1. Visión y Pilares

1. **Flujo de APU unificado (Liderado por Interventoría):**
   - El **Residente de Interventoría** crea el borrador asistido por IA (Constructor APU).
   - El contratista ajusta/completa los precios de mercado según sus cotizaciones.
   - El expediente se presenta a la Entidad contratante (IDU, Invías, Gobernación, etc.).
   - Una vez **aprobado por la Entidad**, el Residente de Interventoría realiza la **incorporación formal** al proyecto y al banco histórico de APUs.
   - Se retira el flujo legacy ("Nuevos APU IA") del menú para evitar duplicidades.

2. **Desglose Paramétrico del A.I.U. por Proyecto:**
   - Configuración en cada proyecto de: `% Administración`, `% Imprevistos`, `% Utilidad` y `% IVA sobre Utilidad`.
   - Cálculo automático del Costo Directo y desglose transparente del AIU en el Constructor de APU y en la ficha del proyecto.

3. **Generador de Memoria Justificativa de Ítem No Previsto (PDF Oficial):**
   - Generación de PDF institucional auditable:
     - Justificación técnica y necesidad del ítem en obra.
     - Memoria de cálculo de rendimientos y cuadrillas.
     - Cuadro comparativo de fuentes de soporte (banco, CYPE, SECOP II, cotizaciones).
     - Bloques de firmas formales: Residente Técnico de Interventoría, Director de Interventoría y Supervisor de la Entidad.

4. **Exportación a Excel Formulado (Fórmulas Vivas):**
   - Reemplazo de valores planos por fórmulas Excel reales en `openpyxl`:
     - Parcial de insumo: `=C10*D10` (Rendimiento × Valor Unitario).
     - Subtotales por categoría: `=SUMA(...)`.
     - Costo Directo, cascada de AIU y Valor Total formulados dinámicamente.

5. **Experiencia de Scraping Web en Vivo con Indicador Moderno:**
   - Feedback visual atractivo durante la cotización en vivo con CYPE/Homecenter/Mercado ("Consultando CYPE Colombia...", "Buscando tarifas de mano de obra vigentes...").

6. **Notificaciones en Tiempo Real vía Server-Sent Events (SSE):**
   - Reemplazo del polling HTTP de 60s (`GET /notificaciones`) por una conexión SSE reactiva ligera.

7. **Scheduler / Cron Background para Índices DANE y Fuentes Externas:**
   - Tarea en segundo plano dentro de FastAPI que refresca periódicamente series del DANE (ICCP) y contratos recientes de SECOP/ANI sin bloquear peticiones.

---

## 2. Cambios de Base de Datos (Schema)

Todos los cambios son aditivos en `src/infrastructure/database/schema.py`:

```sql
-- Parámetros de A.I.U. por proyecto
ALTER TABLE proyectos ADD COLUMN aiu_administracion DECIMAL(5,2) DEFAULT 15.00;
ALTER TABLE proyectos ADD COLUMN aiu_imprevistos DECIMAL(5,2) DEFAULT 3.00;
ALTER TABLE proyectos ADD COLUMN aiu_utilidad DECIMAL(5,2) DEFAULT 5.00;
ALTER TABLE proyectos ADD COLUMN aiu_iva_utilidad DECIMAL(5,2) DEFAULT 19.00;

-- Campos para la Memoria Justificativa en solicitudes_apu
ALTER TABLE solicitudes_apu ADD COLUMN justificacion_tecnica TEXT NULL;
ALTER TABLE solicitudes_apu ADD COLUMN localizacion_obra VARCHAR(255) NULL;
ALTER TABLE solicitudes_apu ADD COLUMN numero_acta_aprobacion VARCHAR(100) NULL;
ALTER TABLE solicitudes_apu ADD COLUMN fecha_aprobacion_entidad DATE NULL;
ALTER TABLE solicitudes_apu ADD COLUMN estado_incorporacion VARCHAR(30) DEFAULT 'pendiente';
```

---

## 3. Cambios por Módulos

### A. Backend (`src/`)

1. **Flujo Unificado e Incorporación:**
   - `POST /constructor-apu/{id}/incorporar`: Incorpora formalmente el APU aprobado por la entidad a la tabla `item_proyecto` y a la tabla `apus` (asociado a `proyecto_id`).
   - `PATCH /constructor-apu/{id}/justificacion`: Guarda justificación técnica, acta y fecha de aprobación de la entidad.

2. **Desglose de A.I.U.:**
   - Actualización de `proyectos` con los 4 campos de AIU.
   - Cálculo automático en `constructor_apu.py` de Costo Directo + Cascada de AIU personalizada del proyecto.

3. **Memoria Justificativa en PDF (`src/infrastructure/reporting/memoria_pdf.py`):**
   - Generación con `reportlab` de documento formal con encabezado de proyecto, justificación técnica, desglose de insumos, AIU, fuentes de soporte y espacio de 3 firmas.
   - Endpoint: `GET /constructor-apu/{id}/memoria-pdf`.

4. **Excel Formulado (`src/infrastructure/reporting/apu_excel_formulado.py`):**
   - Generación de archivo `.xlsx` con celdas de fórmulas vivas (`=C*D`, `=SUM()`, `=CostoDirecto*AIU`).
   - Endpoint: `GET /constructor-apu/{id}/export-excel`.

5. **Notificaciones SSE (`src/presentation/routers/notificaciones.py`):**
   - Endpoint `GET /notificaciones/stream` para streaming en tiempo real.

6. **Scheduler Background (`src/infrastructure/jobs/background_scheduler.py`):**
   - Tarea periódica no bloqueante para refrescar DANE (ICCP) y contratos SECOP/ANI.

---

### B. Frontend (`frontend/src/app/`)

1. **Menú Unificado:**
   - Ocultar "Nuevos APU IA" en el sidebar y concentrar el flujo en "Constructor APU" y "Banco de APUs".

2. **Constructor APU:**
   - Indicador visual animado mientras busca en la web en vivo.
   - Sección de aprobación de la Entidad (acta, fecha, justificación).
   - Botón de "Incorporar al Proyecto y Banco de APUs".
   - Botones de descarga de PDF oficial y Excel formulado.

3. **Proyectos:**
   - Formulario de proyecto con campos de AIU personalizables (% Adm, % Imp, % Ut, % IVA).
   - Visualización de la estructura de AIU en la tarjeta y detalle del proyecto.

4. **Notificaciones Reactivas:**
   - Suscripción al stream SSE de notificaciones en lugar del polling cada 60s.

---

## 4. Verificación y Calidad

1. Tests unitarios en pytest para AIU, PDF, Excel formulado y endpoints nuevos.
2. `ng build --configuration production` para validar compilación estricta en TypeScript.
3. Pruebas end-to-end de generación y apertura de archivos PDF y Excel en aplicaciones de escritorio.
