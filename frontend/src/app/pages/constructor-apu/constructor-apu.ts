import { Component, ChangeDetectorRef, OnDestroy, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { ApuService, FilterOptions } from '../../services/apu';

interface FilaPropuesta {
  incluir: boolean;
  tipo_insumo: string;
  descripcion: string;
  unidad: string;
  rendimiento: number | null;
  precio: number | null;
  fuente: string;
  fuente_link: string;
}

interface BorradorResumen {
  id: number;
  descripcion_actividad?: string;
  ciudad?: string;
  codigo_item?: string;
  total_insumos?: number;
}

@Component({
  selector: 'app-constructor-apu',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './constructor-apu.html',
  styleUrl: './constructor-apu.scss',
})
export class ConstructorApu implements OnInit, OnDestroy {
  private apuService = inject(ApuService);
  private cdr = inject(ChangeDetectorRef);
  private router = inject(Router);
  private route = inject(ActivatedRoute);

  paso = 1;
  pasoMax = 1;
  isLoading = false;
  errorMessage = '';
  successMessage = '';

  descripcionActividad = '';
  unidadActividad = '';
  codigoItem = '';
  ciudad = '';
  ciudades: string[] = [];
  continuarId: number | null = null;
  borradores: BorradorResumen[] = [];

  solicitudId: number | null = null;
  proyectoId: number | null = null;
  proyectosDisponibles: any[] = [];
  estadoSolicitud = 'borrador';

  propuesta: any = null;
  desgloseAiu: any = null;
  filas: FilaPropuesta[] = [];
  referenciasUsadas: any[] = [];
  conversacion: { rol: 'ia' | 'usuario'; texto: string }[] = [];
  respuestasPreguntas: string[] = [];

  progresoTexto = '';
  progresoPaso = 1;
  private progresoTimer: ReturnType<typeof setInterval> | null = null;

  insumosBorrador: any[] = [];
  preciosContratista: Record<number, number | null> = {};
  sinCoincidencia: any[] = [];

  justificacionTecnica = '';
  localizacionObra = '';
  numeroActaAprobacion = '';
  fechaAprobacionEntidad = '';
  estadoIncorporacion = 'pendiente';
  incorporando = false;
  descargandoPdf = false;
  descargandoExcel = false;

  omitirSinPrecio = false;

  tiposInsumo = ['Materiales', 'Equipos', 'Mano de obra', 'Transporte', 'Herramienta', 'Otro'];

  private sugerenciaRetries = 0;
  private sugerenciaMaxRetries = 2;
  private retryTimer: ReturnType<typeof setInterval> | null = null;
  retryCountdown = 0;

  ngOnInit(): void {
    this.apuService.getFilterOptions().subscribe({
      next: (opts: FilterOptions) => {
        this.ciudades = opts.ciudades || [];
        this.cdr.markForCheck();
      },
      error: () => { /* los selects quedan vacíos */ },
    });

    this.apuService.getProyectosMapus().subscribe({
      next: (res) => {
        this.proyectosDisponibles = res.proyectos || [];
        this.cdr.markForCheck();
      },
      error: () => { /* silencioso */ },
    });

    this.cargarListaBorradores();

    const idParam = this.route.snapshot.queryParamMap.get('id');
    if (idParam) {
      const id = Number(idParam);
      if (id > 0) {
        this.continuarId = id;
        this.continuarBorrador();
      }
    }
  }

  ngOnDestroy(): void {
    this.detenerProgresoScraping();
    if (this.retryTimer) {
      clearInterval(this.retryTimer);
      this.retryTimer = null;
    }
  }

  cargarListaBorradores(): void {
    this.apuService.listarBorradoresConstructor().subscribe({
      next: (res) => {
        this.borradores = res.borradores || [];
        this.cdr.markForCheck();
      },
      error: () => { this.borradores = []; },
    });
  }

  eliminarBorrador(id: number, event?: Event): void {
    event?.stopPropagation();
    if (!confirm(`¿Eliminar el borrador #${id}? Esta acción no se puede deshacer.`)) return;
    this.isLoading = true;
    this.apuService.deleteSolicitud(id).subscribe({
      next: () => {
        this.isLoading = false;
        this.successMessage = `Borrador #${id} eliminado correctamente.`;
        this.cargarListaBorradores();
        if (this.solicitudId === id) {
          this.solicitudId = null;
          this.paso = 1;
        }
        this.cdr.markForCheck();
      },
      error: (e) => this._fallo(e, 'No se pudo eliminar el borrador.'),
    });
  }

  iniciarProgresoScraping(): void {
    const pasos = [
      'Paso 1/4: Interpretando especificaciones técnicas con Inteligencia Artificial...',
      'Paso 2/4: Consultando tarifas de mercado en CYPE Colombia y Homecenter...',
      'Paso 3/4: Evaluando rendimientos históricos y referencias viales...',
      'Paso 4/4: Consolidando propuesta y calculando cascada de A.I.U....',
    ];
    this.progresoPaso = 1;
    this.progresoTexto = pasos[0];
    let idx = 0;
    if (this.progresoTimer) clearInterval(this.progresoTimer);
    this.progresoTimer = setInterval(() => {
      idx++;
      if (idx < pasos.length) {
        this.progresoPaso = idx + 1;
        this.progresoTexto = pasos[idx];
        this.cdr.markForCheck();
      }
    }, 2500);
  }

  detenerProgresoScraping(): void {
    if (this.progresoTimer) {
      clearInterval(this.progresoTimer);
      this.progresoTimer = null;
    }
  }

  get totalInsumos(): number {
    return this.filas.length;
  }

  get preguntasIa(): string[] {
    return this.propuesta?.preguntas || [];
  }

  get conPrecio(): number {
    return Object.values(this.preciosContratista).filter(v => v !== null && Number(v) > 0).length;
  }

  aiuConfig = {
    administracion: 15,
    imprevistos: 3,
    utilidad: 5,
    iva_utilidad: 19,
  };
  editandoAiu = false;
  guardandoAiuProyecto = false;

  get filasIncluidas(): FilaPropuesta[] {
    return this.filas.filter(f => f.incluir && (f.descripcion || '').trim());
  }

  get costoDirectoPreliminar(): number {
    return this.filasIncluidas.reduce((s, f) => {
      const p = Number(f.precio);
      const r = f.rendimiento == null ? 1 : Number(f.rendimiento);
      if (!p || p <= 0) return s;
      return s + p * (Number.isFinite(r) && r > 0 ? r : 1);
    }, 0);
  }

  get desgloseAiuVivo(): any {
    const pct = this.aiuConfig;
    const cd = Math.round(this.costoDirectoPreliminar * 100) / 100;
    const pctAdm = Number(pct.administracion || 0);
    const pctImp = Number(pct.imprevistos || 0);
    const pctUt = Number(pct.utilidad || 0);
    const pctIva = Number(pct.iva_utilidad || 0);
    const valA = Math.round(cd * (pctAdm / 100) * 100) / 100;
    const valI = Math.round(cd * (pctImp / 100) * 100) / 100;
    const valU = Math.round(cd * (pctUt / 100) * 100) / 100;
    const valIva = Math.round(valU * (pctIva / 100) * 100) / 100;
    const totalAiu = Math.round((valA + valI + valU + valIva) * 100) / 100;
    const totalPct = cd > 0 ? Math.round((totalAiu / cd) * 10000) / 100 : (pctAdm + pctImp + pctUt);
    return {
      costo_directo: cd,
      porcentajes: {
        administracion: pctAdm,
        imprevistos: pctImp,
        utilidad: pctUt,
        iva_utilidad: pctIva,
        aiu_total_porcentaje: totalPct,
      },
      valores: {
        administracion: valA,
        imprevistos: valI,
        utilidad: valU,
        iva_utilidad: valIva,
        total_aiu: totalAiu,
        costo_total: Math.round((cd + totalAiu) * 100) / 100,
      },
    };
  }

  get puedeIncorporar(): boolean {
    return ['aprobado_legal', 'firmado_legal'].includes(this.estadoSolicitud)
      && this.estadoIncorporacion !== 'incorporado';
  }

  parcialFila(f: FilaPropuesta): number | null {
    if (f.precio == null || Number(f.precio) <= 0) return null;
    const r = f.rendimiento == null ? 1 : Number(f.rendimiento);
    return Number(f.precio) * (Number.isFinite(r) && r > 0 ? r : 1);
  }

  irAPaso(n: number): void {
    if (n < 1 || n > 4 || n > this.pasoMax) return;
    if (n === 3 && !this.insumosBorrador.length && this.paso < 3) return;
    this.paso = n;
  }

  crearYSugerir(): void {
    if ((this.descripcionActividad || '').trim().length < 5) {
      this.errorMessage = 'Describe la actividad con al menos 5 caracteres (ej.: "Construcción de pilotes de concreto de 60 cm").';
      return;
    }
    this.isLoading = true;
    this.errorMessage = '';
    this.iniciarProgresoScraping();
    this.apuService.crearBorrador({
      descripcion_actividad: this.descripcionActividad.trim(),
      unidad_actividad: this.unidadActividad.trim() || null,
      codigo_item: this.codigoItem.trim() || null,
      ciudad: this.ciudad || null,
      proyecto_id: this.proyectoId || null,
    }).subscribe({
      next: (res) => {
        this.solicitudId = res.solicitud_id;
        this.estadoSolicitud = 'borrador';
        this.cargarListaBorradores();
        this.generarSugerencia();
      },
      error: (e) => this._fallo(e, 'No se pudo crear el borrador.'),
    });
  }

  onProyectoChange(): void {
    if (!this.proyectoId) return;
    const proy = this.proyectosDisponibles.find(p => Number(p.id) === Number(this.proyectoId));
    if (proy) {
      if (proy.aiu_administracion != null) this.aiuConfig.administracion = Number(proy.aiu_administracion);
      if (proy.aiu_imprevistos != null) this.aiuConfig.imprevistos = Number(proy.aiu_imprevistos);
      if (proy.aiu_utilidad != null) this.aiuConfig.utilidad = Number(proy.aiu_utilidad);
      if (proy.aiu_iva_utilidad != null) this.aiuConfig.iva_utilidad = Number(proy.aiu_iva_utilidad);
      this.cdr.markForCheck();
    }
  }

  guardarAiuEnProyecto(): void {
    if (!this.proyectoId) {
      this.errorMessage = 'Selecciona un proyecto antes de guardar la configuración de A.I.U.';
      return;
    }
    this.guardandoAiuProyecto = true;
    this.apuService.updateProyectoMapus(this.proyectoId, {
      aiu_administracion: Number(this.aiuConfig.administracion),
      aiu_imprevistos: Number(this.aiuConfig.imprevistos),
      aiu_utilidad: Number(this.aiuConfig.utilidad),
      aiu_iva_utilidad: Number(this.aiuConfig.iva_utilidad),
    }).subscribe({
      next: () => {
        this.guardandoAiuProyecto = false;
        this.successMessage = 'Porcentajes de A.I.U. guardados exitosamente en el proyecto.';
        const proy = this.proyectosDisponibles.find(p => Number(p.id) === Number(this.proyectoId));
        if (proy) {
          proy.aiu_administracion = Number(this.aiuConfig.administracion);
          proy.aiu_imprevistos = Number(this.aiuConfig.imprevistos);
          proy.aiu_utilidad = Number(this.aiuConfig.utilidad);
          proy.aiu_iva_utilidad = Number(this.aiuConfig.iva_utilidad);
        }
        this.cdr.markForCheck();
      },
      error: (e) => {
        this.guardandoAiuProyecto = false;
        this.errorMessage = e?.error?.detail || 'No se pudo guardar la configuración de A.I.U. en el proyecto.';
        this.cdr.markForCheck();
      },
    });
  }

  generarSugerencia(): void {
    if (!this.solicitudId) return;
    this.isLoading = true;
    this.errorMessage = '';
    this.retryCountdown = 0;
    this.iniciarProgresoScraping();
    this.apuService.sugerirEstructura(this.solicitudId, this.aiuConfig).subscribe({
      next: (res) => {
        this.sugerenciaRetries = 0;
        this._cargarPropuesta(res);
      },
      error: (e) => {
        const status = e?.status || 0;
        const isOverloaded = status === 503 || status === 502;
        if (isOverloaded && this.sugerenciaRetries < this.sugerenciaMaxRetries) {
          this.sugerenciaRetries++;
          this.progresoTexto = `IA temporalmente saturada. Reintentando automáticamente (${this.sugerenciaRetries}/${this.sugerenciaMaxRetries})...`;
          this.retryCountdown = 15;
          this.cdr.markForCheck();
          if (this.retryTimer) clearInterval(this.retryTimer);
          this.retryTimer = setInterval(() => {
            this.retryCountdown--;
            if (this.retryCountdown > 0) {
              this.progresoTexto = `Reintentando en ${this.retryCountdown}s (intento ${this.sugerenciaRetries}/${this.sugerenciaMaxRetries})...`;
              this.cdr.markForCheck();
            } else {
              clearInterval(this.retryTimer!);
              this.retryTimer = null;
              this.generarSugerencia();
            }
          }, 1000);
        } else {
          this.sugerenciaRetries = 0;
          this._fallo(e, 'La IA no pudo generar la propuesta. Intenta de nuevo.');
        }
      },
    });
  }

  refinar(): void {
    if (!this.solicitudId) return;
    const respuestas = this.respuestasPreguntas
      .map((r, i) => ({ r, i }))
      .filter(({ r }) => (r || '').trim())
      .map(({ r, i }) => ({ rol: 'usuario' as const, texto: `${this.preguntasIa[i]} → ${r.trim()}` }));
    if (!respuestas.length && !this.conversacion.length) {
      this.errorMessage = 'Responde al menos una pregunta para refinar.';
      return;
    }
    this.isLoading = true;
    this.errorMessage = '';
    const conversacion = [...this.conversacion, ...respuestas];
    this.apuService.refinarPropuesta(this.solicitudId, conversacion, this.propuesta, this.aiuConfig).subscribe({
      next: (res) => {
        this.conversacion = [
          ...this.conversacion,
          ...respuestas,
          { rol: 'ia', texto: res.propuesta?.notas || 'Propuesta actualizada.' },
        ];
        this._cargarPropuesta(res);
      },
      error: (e) => this._fallo(e, 'No se pudo refinar la propuesta.'),
    });
  }

  agregarFilaVacia(): void {
    this.filas.push({
      incluir: true,
      tipo_insumo: 'Materiales',
      descripcion: '',
      unidad: '',
      rendimiento: null,
      precio: null,
      fuente: '',
      fuente_link: '',
    });
  }

  eliminarFila(idx: number): void {
    this.filas.splice(idx, 1);
  }

  navegarFuente(link?: string, event?: Event): void {
    if (!link) return;
    if (link.startsWith('http')) {
      window.open(link, '_blank', 'noopener,noreferrer');
    } else {
      event?.preventDefault();
      this.router.navigateByUrl(link);
    }
  }

  aplicarEstructura(): void {
    if (!this.solicitudId) return;
    const insumos = this.filasIncluidas;
    if (!insumos.length) {
      this.errorMessage = 'Deja al menos un insumo con descripción marcado para incluir.';
      return;
    }
    const propuestaFinal = {
      ...(this.propuesta || {}),
      insumos: insumos.map(f => ({
        tipo_insumo: f.tipo_insumo,
        descripcion: f.descripcion.trim(),
        unidad: f.unidad,
        rendimiento: f.rendimiento,
        precio: f.precio,
        fuente: f.fuente,
        fuente_link: f.fuente_link || '',
      })),
    };
    this.isLoading = true;
    this.errorMessage = '';
    this.apuService.aplicarEstructura(this.solicitudId, propuestaFinal).subscribe({
      next: () => {
        this.successMessage = 'Estructura guardada. Registra los precios del contratista.';
        this.isLoading = false;
        this.cargarBorrador(() => { this.paso = 3; this.pasoMax = Math.max(this.pasoMax, 3); });
      },
      error: (e) => this._fallo(e, 'No se pudo guardar la estructura.'),
    });
  }

  cargarBorrador(cb?: () => void): void {
    if (!this.solicitudId) return;
    this.isLoading = true;
    this.apuService.getAnalisisApuDetail(this.solicitudId).subscribe({
      next: (res) => {
        const s = res?.data || res;
        this._aplicarDetalleSolicitud(s);
        this.isLoading = false;
        cb?.();
        this.cdr.markForCheck();
      },
      error: (e) => this._fallo(e, 'No se pudo cargar el borrador.'),
    });
  }

  continuarBorrador(id?: number): void {
    const sid = id ?? this.continuarId;
    if (!sid) return;
    this.continuarId = sid;
    this.solicitudId = sid;
    this.isLoading = true;
    this.apuService.getAnalisisApuDetail(sid).subscribe({
      next: (res) => {
        const s = res?.data || res;
        if (s.origen !== 'constructor') {
          this._fallo({ error: { detail: 'Esta solicitud no proviene del Constructor.' } }, '');
          return;
        }
        this.descripcionActividad = s.descripcion_actividad || '';
        this.ciudad = s.ciudad || '';
        this.codigoItem = s.codigo_item || '';
        this.unidadActividad = s.unidad_actividad || '';
        this.proyectoId = s.proyecto_id ?? this.proyectoId;
        this._aplicarDetalleSolicitud(s);
        if (s.estado === 'borrador' && !(s.insumos || []).length) {
          this.paso = 2;
          this.pasoMax = 2;
          this.generarSugerencia();
        } else if (s.estado === 'borrador') {
          this.paso = 3;
          this.pasoMax = 3;
          this.isLoading = false;
        } else if (['aprobado_legal', 'firmado_legal'].includes(s.estado)) {
          this.paso = 4;
          this.pasoMax = 4;
          this.isLoading = false;
        } else {
          this.router.navigate(['/analisis-apu']);
        }
        this.cdr.markForCheck();
      },
      error: (e) => this._fallo(e, 'No se encontró el borrador.'),
    });
  }

  onArchivoCotizacion(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file || !this.solicitudId) return;
    this.isLoading = true;
    this.errorMessage = '';
    this.apuService.cargarPreciosArchivo(this.solicitudId, file).subscribe({
      next: (res) => {
        for (const a of res.asignadas || []) {
          this.preciosContratista[a.insumo_id] = a.precio;
        }
        this.sinCoincidencia = res.sin_coincidencia || [];
        this.successMessage = res.mensaje || 'Cotización procesada.';
        this.isLoading = false;
        input.value = '';
        this.cdr.markForCheck();
      },
      error: (e) => this._fallo(e, 'No se pudo procesar la cotización.'),
    });
  }

  guardarPrecios(): void {
    if (!this.solicitudId) return;
    const precios = Object.entries(this.preciosContratista)
      .filter(([, v]) => v !== null && Number(v) > 0)
      .map(([k, v]) => ({ insumo_id: Number(k), precio: Number(v) }));
    if (!precios.length) {
      this.errorMessage = 'Registra al menos un precio mayor que cero.';
      return;
    }
    this.isLoading = true;
    this.errorMessage = '';
    this.apuService.registrarPrecios(this.solicitudId, precios).subscribe({
      next: (res) => {
        this.successMessage = `Precios guardados (${res.actualizados}).` +
          (res.errores?.length ? ` Errores: ${res.errores.join('; ')}` : '');
        this.isLoading = false;
        this.pasoMax = Math.max(this.pasoMax, 4);
        this.cdr.markForCheck();
      },
      error: (e) => this._fallo(e, 'No se pudieron guardar los precios.'),
    });
  }

  irAExpediente(): void {
    if (!this.insumosBorrador.length) return;
    if (this.conPrecio === 0) {
      this.errorMessage = 'Registra y guarda al menos un precio del contratista antes de continuar.';
      return;
    }
    this.paso = 4;
    this.pasoMax = 4;
  }

  enviarAnalisis(): void {
    if (!this.solicitudId) return;
    this.isLoading = true;
    this.errorMessage = '';
    this.apuService.enviarAAnalisis(this.solicitudId, this.omitirSinPrecio).subscribe({
      next: () => {
        this.successMessage = 'Análisis generado. Redirigiendo al flujo de aprobación…';
        setTimeout(() => this.router.navigate(['/analisis-apu']), 800);
      },
      error: (e) => this._fallo(e, 'No se pudo enviar a análisis.'),
    });
  }

  guardarJustificacion(): void {
    if (!this.solicitudId) return;
    this.apuService.actualizarJustificacionApu(this.solicitudId, {
      justificacion_tecnica: this.justificacionTecnica,
      localizacion_obra: this.localizacionObra,
      numero_acta_aprobacion: this.numeroActaAprobacion,
      fecha_aprobacion_entidad: this.fechaAprobacionEntidad,
    }).subscribe({
      next: () => {
        this.successMessage = 'Justificación técnica y datos de acta guardados.';
        this.cdr.markForCheck();
      },
      error: () => {
        this.errorMessage = 'Error al guardar datos de justificación.';
        this.cdr.markForCheck();
      },
    });
  }

  incorporarAPU(): void {
    if (!this.solicitudId) return;
    if (!this.puedeIncorporar) {
      this.errorMessage = 'La incorporación al banco solo está disponible después de la firma legal.';
      return;
    }
    this.incorporando = true;
    this.errorMessage = '';
    this.apuService.incorporarApuAProyecto(this.solicitudId, {
      proyecto_id: this.proyectoId,
      numero_acta: this.numeroActaAprobacion,
      fecha_aprobacion: this.fechaAprobacionEntidad,
      justificacion: this.justificacionTecnica,
    }).subscribe({
      next: (res) => {
        this.incorporando = false;
        this.estadoIncorporacion = 'incorporado';
        this.successMessage = res.mensaje || '¡APU incorporado exitosamente al proyecto y al banco!';
        this.cdr.markForCheck();
      },
      error: (e) => {
        this.incorporando = false;
        this.errorMessage = e?.error?.detail || 'No se pudo incorporar el APU.';
        this.cdr.markForCheck();
      },
    });
  }

  async descargarPdf(): Promise<void> {
    if (!this.solicitudId) return;
    this.descargandoPdf = true;
    try {
      await this.apuService.exportMemoriaPdf(this.solicitudId);
    } catch {
      this.errorMessage = 'Error al descargar la memoria técnica en PDF.';
    } finally {
      this.descargandoPdf = false;
      this.cdr.markForCheck();
    }
  }

  async descargarExcel(): Promise<void> {
    if (!this.solicitudId) return;
    this.descargandoExcel = true;
    try {
      await this.apuService.exportApuFormulado(this.solicitudId);
    } catch {
      this.errorMessage = 'Error al descargar el APU en Excel formulado.';
    } finally {
      this.descargandoExcel = false;
      this.cdr.markForCheck();
    }
  }

  private _esIndirectoOAiu(desc?: string, tipo?: string): boolean {
    const t = (tipo || '').trim().toLowerCase();
    if (t === 'indirectos' || t === 'indirecto') return true;
    const d = (desc || '').trim().toLowerCase();
    const terminos = [
      'administracion', 'administración', 'imprevisto', 'imprevistos',
      'utilidad', 'utilidades', 'aiu', 'a.i.u', 'a.i.u.'
    ];
    return terminos.some(term => d.includes(term));
  }

  private _inferirFuenteLink(fuente?: string, link?: string): string {
    if (link) return link;
    if (!fuente) return '';
    const f = fuente.toLowerCase();
    if (f.includes('cype')) return 'https://generadordeprecios.info/obra_nueva/Colombia.html';
    if (f.includes('banco') || f.includes('histórica') || f.includes('historica')) return '/banco-apus';
    if (f.includes('homecenter') || f.includes('sodimac')) return 'https://www.homecenter.com.co';
    if (f.includes('secop')) return 'https://community.secop.gov.co/Public/Tendering/ContractNoticeManagement/Index';
    return '';
  }

  private _aplicarDetalleSolicitud(s: any): void {
    this.insumosBorrador = (s.insumos || [])
      .filter((ins: any) => !this._esIndirectoOAiu(ins.insumo_descripcion, ins.tipo_insumo))
      .map((ins: any) => ({
        ...ins,
        fuente_link: this._inferirFuenteLink(ins.fuente_precio, ins.fuente_link),
      }));
    this.preciosContratista = {};
    for (const ins of this.insumosBorrador) {
      this.preciosContratista[ins.id] = ins.precio_unitario_apu != null ? Number(ins.precio_unitario_apu) : null;
    }
    this.estadoSolicitud = s.estado || 'borrador';
    this.estadoIncorporacion = s.estado_incorporacion || 'pendiente';
    this.justificacionTecnica = s.justificacion_tecnica || this.justificacionTecnica;
    this.localizacionObra = s.localizacion_obra || this.localizacionObra;
    this.numeroActaAprobacion = s.numero_acta_aprobacion || this.numeroActaAprobacion;
    this.fechaAprobacionEntidad = s.fecha_aprobacion_entidad || this.fechaAprobacionEntidad;
    if (s.proyecto_id) {
      this.proyectoId = s.proyecto_id;
      this.onProyectoChange();
    }
  }

  private _cargarPropuesta(res: any): void {
    this.detenerProgresoScraping();
    this.propuesta = res.propuesta || {};
    this.desgloseAiu = res.desglose_aiu || null;
    if (res.desglose_aiu?.porcentajes) {
      this.aiuConfig = {
        administracion: Number(res.desglose_aiu.porcentajes.administracion ?? this.aiuConfig.administracion),
        imprevistos: Number(res.desglose_aiu.porcentajes.imprevistos ?? this.aiuConfig.imprevistos),
        utilidad: Number(res.desglose_aiu.porcentajes.utilidad ?? this.aiuConfig.utilidad),
        iva_utilidad: Number(res.desglose_aiu.porcentajes.iva_utilidad ?? this.aiuConfig.iva_utilidad),
      };
    }
    this.referenciasUsadas = res.referencias_usadas || this.referenciasUsadas;
    this.filas = (this.propuesta.insumos || [])
      .filter((i: any) => !this._esIndirectoOAiu(i.descripcion, i.tipo_insumo))
      .map((i: any) => ({
        incluir: true,
        tipo_insumo: i.tipo_insumo || 'Materiales',
        descripcion: i.descripcion || '',
        unidad: i.unidad || '',
        rendimiento: i.rendimiento ?? null,
        precio: i.precio ?? null,
        fuente: i.fuente || '',
        fuente_link: this._inferirFuenteLink(i.fuente, i.fuente_link),
      }));
    this.respuestasPreguntas = new Array(this.preguntasIa.length).fill('');
    this.isLoading = false;
    this.errorMessage = '';
    this.paso = 2;
    this.pasoMax = Math.max(this.pasoMax, 2);
    this.cdr.markForCheck();
  }

  private _fallo(e: any, fallback: string): void {
    this.detenerProgresoScraping();
    this.errorMessage = e?.error?.detail || fallback;
    this.isLoading = false;
    this.cdr.markForCheck();
  }
}
