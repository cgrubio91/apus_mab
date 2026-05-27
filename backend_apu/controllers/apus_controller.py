@router.get("/apus", response_model=ApuResponse, tags=["APUs"])
async def get_apus_endpoint(
    # Sintaxis válida de FastAPI para inyectar un objeto Pydantic como Query Params planos
    filters_params: Annotated[ApuQueryFilters, Query()],
    
    # CORRECCIÓN DEFINITIVA: Un solo backslash para \s, \-, \+ en el raw string
    search: Optional[str] = Query(None, pattern=r"^[a-zA-Z0-9\s\-_.,\+áéíóúÁÉÍÓÚñÑ]+$"),
    
    # Validación estricta usando lista blanca dinámica para ordenamiento
    sort_by: Optional[str] = Query(None, pattern=f"^({'|'.join(ALLOWED_SORT_FIELDS)})$"),
    
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
):
    try:
        # Extraemos el diccionario limpio omitiendo los valores nulos
        filters = {k: v for k, v in filters_params.model_dump().items() if v is not None}
        
        # Ejecución segura delegada al pool de hilos
        result = await asyncio.to_thread(
            get_apus,
            filters,
            limit,
            offset,
            sort_by=sort_by,
            sort_order=sort_order,
            search=search
        )
        
        # Logging estructurado con metadatos de telemetría de la consulta
        log.info("APU query executed smoothly", extra={
            "filters": filters,
            "limit": limit,
            "offset": offset,
            "search_term": search,
            "result_count": len(result.get("data", [])) if isinstance(result, dict) else 0
        })
        
        return result

    except DatabaseError as dbe:
        log.error("Database syntax or connection error in get_apus: %s", dbe)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al procesar la consulta en la base de datos."
        )
    except Exception:
        log.exception("Critical unexpected error in get_apus_endpoint")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ocurrió un error interno al recuperar los registros."
        )