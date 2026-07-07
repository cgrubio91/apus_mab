import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, Subject } from 'rxjs';
import { environment } from '../../environments/environment';
import { authHeaders, getStoredToken, USER_KEY } from './auth.storage';

export interface ApuRecord {
  id?: number;
  fecha_aprobacion_apu?: string;
  fecha_analisis_apu?: string;
  ciudad: string;
  pais?: string;
  entidad?: string;
  contratista?: string;
  nombre_proyecto: string;
  numero_contrato?: string;
  item: string;
  items_descripcion: string;
  item_unidad?: string;
  precio_unitario?: number;
  precio_unitario_sin_aiu?: number;
  codigo_insumo?: string;
  tipo_insumo?: string;
  insumo_descripcion?: string;
  insumo_unidad?: string;
  rendimiento_insumo?: number;
  precio_unitario_apu?: number;
  precio_parcial_apu?: number;
  observacion?: string;
  link_documento?: string;
}

export interface ApuFilters {
  nombre_proyecto?: string;
  ciudad?: string;
  items_descripcion?: string;
  insumo_descripcion?: string;
  tipo_insumo?: string;
  contratista?: string;
  entidad?: string;
  codigo_insumo?: string;
  item?: string;
  item_unidad?: string;
  insumo_unidad?: string;
  pais?: string;
  numero_contrato?: string;
  search?: string;
  sort_by?: string;
  sort_order?: string;
  limit?: number;
  offset?: number;
}

export interface FilterOptions {
  proyectos: string[];
  ciudades: string[];
  tipos_insumo: string[];
  entidades: string[];
  contratistas: string[];
}

export interface Job {
  id: string;
  filename: string;
  status: 'QUEUED' | 'EXTRACTING' | 'POST_PROCESSING' | 'DONE' | 'ERROR';
  progress: {
    current_batch: number;
    total_batches: number;
    phase: string;
    percent: number;
  };
  result?: {
    success: boolean;
    filename: string;
    count: number;
    insumos: ApuRecord[];
    copy_paste_table: string;
  };
  error?: string;
  created_at: number;
  updated_at: number;
}


export interface Notificacion {
  id: number;
  rol_destino: string;
  titulo: string;
  mensaje: string;
  tipo: string;
  solicitud_id?: number;
  created_at: string;
  leida: boolean;
}

export interface HistoricoPunto {
  periodo: string;
  precio_promedio: number;
  precio_minimo: number;
  precio_maximo: number;
  registros: number;
}

export interface HistoricoPreciosResponse {
  success: boolean;
  insumo: string;
  data: HistoricoPunto[];
}

export interface UsuarioAdmin {
  id: number;
  telefono: string;
  nombre: string;
  rol: string;
  activo: boolean;
  fecha_registro?: string;
}

@Injectable({
  providedIn: 'root',
})
export class ApuService {
  private baseUrl = environment.apiUrl;

  constructor(private http: HttpClient) {}

  getProjects(): Observable<any> {
    return this.http.get(`${this.baseUrl}/projects`);
  }

  getDashboard(): Observable<any> {
    return this.http.get(`${this.baseUrl}/dashboard`);
  }

  getApus(filters: ApuFilters = {}): Observable<any> {
    const params: any = {};
    Object.keys(filters).forEach((key) => {
      const val = filters[key as keyof ApuFilters];
      if (val !== undefined && val !== null && val !== '') {
        params[key] = String(val);
      }
    });
    return this.http.get(`${this.baseUrl}/apus`, { params });
  }

  getFilterOptions(): Observable<FilterOptions> {
    return this.http.get<FilterOptions>(`${this.baseUrl}/apus/filter-options`);
  }

  extractFile(file: File): Observable<{success: boolean, job_id: string, message: string}> {
    const formData = new FormData();
    formData.append('file', file);
    return this.http.post<{success: boolean, job_id: string, message: string}>(`${this.baseUrl}/extract-file`, formData);
  }

  getJob(jobId: string): Observable<Job> {
    return this.http.get<Job>(`${this.baseUrl}/jobs/${jobId}`);
  }

  streamJobProgress(jobId: string): Observable<Job> {
    return new Observable<Job>(observer => {
      let stopped = false;

      const poll = async () => {
        while (!stopped) {
          try {
            const response = await fetch(`${this.baseUrl}/jobs/${jobId}`, { headers: authHeaders() });
            if (!response.ok) {
              console.error('Job poll failed:', response.status);
              await new Promise(r => setTimeout(r, 2000));
              continue;
            }
            const job: Job = await response.json();
            if (!stopped) {
              observer.next(job);
            }

            if (job.status === 'DONE' || job.status === 'ERROR') {
              observer.complete();
              stopped = true;
              return;
            }
          } catch (e) {
            console.error('Job poll error:', e);
          }
          await new Promise(r => setTimeout(r, 2000));
        }
      };

      poll();

      return () => {
        stopped = true;
      };
    });
  }


  getJobEventStream(jobId: string): EventSource {
    // EventSource no permite headers: el backend acepta el token por query param.
    const token = getStoredToken();
    const qs = token ? `?token=${encodeURIComponent(token)}` : '';
    return new EventSource(`${this.baseUrl}/jobs/${jobId}/stream${qs}`);
  }

  getJobs(): Observable<{ jobs: Job[] }> {
    return this.http.get<{ jobs: Job[] }>(`${this.baseUrl}/jobs`);
  }

  saveProgress = new Subject<any>();

  saveExtractedStreaming(data: ApuRecord[]): Promise<{ inserted: number; total: number; errors: string[] }> {
    return new Promise((resolve, reject) => {
      fetch(`${this.baseUrl}/save-extracted`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify(data),
      }).then(async (response) => {
        if (!response.ok) {
          reject(new Error('Error al guardar'));
          return;
        }
        const reader = response.body!.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (!line.trim()) continue;
            try {
              const update = JSON.parse(line);
              this.saveProgress.next(update);
            } catch { /* ignore partial lines */ }
          }
        }

        this.saveProgress.complete();
        resolve({ inserted: 0, total: 0, errors: [] });
      }).catch(reject);
    });
  }

  chatAssistant(message: string): Observable<any> {
    // Se envía el usuario autenticado real para que el historial multi-turno
    // sea por usuario y no compartido entre todos los clientes web.
    let telefono = 'web-user';
    let nombre = 'Usuario Web';
    try {
      const raw = localStorage.getItem(USER_KEY);
      if (raw) {
        const user = JSON.parse(raw);
        telefono = user.telefono || telefono;
        nombre = user.nombre || nombre;
      }
    } catch { /* usuario no disponible: usa valores por defecto */ }
    return this.http.post(`${this.baseUrl}/chat-assistant`, { message, telefono, nombre });
  }

  uploadCotizaciones(files: File[]): Observable<any> {
    const formData = new FormData();
    files.forEach(f => formData.append('files', f));
    return this.http.post(`${this.baseUrl}/analisis-apu/upload`, formData);
  }

  analizarSolicitud(solicitudId: number): Observable<any> {
    return this.http.post(`${this.baseUrl}/analisis-apu/${solicitudId}/analizar`, {});
  }

  getAnalisisApuList(estado?: string): Observable<any> {
    const params: any = {};
    if (estado) params.estado = estado;
    return this.http.get(`${this.baseUrl}/analisis-apu`, { params });
  }

  getAnalisisApuDetail(solicitudId: number): Observable<any> {
    return this.http.get(`${this.baseUrl}/analisis-apu/${solicitudId}`);
  }

  preaprobarApu(solicitudId: number): Observable<any> {
    return this.http.post(`${this.baseUrl}/analisis-apu/${solicitudId}/preaprobar`, {});
  }

  rechazarApu(solicitudId: number, motivo: string): Observable<any> {
    return this.http.post(`${this.baseUrl}/analisis-apu/${solicitudId}/rechazar`, { motivo });
  }

  nuevasCotizaciones(solicitudId: number): Observable<any> {
    return this.http.post(`${this.baseUrl}/analisis-apu/${solicitudId}/nuevas-cotizaciones`, {});
  }

  aprobarSubgerente(solicitudId: number): Observable<any> {
    return this.http.post(`${this.baseUrl}/analisis-apu/${solicitudId}/aprobar-subgerente`, {});
  }

  firmarLegal(solicitudId: number): Observable<any> {
    return this.http.post(`${this.baseUrl}/analisis-apu/${solicitudId}/firmar-legal`, {});
  }

  // ── Notificaciones ──────────────────────────────────────────────
  getNotificaciones(): Observable<{ success: boolean; notificaciones: Notificacion[]; no_leidas: number }> {
    return this.http.get<{ success: boolean; notificaciones: Notificacion[]; no_leidas: number }>(
      `${this.baseUrl}/notificaciones`,
    );
  }

  marcarNotificacionLeida(id: number): Observable<any> {
    return this.http.post(`${this.baseUrl}/notificaciones/${id}/leer`, {});
  }

  marcarTodasLeidas(): Observable<any> {
    return this.http.post(`${this.baseUrl}/notificaciones/leer-todas`, {});
  }

  // ── Exportación ─────────────────────────────────────────────────
  /** Descarga el banco de APUs (con los filtros dados) como archivo xlsx o csv. */
  async exportApus(filters: ApuFilters, formato: 'xlsx' | 'csv'): Promise<void> {
    const params = new URLSearchParams({ formato });
    for (const [key, val] of Object.entries(filters)) {
      if (val !== undefined && val !== null && val !== '' && key !== 'limit' && key !== 'offset') {
        params.set(key, String(val));
      }
    }
    await this.downloadFile(`${this.baseUrl}/apus/export?${params}`, `banco_apus.${formato}`);
  }

  /** Descarga el análisis comparativo de una solicitud como xlsx. */
  async exportAnalisis(solicitudId: number): Promise<void> {
    await this.downloadFile(
      `${this.baseUrl}/analisis-apu/${solicitudId}/export`,
      `analisis_solicitud_${solicitudId}.xlsx`,
    );
  }

  private async downloadFile(url: string, fallbackName: string): Promise<void> {
    const response = await fetch(url, { headers: authHeaders() });
    if (!response.ok) {
      throw new Error(`Error ${response.status} al exportar`);
    }
    const disposition = response.headers.get('Content-Disposition') || '';
    const match = disposition.match(/filename="?([^";]+)"?/);
    const filename = match ? match[1] : fallbackName;
    const blob = await response.blob();
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.click();
    URL.revokeObjectURL(link.href);
  }

  // ── Histórico de precios ────────────────────────────────────────
  getHistoricoPrecios(insumo: string, ciudad?: string, proyecto?: string): Observable<HistoricoPreciosResponse> {
    const params: any = { insumo };
    if (ciudad) params.ciudad = ciudad;
    if (proyecto) params.nombre_proyecto = proyecto;
    return this.http.get<HistoricoPreciosResponse>(`${this.baseUrl}/apus/historico-precios`, { params });
  }

  // ── Gestión de usuarios (admin) ─────────────────────────────────
  getUsers(): Observable<{ users: UsuarioAdmin[] }> {
    return this.http.get<{ users: UsuarioAdmin[] }>(`${this.baseUrl}/auth/users`);
  }

  createUser(user: { telefono: string; nombre: string; password: string; rol: string }): Observable<any> {
    return this.http.post(`${this.baseUrl}/auth/users`, user);
  }

  updateUser(id: number, cambios: { rol?: string; activo?: boolean }): Observable<any> {
    return this.http.patch(`${this.baseUrl}/auth/users/${id}`, cambios);
  }
}

export default ApuService;
