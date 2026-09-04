import { Component, ChangeDetectorRef, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { ApuService, FilterOptions } from '../../services/apu';

interface FilaPropuesta {
  incluir: boolean;
  tipo_insumo: string;
  descripcion: string;
  unidad: string;
  rendimiento: number | null;
  precio: number | null;
  fuente: string;
}

@Component({
  selector: 'app-constructor-apu',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './constructor-apu.html',
  styleUrl: './constructor-apu.scss',
})
export class ConstructorApu {
  private apuService = inject(ApuService);
  private cdr = inject(ChangeDetectorRef);
  private router = inject(Router);

  paso = 1;
  isLoading = false;
  errorMessage = '';
  successMessage = '';

  // Paso 1: actividad
  descripcionActividad = '';
  unidadActividad = '';
  codigoItem = '';
  ciudad = '';
  ciudades: string[] = [];
  continuarId: number | null = null;

  // Borrador activo
  solicitudId: number | null = null;
  proyectoId: number | null = null;
  proyectosDisponibles: any[] = [];

  // Paso 2: propuesta IA
  propuesta: any = null;
  desgloseAiu: any = null;
  filas: FilaPropuesta[] = [];
  referenciasUsadas: any[] = [];
  conversacion: { rol: 'ia' | 'usuario'; texto: string }[] = [];
  respuestasPreguntas: string[] = [];

  // Indicador dinámico de búsqueda en vivo / scraping
  progresoTexto = '';
  progresoPaso = 1;
  private progresoTimer: any = null;

  // Paso 3: precios y visto bueno de entidad
  insumosBorrador: any[] = [];
  preciosContratista: Record<number, number | null> = {};
  sinCoincidencia: any[] = [];

  // Memoria técnica y aprobación formal
  justificacionTecnica = '';
  localizacionObra = '';
  numeroActaAprobacion = '';
  fechaAprobacionEntidad = '';
  estadoIncorporacion = 'pendiente';
  incorporando = false;
  descargandoPdf = false;
  descargandoExcel = false;

  omitirSinPrecio = false;

  tiposInsumo = ['Materiales', 'Equipos', 'Mano de obra', 'Transporte', 'Herramienta', 'Indirectos', 'Otro'];

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
    return Object.values(this.preciosContratista).filter(v => v !== null && v > 0).length;
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
        this.generarSugerencia();
      },
      error: (e) => this._fallo(e, 'No se pudo crear el borrador.'),
    });
  }

  // Auto-retry state for IA overload
  private sugerenciaRetries = 0;
  private sugerenciaMaxRetries = 2;
  private retryTimer: any = null;
  retryCountdown = 0;

  generarSugerencia(): void {
    if (!this.solicitudId) return;
    this.isLoading = true;
    this.errorMessage = '';
    this.retryCountdown = 0;
    this.iniciarProgresoScraping();
    this.apuService.sugerirEstructura(this.solicitudId).subscribe({
      next: (res) => {
        this.sugerenciaRetries = 0;
        this._cargarPropuesta(res);
        // NO navegar automáticamente: el residente decide cuándo ir a análisis
        // this.paso = Math.max(this.paso, 2); // Removido: se maneja en _cargarPropuesta
      },
      error: (e) => {
        const status = e?.status || 0;
        const isOverloaded = status === 503 || status === 502;
        if (isOverloaded && this.sugerenciaRetries < this.sugerenciaMaxRetries) {
          this.sugerenciaRetries++;
          this.progresoTexto = `⏳ IA temporalmente saturada. Reintentando automáticamente (${this.sugerenciaRetries}/${this.sugerenciaMaxRetries})...`;
          this.retryCountdown = 15;
          this.cdr.markForCheck();
          if (this.retryTimer) clearInterval(this.retryTimer);
          this.retryTimer = setInterval(() => {
            this.retryCountdown--;
            if (this.retryCountdown > 0) {
              this.progresoTexto = `⏳ Reintentando en ${this.retryCountdown}s (intento ${this.sugerenciaRetries}/${this.sugerenciaMaxRetries})...`;
              this.cdr.markForCheck();
            } else {
              clearInterval(this.retryTimer);
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
    this.apuService.refinarPropuesta(this.solicitudId, conversacion).subscribe({
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
    this.filas.push({ incluir: true, tipo_insumo: 'Materiales', descripcion: '', unidad: '', rendimiento: null, precio: null, fuente: '' });
  }

  eliminarFila(idx: number): void {
    this.filas.splice(idx, 1);
  }

  aplicarEstructura(): void {
    if (!this.solicitudId) return;
    const insumos = this.filas.filter(f => f.incluir && f.descripcion.trim());
    if (!insumos.length) {
      this.errorMessage = 'Deja al menos un insumo con descripción marcado para incluir.';
      return;
    }
    const propuestaFinal = {
      ...(this.propuesta || {}),
      insumos: insumos.map(f => ({
        tipo_insumo: f.tipo_insumo, descripcion: f.descripcion.trim(), unidad: f.unidad,
        rendimiento: f.rendimiento, precio: f.precio, fuente: f.fuente,
      })),
    };
    this.isLoading = true;
    this.errorMessage = '';
    this.apuService.aplicarEstructura(this.solicitudId, propuestaFinal).subscribe({
      next: () => {
        this.successMessage = 'Estructura guardada. Registra los precios del contratista.';
        this.isLoading = false;
        this.cargarBorrador(() => { this.paso = 3; });
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
        this.insumosBorrador = s.insumos || [];
        this.preciosContratista = {};
        for (const ins of this.insumosBorrador) {
          this.preciosContratista[ins.id] = ins.precio_unitario_apu != null ? Number(ins.precio_unitario_apu) : null;
        }
        this.isLoading = false;
        cb?.();
        this.cdr.markForCheck();
      },
      error: (e) => this._fallo(e, 'No se pudo cargar el borrador.'),
    });
  }

  continuarBorrador(): void {
    if (!this.continuarId) return;
    this.solicitudId = this.continuarId;
    this.isLoading = true;
    this.apuService.getAnalisisApuDetail(this.continuarId).subscribe({
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
        if (s.estado === 'borrador' && !(s.insumos || []).length) {
          this.paso = 2;
          this.generarSugerencia();
        } else if (s.estado === 'borrador') {
          this.insumosBorrador = s.insumos || [];
          this.preciosContratista = {};
          for (const ins of this.insumosBorrador) {
            this.preciosContratista[ins.id] = ins.precio_unitario_apu != null ? Number(ins.precio_unitario_apu) : null;
          }
          this.paso = 3;
          this.isLoading = false;
        } else {
          // Ya salió del constructor: va directo a su detalle en Análisis APU.
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
      .filter(([, v]) => v !== null && v > 0)
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
        this.cdr.markForCheck();
      },
      error: (e) => this._fallo(e, 'No se pudieron guardar los precios.'),
    });
  }

  enviarAnalisis(): void {
    if (!this.solicitudId) return;
    this.isLoading = true;
    this.errorMessage = '';
    this.apuService.enviarAAnalisis(this.solicitudId, this.omitirSinPrecio).subscribe({
      next: () => {
        this.successMessage = 'Análisis generado. Redirigiendo…';
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
    } catch (e) {
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
    } catch (e) {
      this.errorMessage = 'Error al descargar el APU en Excel formulado.';
    } finally {
      this.descargandoExcel = false;
      this.cdr.markForCheck();
    }
  }

  private _cargarPropuesta(res: any): void {
    this.detenerProgresoScraping();
    this.propuesta = res.propuesta || {};
    this.desgloseAiu = res.desglose_aiu || null;
    this.referenciasUsadas = res.referencias_usadas || [];
    this.filas = (this.propuesta.insumos || []).map((i: any) => ({
      incluir: true,
      tipo_insumo: i.tipo_insumo || 'Materiales',
      descripcion: i.descripcion || '',
      unidad: i.unidad || '',
      rendimiento: i.rendimiento ?? null,
      precio: i.precio ?? null,
      fuente: i.fuente || '',
    }));
    this.respuestasPreguntas = new Array(this.preguntasIa.length).fill('');
    this.isLoading = false;
    this.errorMessage = '';
    this.paso = 2;
    this.cdr.markForCheck();
  }

  private _fallo(e: any, fallback: string): void {
    this.detenerProgresoScraping();
    this.errorMessage = e?.error?.detail || fallback;
    this.isLoading = false;
    this.cdr.markForCheck();
  }
}
