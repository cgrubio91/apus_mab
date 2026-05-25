# 🤖 Bot WhatsApp APUs - Memoria Conversacional

## 🎯 ¿Qué cambió?

El bot ahora tiene **MEMORIA** y puede entender el contexto de conversaciones anteriores.

## ✨ Ejemplos Prácticos

### ❌ ANTES (sin memoria)
```
Usuario: "Dame los ítems más caros de Bogotá"
Bot: [Lista de ítems de Bogotá]

Usuario: "Y de Medellín?"
Bot: ❌ "No entiendo a qué te refieres"
```

### ✅ AHORA (con memoria)
```
Usuario: "Dame los ítems más caros de Bogotá"
Bot: [Lista de ítems de Bogotá]

Usuario: "Y de Medellín?"
Bot: ✅ [Lista de ítems de Medellín] (entiende el contexto)

Usuario: "Compara los precios"
Bot: ✅ [Tabla comparando Bogotá vs Medellín]
```

## 🧠 ¿Cómo funciona?

1. **Guarda** cada pregunta y respuesta en la BD
2. **Recupera** las últimas 5 conversaciones antes de responder
3. **Incluye** ese contexto en el prompt de Gemini
4. Gemini **entiende** referencias como "el anterior", "ese mismo", etc.

## 📊 Mejoras en las Respuestas

### Formato Inteligente

**LISTADOS** (numerados):
```
1. Excavación manual - $45,000 (Bogotá)
2. Concreto 5000 PSI - $850,000 (Medellín)
3. Acero estructural - $720,000 (Cali)
```

**COMPARACIONES** (tablas):
```
Ciudad    | Precio      | Proyecto
----------------------------------------
Bogotá    | $45,000     | Metro L2
Medellín  | $32,500     | Vía Norte
Cali      | $38,000     | Túnel Sur
```

**TOTALES** (destacados):
```
💰 PRECIO PROMEDIO: $425,000
📊 Total de registros: 15
```

## 🚀 Instalación Rápida

```bash
# 1. Crear la tabla de historial
python create_historial_table.py

# 2. Probar el sistema (opcional)
python test_memoria.py

# 3. Verificar que funciona (opcional)
python verificar_historial.py

# 4. ¡Listo! El bot ya tiene memoria
```

## 📝 Archivos Nuevos

| Archivo | Propósito |
|---------|-----------|
| `create_historial_table.py` | Crea la tabla en PostgreSQL |
| `test_memoria.py` | Prueba el sistema de memoria |
| `verificar_historial.py` | Verifica datos guardados |
| `MEMORIA_CONVERSACIONAL.md` | Documentación completa |
| `README_MEMORIA.md` | Este archivo (guía rápida) |

## 🔧 Cambios en main.py

### ➕ Nuevas funciones:
- `guardar_conversacion()` - Guarda cada interacción
- `obtener_historial()` - Recupera últimas 5 conversaciones

### 🔄 Flujo actualizado:
```
Mensaje recibido
    ↓
Recuperar historial (últimas 5)
    ↓
Incluir contexto en prompt
    ↓
Generar SQL con contexto
    ↓
Guardar nueva conversación
    ↓
Enviar respuesta
```

## 💡 Casos de Uso

### Caso 1: Consultas Secuenciales
```
"Dame excavación de Bogotá"
"Ahora de Medellín"
"Compara ambas"
```

### Caso 2: Refinamiento
```
"Dame todos los ítems"
"Solo los más caros"
"Agrega el precio sin AIU"
```

### Caso 3: Exploración
```
"Qué proyectos hay?"
"Cuál es el más grande?"
"Muestra sus ítems principales"
```

## ⚙️ Configuración

**Límite de historial:** 5 mensajes
- Puedes cambiar esto en `main.py` línea 222:
```python
historial = obtener_historial(from_number, limite=5)  # Cambiar 5 por otro número
```

## 🗑️ Mantenimiento

### Limpiar historial antiguo (más de 30 días)
```sql
DELETE FROM historial_conversaciones 
WHERE timestamp < NOW() - INTERVAL '30 days';
```

### Ver estadísticas
```sql
-- Usuarios más activos
SELECT telefono, COUNT(*) as consultas
FROM historial_conversaciones
GROUP BY telefono
ORDER BY consultas DESC;
```

## 🎨 Formatos de Respuesta

El bot ahora detecta automáticamente el tipo de consulta:

| Tipo | Formato | Ejemplo |
|------|---------|---------|
| **Listado** | Numeración | "Dame los 10 más caros" |
| **Comparación** | Tabla ASCII | "Compara precios de..." |
| **Total** | Destacado | "Cuántos ítems hay?" |
| **Simple** | Párrafo | "Qué es un APU?" |

## ✅ Checklist de Implementación

- [x] Tabla `historial_conversaciones` creada
- [x] Funciones de memoria implementadas
- [x] Contexto incluido en prompts
- [x] Guardado automático de conversaciones
- [x] Formato inteligente de respuestas
- [x] Detección de tipo de consulta
- [x] Optimización con índices
- [x] Scripts de prueba creados
- [x] Documentación completa

## 🚨 Importante

- Cada usuario tiene su **propia memoria** (aislada)
- La memoria se guarda **permanentemente** en PostgreSQL
- Solo las últimas **5 conversaciones** se usan para contexto
- Solo se guardan consultas **SELECT exitosas**

## 📞 Soporte

Si hay algún problema:
1. Verificar que la tabla existe: `python verificar_historial.py`
2. Ver los logs del servidor
3. Revisar la conexión a PostgreSQL

---

**¡El bot ahora es mucho más inteligente! 🧠✨**
