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

export interface AnalisisItem {
  item: string;
  descripcion: string;
  unidad: string;
  precio_ofertado: number;
  mejor_precio_banco?: number;
  diferencia_precio?: number;
  existe_en_banco: boolean;
  item_banco_encontrado?: string;
  estructura_insumos_coincide?: boolean;
  rendimiento_coincide?: boolean;
  observaciones?: string;
  recomendacion: string;
  grupo_cotizacion?: number;
}

export interface AnalisisApu {
  id?: number;
  solicitud_id: number;
  analisis_json?: string;
  resumen?: string;
  recomendacion?: string;
  items_analizados?: AnalisisItem[];
  created_at?: string;
}

export interface SolicitudApu {
  id?: number;
  link_documento?: string;
  contratista?: string;
  nombre_proyecto?: string;
  fecha_solicitud?: string;
  fecha_limite_respuesta?: string;
  fecha_limite_aprobacion?: string;
  estado: string;
  insumos?: SolicitudInsumo[];
  grupos_archivos?: GrupoArchivo[];
  historial?: HistorialAprobacion[];
  analisis?: AnalisisApu;
  created_at?: string;
  updated_at?: string;
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

  rechazoMotivo = '';
  showRechazoForm = false;
  exportando = false;

  auth = inject(AuthService);

  ngOnInit(): void {
    this.loadSolicitudes();
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

    this.apuService.uploadCotizaciones(this.selectedFiles).subscribe({
      next: (res: any) => {
        this.ngZone.run(() => {
          this.selectedFiles = [];
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

  getGrupoNombre(grupo: number): string {
    const grupos = this.selectedSolicitud?.grupos_archivos || [];
    const found = grupos.find((g: any) => g.grupo_cotizacion === grupo);
    return found ? found.nombre_archivo : `Cotización ${grupo}`;
  }

  trackById(index: number, item: any): number {
    return item.id || index;
  }
}
