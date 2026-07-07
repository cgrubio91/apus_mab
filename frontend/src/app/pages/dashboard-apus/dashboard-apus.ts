import { Component, OnInit, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ApuService } from '../../services/apu';

@Component({
  selector: 'app-dashboard-apus',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './dashboard-apus.html',
  styleUrl: './dashboard-apus.scss',
})
export class DashboardApus implements OnInit {
  stats = {
    totalApus: 0,
    totalProyectos: 0,
    totalCiudades: 0,
    precisionIA: 0,
    apusPorTipoInsumo: {} as Record<string, number>,
  };
  isLoading = true;
  errorMessage = '';

  constructor(
    private apuService: ApuService,
    private cdr: ChangeDetectorRef
  ) {}

  ngOnInit(): void {
    this.loadStats();
  }

  loadStats(): void {
    this.errorMessage = '';
    this.apuService.getDashboard().subscribe({
      next: (data: any) => {
        this.stats.totalApus = data.total_apus || 0;
        this.stats.totalProyectos = data.total_projects || 0;
        this.stats.totalCiudades = data.total_cities || 0;
        this.stats.precisionIA = data.completitud_datos || 0;
        this.stats.apusPorTipoInsumo = data.apus_por_tipo_insumo || {};
        this.isLoading = false;
        this.cdr.markForCheck();
      },
      error: () => {
        this.errorMessage = 'No se pudieron cargar las estadísticas. Verifica tu conexión e intenta de nuevo.';
        this.isLoading = false;
        this.cdr.markForCheck();
      },
    });
  }
}

export default DashboardApus;