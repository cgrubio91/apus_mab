import { Component, OnInit, ChangeDetectorRef, NgZone, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Observable } from 'rxjs';
import { ApuService } from '../../services/apu';
import { AuthService } from '../../services/auth.service';

export interface SolicitudInsumo {
  id?: number;
  solicitud_id?: number;
  grupo_cotizacion?: number;
  nombre_archivo?: string;
  item?: string;
  items_descripcion?: string;
  item_unidad?: string;
  precio_unitario?: number;
  codigo_insumo?: string;
  insumo_descripcion?: string;
  insumo_unidad?: string;
  rendimiento_insumo?: number;
  precio_unitario_apu?: number | null;
  precio_parcial_apu?: number | null;
  tipo_insumo?: string;
}

export interface GrupoArchivo {
  grupo_cotizacion: number;
  nombre_archivo: string;
}

export interface HistorialAprobacion {
  id?: number;
  solicitud_id?: number;
  accion: string;
  responsable_rol: string;
  responsable_nombre: string;
  motivo?: string;
  created_at?: string;
}

export interface InsumoCotizado {
  tipo_insumo?: string;
  codigo_insumo?: string;
  insumo_descripcion?: string;
  insumo_unidad?: string;
  rendimiento_insumo?: number | null;
  precio_unitario_apu?: number | null;
  precio_parcial_apu?: number | null;
  equivalente?: boolean;
}

export interface InsumoBanco extends InsumoCotizado {
  precio_unitario_apu?: number | null;
  precio_parcial_apu?: number | null;
}

export interface CandidatoBanco {
  nombre_proyecto?: string;
  entidad?: string;
  ciudad?: string;
  contratista?: string;
  numero_contrato?: string;
  item?: string;
  items_descripcion?: string;
  item_unidad?: string;
  precio_unitario?: number;
  precio_unitario_sin_aiu?: number;
  fecha?: string;
  similitud?: number;
  diferencia_precio?: number | null;
  diferencia_pct?: number | null;
  es_match_ia?: boolean;
  es_referencia?: boolean;
  insumos?: InsumoBanco[];
}

export interface AnalisisItem {
  item: string;
  descripcion: string;
  unidad: string;
  precio_ofertado: number;
  mejor_precio_banco?: number;
  diferencia_precio?: number;
  diferencia_pct?: number;
  existe_en_banco: boolean;
  item_banco_encontrado?: string;
  estructura_insumos_coincide?: boolean;
  rendimiento_coincide?: boolean;
  observaciones?: string;
  recomendacion: string;
  grupo_cotizacion?: number;
  nombre_archivo?: string;
  insumos_cotizados?: InsumoCotizado[];
  candidatos?: CandidatoBanco[];
}

export interface ProveedorPrecio {
  grupo: number;
  proveedor: string;
  precio: number;
  rendimiento?: number | null;
  precio_parcial?: number | null;
  es_menor?: boolean;
}

export interface BancoRefInsumo {
  insumo_descripcion?: string;
  insumo_unidad?: string;
  tipo_insumo?: string;
  rendimiento_insumo?: number | null;
  precio_unitario_apu?: number;
  precio_parcial_apu?: number | null;
  nombre_proyecto?: string;
  entidad?: string;
  ciudad?: string;
  contratista?: string;
  fecha?: string;
  similitud?: number;
  diferencia?: number | null;
  diferencia_pct?: number | null;
}

export interface SugerenciaInsumo {
  insumo_descripcion?: string;
  insumo_unidad?: string;
  tipo_insumo?: string;
  codigo_insumo?: string;
  precio_unitario_apu?: number | null;
}

export interface InsumoComparado {
  descripcion: string;
  unidad?: string;
  codigo?: string;
  tipo_insumo?: string;
  sugerencia?: SugerenciaInsumo;
  descripciones_originales?: string[];
  proveedores: ProveedorPrecio[];
  mejor_precio?: number | null;
  mejor_proveedor?: string | null;
  mejor_precio_banco?: number | null;
  existe_en_banco?: boolean;
  banco_referencia?: BancoRefInsumo[];
}

export interface AnalisisApu {
  id?: number;
  solicitud_id: number;
  analisis_json?: string;
  resumen?: string;
  recomendacion?: string;
  modo?: string;
  items_analizados?: AnalisisItem[];
  insumos_comparados?: InsumoComparado[];
  created_at?: string;
}

export interface SolicitudApu {
  id?: number;
  link_documento?: string;
  contratista?: string;
  nombre_proyecto?: string;
  proyecto_id?: number | null;
  fecha_solicitud?: string;
  fecha_limite_respuesta?: string;
  fecha_limite_aprobacion?: string;
  estado: string;
  tipo_comparacion?: string;
  insumos?: SolicitudInsumo[];
  grupos_archivos?: GrupoArchivo[];
  historial?: HistorialAprobacion[];
  analisis?: AnalisisApu;
  created_at?: string;
  updated_at?: string;
}

export interface ProyectoMapus {
  id: number;
  id_proy: number;
  descripcion: string;
}

@Component({
  selector: 'app-analisis-apu',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './analisis-apu.html',
  styleUrl: './analisis-apu.scss',
})
export class AnalisisApu implements OnInit {
  solicitudes: SolicitudApu[] = [];
  selectedSolicitud: SolicitudApu | null = null;
  loading = false;
  error: string | null = null;
  successMsg: string | null = null;
  showUploadForm = false;
  filterEstado = '';

  selectedFiles: File[] = [];
  uploading = false;
  uploadProgress = '';
  uploadProyectoId: number | null = null;

  rechazoMotivo = '';
  showRechazoForm = false;
  exportando = false;

  proyectos: ProyectoMapus[] = [];
  proyectoSeleccionId: number | null = null;
  guardandoProyecto = false;

  auth = inject(AuthService);

  ngOnInit(): void {
    this.loadSolicitudes();
    this.loadProyectos();
  }

  constructor(
    private apuService: ApuService,
    private cdr: ChangeDetectorRef,
    private ngZone: NgZone,
  ) {}

  loadSolicitudes(): void {
    this.loading = true;
    this.error = null;
    this.apuService.getAnalisisApuList(this.filterEstado || undefined).subscribe({
      next: (res: any) => {
        this.ngZone.run(() => {
          this.solicitudes = res.data || [];
          this.loading = false;
          this.cdr.detectChanges();
        });
      },
      error: (err) => {
        this.ngZone.run(() => {
          this.error = 'Error cargando solicitudes';
          this.loading = false;
          this.cdr.detectChanges();
        });
      },
    });
  }

  loadProyectos(): void {
    this.apuService.getProyectosMapus().subscribe({
      next: (res: any) => {
        this.ngZone.run(() => {
          this.proyectos = res.proyectos || [];
          this.cdr.detectChanges();
        });
      },
      error: () => {},
    });
  }

  viewSolicitud(s: SolicitudApu): void {
    this._loadSolicitudDetail(s.id!);
  }

  private _loadSolicitudDetail(id: number): void {
    this.loading = true;
    this.showRechazoForm = false;
    this.apuService.getAnalisisApuDetail(id).subscribe({
      next: (res: any) => {
        this.ngZone.run(() => {
          this.selectedSolicitud = res.data;
          this.proyectoSeleccionId = res.data?.proyecto_id ?? null;
          this.loading = false;
          this.cdr.detectChanges();
        });
      },
      error: (err) => {
        this.ngZone.run(() => {
          this.error = 'Error cargando detalle';
          this.loading = false;
          this.cdr.detectChanges();
        });
      },
    });
  }

  closeDetail(): void {
    this.selectedSolicitud = null;
    this.showRechazoForm = false;
    this.rechazoMotivo = '';
    this.loadSolicitudes();
  }

  onFilesSelected(event: any): void {
    const files: FileList = event.target.files;
    this.selectedFiles = [];
    let hasError = false;

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const ext = file.name.split('.').pop()?.toLowerCase();
      if (ext === 'pdf' || ext === 'xlsx' || ext === 'xls') {
        this.selectedFiles.push(file);
      } else {
        hasError = true;
      }
    }

    if (hasError) {
      this.error = 'Algunos archivos fueron ignorados (solo PDF y Excel).';
    }
  }

  removeFile(index: number): void {
    this.selectedFiles.splice(index, 1);
  }

  uploadCotizacion(): void {
    if (this.selectedFiles.length === 0) return;

    this.uploading = true;
    this.error = null;
    this.uploadProgress = `Subiendo ${this.selectedFiles.length} archivo(s)...`;

    this.apuService.uploadCotizaciones(this.selectedFiles, this.uploadProyectoId).subscribe({
      next: (res: any) => {
        this.ngZone.run(() => {
          this.selectedFiles = [];
          this.uploadProyectoId = null;
          this.showUploadForm = false;

          if (res.solicitud_id) {
            this.successMsg = `Solicitud #${res.solicitud_id} creada. Analizando con IA...`;

            this._loadSolicitudDetail(res.solicitud_id);

            this.apuService.analizarSolicitud(res.solicitud_id).subscribe({
              next: (analisisRes: any) => {
                this.ngZone.run(() => {
                  this.uploading = false;
                  this.successMsg = `Análisis completado para solicitud #${res.solicitud_id}`;
                  this._loadSolicitudDetail(res.solicitud_id);
                });
              },
              error: (errAnalisis: any) => {
                this.ngZone.run(() => {
                  this.uploading = false;
                  console.warn('Análisis automático falló:', errAnalisis);
                  this.error = `El análisis IA falló. Haz clic en "Ejecutar Análisis IA" para reintentar.`;
                  this._loadSolicitudDetail(res.solicitud_id);
                });
              },
            });
          } else {
            this.uploading = false;
            this.loadSolicitudes();
          }

          this.cdr.detectChanges();
        });
      },
      error: (err) => {
        this.ngZone.run(() => {
          this.uploading = false;
          this.error = err.error?.detail || 'Error al subir cotización';
          this.cdr.detectChanges();
        });
      },
    });
  }

  /**
   * Ejecuta una acción del flujo de aprobación con el manejo común de
   * loading, mensajes, recarga del detalle y detección de cambios.
   */
  private runWorkflowAction(
    id: number,
    action: () => Observable<any>,
    errorFallback: string,
    opts: { reloadList?: boolean; successMsg?: string; onSuccess?: () => void } = {},
  ): void {
    const { reloadList = true, successMsg, onSuccess } = opts;
    this.loading = true;
    action().subscribe({
      next: (res: any) => {
        this.ngZone.run(() => {
          this.successMsg = successMsg || res.mensaje;
          this.loading = false;
          onSuccess?.();
          this._loadSolicitudDetail(id);
          if (reloadList) this.loadSolicitudes();
        });
      },
      error: (err) => {
        this.ngZone.run(() => {
          this.error = err.error?.detail || errorFallback;
          this.loading = false;
          this.cdr.detectChanges();
        });
      },
    });
  }

  guardarProyecto(id: number): void {
    if (!this.proyectoSeleccionId) {
      this.error = 'Selecciona un proyecto';
      return;
    }
    this.guardandoProyecto = true;
    this.apuService.seleccionarProyectoSolicitud(id, this.proyectoSeleccionId).subscribe({
      next: (res: any) => {
        this.ngZone.run(() => {
          this.guardandoProyecto = false;
          this.successMsg = res.mensaje;
          this._loadSolicitudDetail(id);
        });
      },
      error: (err) => {
        this.ngZone.run(() => {
          this.guardandoProyecto = false;
          this.error = err.error?.detail || 'Error al asignar el proyecto';
          this.cdr.detectChanges();
        });
      },
    });
  }

  analizarManual(id: number): void {
    this.runWorkflowAction(id, () => this.apuService.analizarSolicitud(id), 'Error en análisis', {
      reloadList: false,
      successMsg: 'Análisis completado',
    });
  }

  preaprobar(id: number): void {
    this.runWorkflowAction(id, () => this.apuService.preaprobarApu(id), 'Error en preaprobación');
  }

  rechazar(id: number): void {
    if (!this.rechazoMotivo) {
      this.error = 'Complete el motivo del rechazo';
      return;
    }
    this.runWorkflowAction(id, () => this.apuService.rechazarApu(id, this.rechazoMotivo), 'Error al rechazar', {
      onSuccess: () => {
        this.showRechazoForm = false;
        this.rechazoMotivo = '';
      },
    });
  }

  nuevasCotizaciones(id: number): void {
    this.runWorkflowAction(id, () => this.apuService.nuevasCotizaciones(id), 'Error al registrar');
  }

  aprobarSubgerente(id: number): void {
    this.runWorkflowAction(id, () => this.apuService.aprobarSubgerente(id), 'Error en aprobación');
  }

  firmarLegal(id: number): void {
    this.runWorkflowAction(id, () => this.apuService.firmarLegal(id), 'Error en firma legal');
  }

  async exportarAnalisis(id: number): Promise<void> {
    this.exportando = true;
    this.error = null;
    try {
      await this.apuService.exportAnalisis(id);
    } catch {
      this.error = 'No se pudo exportar el análisis.';
    } finally {
      this.exportando = false;
      this.cdr.detectChanges();
    }
  }

  estadoBadgeClass(estado: string): string {
    const map: Record<string, string> = {
      pendiente_analisis: 'badge-warning',
      analizado: 'badge-info',
      preaprobado: 'badge-primary',
      rechazado: 'badge-danger',
      nuevas_cotizaciones: 'badge-warning',
      aprobado_subgerente: 'badge-success',
      aprobado_legal: 'badge-success',
    };
    return map[estado] || 'badge-secondary';
  }

  estadoLabel(estado: string): string {
    const map: Record<string, string> = {
      pendiente_analisis: 'Pendiente Análisis',
      analizado: 'Analizado',
      preaprobado: 'Preaprobado',
      rechazado: 'Rechazado',
      nuevas_cotizaciones: 'Nuevas Cotizaciones',
      aprobado_subgerente: 'Aprobado Subgerente',
      aprobado_legal: 'Aprobado Legal',
    };
    return map[estado] || estado;
  }

  recomendacionClass(rec: string): string {
    const map: Record<string, string> = {
      aprobar: 'rec-aprobar',
      rechazar: 'rec-rechazar',
      revisar: 'rec-revisar',
    };
    return map[rec] || 'rec-pendiente';
  }

  getStats(items: any[]): any {
    if (!items?.length) return { total: 0, aprobar: 0, rechazar: 0, revisar: 0, conBanco: 0, sinBanco: 0 };
    return {
      total: items.length,
      aprobar: items.filter((i: any) => i.recomendacion === 'aprobar').length,
      rechazar: items.filter((i: any) => i.recomendacion === 'rechazar').length,
      revisar: items.filter((i: any) => i.recomendacion === 'revisar' || i.recomendacion === 'pendiente').length,
      conBanco: items.filter((i: any) => i.existe_en_banco).length,
      sinBanco: items.filter((i: any) => !i.existe_en_banco).length,
    };
  }

  getGroupedItems(items: any[]): any[] {
    if (!items?.length) return [];
    const groups: any = {};
    items.forEach((item: any) => {
      const g = item.grupo_cotizacion || 1;
      if (!groups[g]) groups[g] = [];
      groups[g].push(item);
    });
    return Object.keys(groups).map(k => ({ grupo: Number(k), items: groups[k] }));
  }

  cambiandoModo = false;

  get modoActual(): string {
    return this.selectedSolicitud?.tipo_comparacion
      || this.selectedSolicitud?.analisis?.modo
      || 'apu';
  }

  modoLabel(tipo?: string): string {
    return (tipo || this.modoActual) === 'insumos' ? 'Solo insumos (proveedores)' : 'APU completo';
  }

  cambiarModo(id: number, tipo: 'apu' | 'insumos'): void {
    if (this.modoActual === tipo || this.cambiandoModo) return;
    this.cambiandoModo = true;
    this.error = null;
    this.apuService.setTipoComparacion(id, tipo).subscribe({
      next: () => {
        // Cambiar el modo obliga a re-analizar para regenerar la comparación correcta.
        this.apuService.analizarSolicitud(id).subscribe({
          next: () => this.ngZone.run(() => {
            this.cambiandoModo = false;
            this.successMsg = `Modo cambiado a "${this.modoLabel(tipo)}" y re-analizado.`;
            this._loadSolicitudDetail(id);
          }),
          error: () => this.ngZone.run(() => {
            this.cambiandoModo = false;
            this._loadSolicitudDetail(id);
          }),
        });
      },
      error: (err) => this.ngZone.run(() => {
        this.cambiandoModo = false;
        this.error = err.error?.detail || 'No se pudo cambiar el modo';
        this.cdr.detectChanges();
      }),
    });
  }

  showApuCotizado = true;

  // Explicación de "Vr. Unit. APU" / "Vr. Parcial APU"
  showInfoApu = false;

  toggleInfoApu(): void {
    this.showInfoApu = !this.showInfoApu;
  }

  // ── Subir insumo al banco (modo insumos) ──────────────────────────
  tipoInsumoOpciones = ['Materiales', 'Equipos', 'Mano de obra', 'Transporte', 'Herramienta', 'Indirectos', 'Otro'];
  subiendoIdx: number | null = null;
  subirDatos: SugerenciaInsumo = {};
  subirGuardando = false;
  subidos = new Set<number>();

  abrirSubir(idx: number, ins: InsumoComparado): void {
    this.subiendoIdx = idx;
    const s = ins.sugerencia || {};
    this.subirDatos = {
      insumo_descripcion: s.insumo_descripcion ?? ins.descripcion ?? '',
      insumo_unidad: s.insumo_unidad ?? ins.unidad ?? '',
      tipo_insumo: s.tipo_insumo ?? ins.tipo_insumo ?? '',
      codigo_insumo: s.codigo_insumo ?? ins.codigo ?? '',
      precio_unitario_apu: s.precio_unitario_apu ?? ins.mejor_precio ?? null,
    };
  }

  cancelarSubir(): void {
    this.subiendoIdx = null;
    this.subirDatos = {};
  }

  confirmarSubir(idx: number): void {
    if (!this.subirDatos.insumo_descripcion?.trim()) {
      this.error = 'La descripción del insumo es obligatoria';
      return;
    }
    this.subirGuardando = true;
    this.error = null;
    this.apuService.subirInsumoBanco(this.subirDatos).subscribe({
      next: (res: any) => this.ngZone.run(() => {
        this.subirGuardando = false;
        this.successMsg = res.mensaje;
        this.subidos.add(idx);
        this.subiendoIdx = null;
        this.cdr.detectChanges();
      }),
      error: (err: any) => this.ngZone.run(() => {
        this.subirGuardando = false;
        this.error = err.error?.detail || 'No se pudo subir el insumo al banco';
        this.cdr.detectChanges();
      }),
    });
  }

  expandedKeys = new Set<string>();

  toggleItem(grupo: number, idx: number): void {
    const key = `${grupo}:${idx}`;
    if (this.expandedKeys.has(key)) {
      this.expandedKeys.delete(key);
    } else {
      this.expandedKeys.add(key);
    }
  }

  isExpanded(grupo: number, idx: number): boolean {
    return this.expandedKeys.has(`${grupo}:${idx}`);
  }

  getGrupoNombre(grupo: number): string {
    const grupos = this.selectedSolicitud?.grupos_archivos || [];
    const found = grupos.find((g: any) => g.grupo_cotizacion === grupo);
    return found ? found.nombre_archivo : `Cotización ${grupo}`;
  }

  trackById(index: number, item: any): number {
    return item.id || index;
  }
}
