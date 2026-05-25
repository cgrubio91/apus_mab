# 🧠 Sistema de Memoria Conversacional

## 📋 Descripción

El bot ahora cuenta con **memoria conversacional** que le permite recordar el contexto de las últimas 5 interacciones de cada usuario. Esto permite hacer preguntas de seguimiento sin tener que repetir todo el contexto.

## ✨ Características

### 1. **Memoria Automática**
- Guarda automáticamente cada interacción (pregunta, SQL generado, respuesta)
- Recupera las últimas 5 conversaciones antes de procesar cada mensaje
- Incluye el contexto en el prompt de Gemini

### 2. **Consultas Contextuales**
Los usuarios ahora pueden hacer preguntas como:
- "Y de Medellín?" (en vez de repetir toda la consulta anterior)
- "Compáralo con el anterior"
- "Agrega también los precios"
- "Muéstrame lo mismo pero de Cali"

### 3. **Optimización**
- Índice en la base de datos para búsquedas rápidas por teléfono y fecha
- Límite de 5 mensajes para no sobrecargar el prompt
- Solo guarda consultas SELECT exitosas

## 🗄️ Estructura de la Base de Datos

**Tabla:** `historial_conversaciones`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | SERIAL | Identificador único |
| telefono | VARCHAR(50) | Número de WhatsApp del usuario |
| mensaje_usuario | TEXT | Pregunta del usuario |
| sql_generado | TEXT | Consulta SQL generada |
| respuesta_bot | TEXT | Respuesta enviada al usuario |
| timestamp | TIMESTAMP | Fecha y hora de la interacción |

**Índice:** `idx_telefono_timestamp` en (telefono, timestamp DESC)

## 🔧 Funciones Principales

### `guardar_conversacion(telefono, mensaje_usuario, sql_generado, respuesta_bot)`
Guarda una nueva interacción en el historial.

```python
guardar_conversacion(
    "whatsapp:+573001234567",
    "Dame los ítems más caros",
    "SELECT * FROM apus ORDER BY precio_unitario DESC LIMIT 5",
    "Hola! Aquí están los 5 ítems más caros..."
)
```

### `obtener_historial(telefono, limite=5)`
Recupera las últimas conversaciones del usuario en orden cronológico.

```python
historial = obtener_historial("whatsapp:+573001234567", limite=5)
# Retorna una lista de diccionarios con las conversaciones
```

## 💬 Ejemplos de Uso

### Ejemplo 1: Consulta Simple
**Usuario:** "Dame los ítems más caros de Bogotá"
**Bot:** ✅ Responde con listado

### Ejemplo 2: Pregunta Contextual
**Usuario:** "Y de Medellín?"
**Bot:** 🧠 Entiende que se refiere a "ítems más caros" pero de Medellín

### Ejemplo 3: Comparación
**Usuario:** "Compara los precios de excavación"
**Bot:** ✅ Genera tabla comparativa

**Usuario:** "Ahora solo de concreto"
**Bot:** 🧠 Entiende que debe comparar precios de concreto

## 📊 Flujo de Procesamiento

```
1. Usuario envía mensaje
   ↓
2. Sistema verifica autorización
   ↓
3. Recupera últimas 5 conversaciones del usuario
   ↓
4. Incluye contexto en el prompt de Gemini
   ↓
5. Gemini genera SQL considerando el contexto
   ↓
6. Ejecuta SQL y genera respuesta formateada
   ↓
7. Guarda la interacción en historial_conversaciones
   ↓
8. Envía respuesta al usuario
```

## 🛠️ Scripts de Mantenimiento

### Crear la tabla
```bash
python create_historial_table.py
```

### Probar el sistema
```bash
python test_memoria.py
```

### Verificar datos
```bash
python verificar_historial.py
```

### Limpiar historial antiguo (opcional)
```sql
-- Eliminar conversaciones más antiguas de 30 días
DELETE FROM historial_conversaciones 
WHERE timestamp < NOW() - INTERVAL '30 days';
```

### Ver estadísticas
```sql
-- Usuarios más activos
SELECT telefono, COUNT(*) as total_consultas
FROM historial_conversaciones
GROUP BY telefono
ORDER BY total_consultas DESC
LIMIT 10;

-- Consultas por día
SELECT DATE(timestamp) as fecha, COUNT(*) as consultas
FROM historial_conversaciones
GROUP BY DATE(timestamp)
ORDER BY fecha DESC
LIMIT 7;
```

## ⚙️ Configuración

El sistema está configurado para:
- **Límite de historial:** 5 mensajes por usuario
- **Formato de respuesta:** Adaptativo (listado/tabla/párrafo)
- **Almacenamiento:** Permanente en PostgreSQL
- **Optimización:** Índice en teléfono y timestamp

## 🔒 Seguridad y Privacidad

- Cada usuario solo puede ver su propio historial
- Las conversaciones se almacenan de forma segura en PostgreSQL
- No se comparte información entre usuarios
- Los datos pueden ser eliminados bajo petición

## 📝 Notas Técnicas

1. **PostgreSQL específico:** El código usa características específicas de PostgreSQL (SERIAL, TIMESTAMP, etc.)
2. **Memoria por usuario:** Cada usuario tiene su propia memoria conversacional aislada
3. **Performance:** El índice compuesto optimiza las consultas por teléfono y fecha
4. **Escalabilidad:** El límite de 5 mensajes mantiene el prompt de Gemini eficiente

## 🚀 Próximas Mejoras

- [ ] Agregar comando `/borrar_historial` para limpiar memoria
- [ ] Implementar resumen inteligente del historial (en vez de enviar todo)
- [ ] Agregar análisis de patrones de uso por usuario
- [ ] Implementar memoria semántica (conceptos vs mensajes exactos)
- [ ] Agregar métricas de satisfacción del usuario

---

**Última actualización:** 2025-12-04
**Versión:** 1.0.0
