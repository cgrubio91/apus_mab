import { Component, OnDestroy, ChangeDetectorRef, NgZone } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { Subscription } from 'rxjs';
import { ApuService, Job } from '../../services/apu';

@Component({
  selector: 'app-nuevos-apu-ia',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './nuevos-apu-ia.html',
  styleUrl: './nuevos-apu-ia.scss',
})
export class NuevosApuIa implements OnDestroy {
  selectedFile: File | null = null;
  isUploading = false;
  extracting = false;
  extractedData: any = null;
  isSaving = false;
  saved = false;
  error: string | null = null;

  saveProgress = 0;
  saveTotal = 0;
  saveErrors: string[] = [];
  saveResult: { inserted: number; total: number } | null = null;

  // Tracking elapsed time
  elapsedSeconds = 0;
  elapsedDisplay = '';

  // Background Job Tracking
  jobId: string | null = null;
  jobPhase: string = '';
  jobPercent: number = 0;
  jobBatches: string = '';
  processInBackground: boolean = false;
  notificationsEnabled: boolean = false;

  private progressSub: Subscription | null = null;
  private jobSub: Subscription | null = null;
  private timerInterval: any = null;

  constructor(
    private apuService: ApuService,
    private router: Router,
    private cdr: ChangeDetectorRef,
    private ngZone: NgZone,
  ) {
    if ('Notification' in window) {
      this.notificationsEnabled = Notification.permission === 'granted';
    }
  }

  ngOnDestroy(): void {
    this.progressSub?.unsubscribe();
    this.jobSub?.unsubscribe();
    this.stopTimer();
  }

  requestNotificationPermission(): void {
    if ('Notification' in window && Notification.permission !== 'granted') {
      Notification.requestPermission().then(permission => {
        this.notificationsEnabled = permission === 'granted';
      });
    }
  }

  toggleBackgroundProcessing(): void {
    this.processInBackground = !this.processInBackground;
    if (this.processInBackground && !this.notificationsEnabled) {
      this.requestNotificationPermission();
    }
  }

  onFileSelected(event: any): void {
    const file = event.target.files[0];
    if (file) {
      const ext = file.name.split('.').pop()?.toLowerCase();
      if (ext === 'pdf' || ext === 'xlsx' || ext === 'xls') {
        this.selectedFile = file;
        this.error = null;
        this.extractedData = null;
        this.saved = false;
        this.saveResult = null;
      } else {
        this.error = 'Formato no soportado. Use PDF o Excel (.xlsx, .xls)';
        this.selectedFile = null;
      }
    }
  }

  uploadFile(): void {
    if (!this.selectedFile) return;

    this.isUploading = true;
    this.extracting = true;
    this.error = null;
    this.extractedData = null;
    this.elapsedSeconds = 0;
    this.elapsedDisplay = '';
    this.startTimer();

    this.apuService.extractFile(this.selectedFile).subscribe({
      next: (response) => {
        if (response.success && response.job_id) {
          this.jobId = response.job_id;
          this.listenToJob(response.job_id);
        } else {
          this.handleError('Error iniciando el proceso.');
        }
      },
      error: (err) => {
        this.handleError('Error al subir el archivo. ' + err.message);
      },
    });
  }

  private listenToJob(jobId: string): void {
    this.jobSub = this.apuService.streamJobProgress(jobId).subscribe({
      next: (job: Job) => {
        this.ngZone.run(() => {
          this.jobPhase = job.progress.phase;
          this.jobPercent = job.progress.percent;
          
          if (job.progress.total_batches > 0) {
            this.jobBatches = `(${job.progress.current_batch}/${job.progress.total_batches})`;
          } else {
            this.jobBatches = '';
          }

          if (job.status === 'DONE') {
            this.stopTimer();
            this.extractedData = job.result;
            this.isUploading = false;
            this.extracting = false;
            this.notifyComplete();
          } else if (job.status === 'ERROR') {
            this.handleError('Error en extracción: ' + (job.error || 'Error desconocido'));
          }
          
          this.cdr.detectChanges();
        });
      },
      error: (err) => {
        this.ngZone.run(() => {
          console.error('Job stream error:', err);
          this.handleError('Error de conexión. Reintentando...');
        });
      }
    });
  }

  private notifyComplete() {
    if (this.processInBackground && this.notificationsEnabled && document.visibilityState === 'hidden') {
      new Notification('Extracción Completada', {
        body: `El archivo ${this.selectedFile?.name} ha sido procesado exitosamente.`,
        icon: '/favicon.ico'
      });
    }
  }

  private handleError(msg: string) {
    this.stopTimer();
    this.error = msg;
    this.isUploading = false;
    this.extracting = false;
    this.jobSub?.unsubscribe();
  }

  private startTimer(): void {
    this.stopTimer();
    this.timerInterval = setInterval(() => {
      this.elapsedSeconds++;
      this.elapsedDisplay = this.formatElapsedTime(this.elapsedSeconds);
    }, 1000);
  }

  private stopTimer(): void {
    if (this.timerInterval) {
      clearInterval(this.timerInterval);
      this.timerInterval = null;
    }
  }

  private formatElapsedTime(seconds: number): string {
    const minutes = Math.floor(seconds / 60);
    const secs = seconds % 60;
    if (minutes === 0) return `${secs}s`;
    if (minutes < 60) return `${minutes}m ${secs}s`;
    const hours = Math.floor(minutes / 60);
    return `${hours}h ${minutes % 60}m`;
  }

  saveExtracted(): void {
    if (!this.extractedData?.insumos?.length) return;

    this.isSaving = true;
    this.error = null;
    this.saveProgress = 0;
    this.saveTotal = this.extractedData.insumos.length;
    this.saveErrors = [];
    this.saveResult = null;

    this.progressSub = this.apuService.saveProgress.subscribe({
      next: (update: any) => {
        this.ngZone.run(() => {
          if (update.type === 'progress' || update.type === 'complete') {
            this.saveProgress = update.inserted;
            this.saveTotal = update.total;
            if (update.errors?.length) {
              this.saveErrors = update.errors;
            }
          }
          if (update.type === 'complete') {
            this.saveResult = { inserted: update.inserted, total: update.total };
            this.isSaving = false;
            this.saved = true;
          }
          this.cdr.detectChanges();
        });
      },
      error: () => {
        this.ngZone.run(() => {
          this.error = 'Error al guardar los datos.';
          this.isSaving = false;
        });
      },
    });

    this.apuService.saveExtractedStreaming(this.extractedData.insumos).catch((err) => {
      this.error = 'Error de conexión al guardar.';
      this.isSaving = false;
      console.error(err);
    });
  }

  goToDashboard(): void {
    this.router.navigate(['/dashboard-apus']);
  }

  resetForm(): void {
    this.stopTimer();
    this.selectedFile = null;
    this.extractedData = null;
    this.error = null;
    this.isUploading = false;
    this.extracting = false;
    this.isSaving = false;
    this.saved = false;
    this.saveProgress = 0;
    this.saveTotal = 0;
    this.saveErrors = [];
    this.saveResult = null;
    this.elapsedSeconds = 0;
    this.elapsedDisplay = '';
    
    this.jobId = null;
    this.jobPhase = '';
    this.jobPercent = 0;
    this.jobBatches = '';

    this.progressSub?.unsubscribe();
    this.progressSub = null;
    this.jobSub?.unsubscribe();
    this.jobSub = null;
  }
}
