import { Component, OnInit } from '@angular/core';
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
    ultimoMes: 0,
  };
  isLoading = true;

  constructor(private apuService: ApuService) {}

  ngOnInit(): void {
    this.loadStats();
  }

  loadStats(): void {
    this.apuService.getDashboard().subscribe({
      next: (data: any) => {
        this.stats.totalApus = data.total_apus || 0;
        this.stats.totalProyectos = data.total_proyectos || 0;
        this.stats.totalCiudades = data.total_ciudades || 0;
        this.stats.ultimoMes = data.ultimo_mes || 0;
        this.isLoading = false;
      },
      error: () => {
        this.isLoading = false;
      },
    });
  }
}

export default DashboardApus;