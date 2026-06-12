import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, Subject } from 'rxjs';
import { environment } from '../../environments/environment';

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
            const response = await fetch(`${this.baseUrl}/jobs/${jobId}`);
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


  extractAndSave(file: File): Observable<any> {
    const formData = new FormData();
    formData.append('file', file);
    return this.http.post(`${this.baseUrl}/extract-file?auto_save=true`, formData);
  }

  startExtraction(file: File): Observable<{ job_id: string; status: string; filename: string }> {
    const formData = new FormData();
    formData.append('file', file);
    return this.http.post<{ job_id: string; status: string; filename: string }>(
      `${this.baseUrl}/extract-file-async`,
      formData,
    );
  }

  getJobStatus(jobId: string): Observable<Job> {
    return this.http.get<Job>(`${this.baseUrl}/jobs/${jobId}`);
  }

  getJobEventStream(jobId: string): EventSource {
    return new EventSource(`${this.baseUrl}/jobs/${jobId}/stream`);
  }

  getJobs(): Observable<{ jobs: Job[] }> {
    return this.http.get<{ jobs: Job[] }>(`${this.baseUrl}/jobs`);
  }

  saveExtracted(data: ApuRecord[]): Observable<any> {
    return this.http.post(`${this.baseUrl}/save-extracted`, data);
  }

  saveExtractedStreaming(data: ApuRecord[]): Promise<{ inserted: number; total: number; errors: string[] }> {
    return new Promise((resolve, reject) => {
      fetch(`${this.baseUrl}/save-extracted`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
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

  saveProgress = new Subject<any>();

  chatAssistant(message: string): Observable<any> {
    return this.http.post(`${this.baseUrl}/chat-assistant`, {
      message,
      telefono: 'web-user',
      nombre: 'Usuario Web',
    });
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
}

export default ApuService;
