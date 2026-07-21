import { Component, OnInit, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApuService } from '../../services/apu';

interface ProyectoMapus {
  id: number;
  id_proy: number;
  descripcion: string;
  presupuesto_total: number;
  items_apu_cargados: number;
  items_apu_aprobados: number;
  total_apu_cargado: number;
}

@Component({
  selector: 'app-proyectos-mapus',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './proyectos-mapus.html',
  styleUrl: './proyectos-mapus.scss',
})
export class ProyectosMapus implements OnInit {
  proyectos: ProyectoMapus[] = [];
  isLoading = true;
  errorMessage = '';
  showModal = false;
  creating = false;

  form = {
    id_proy: 0,
    descripcion: '',
    presupuesto_total: 0,
    id_folder: 'local',
    id_folder_bim: '',
    pdo_current_version_id: null as number | null,
    pdo_drive_subfolder_id: '',
  };

  constructor(
    private apuService: ApuService,
    private cdr: ChangeDetectorRef
  ) {}

  ngOnInit(): void {
    this.cargarProyectos();
  }

  cargarProyectos(): void {
    this.errorMessage = '';
    this.apuService.getProyectosMapus().subscribe({
      next: (data: any) => {
        this.proyectos = data.proyectos || [];
        this.isLoading = false;
        this.cdr.markForCheck();
      },
      error: () => {
        this.errorMessage = 'No se pudieron cargar los proyectos. Verifica tu conexión e intenta de nuevo.';
        this.isLoading = false;
        this.cdr.markForCheck();
      },
    });
  }

  abrirModal(): void {
    this.form = { id_proy: 0, descripcion: '', presupuesto_total: 0, id_folder: 'local', id_folder_bim: '', pdo_current_version_id: null, pdo_drive_subfolder_id: '' };
    this.showModal = true;
  }

  cerrarModal(): void {
    this.showModal = false;
  }

  crearProyecto(): void {
    if (!this.form.id_proy) return;
    this.creating = true;
    this.apuService.crearProyecto(this.form).subscribe({
      next: () => {
        this.creating = false;
        this.showModal = false;
        this.cargarProyectos();
      },
      error: () => {
        this.creating = false;
        this.errorMessage = 'Error al crear el proyecto.';
        this.cdr.markForCheck();
      },
    });
  }

  formatearMoneda(valor: number): string {
    return new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', minimumFractionDigits: 0 }).format(valor);
  }

  porcentajePresupuesto(p: ProyectoMapus): string {
    if (!p.presupuesto_total) return '0';
    return ((p.total_apu_cargado / p.presupuesto_total) * 100).toFixed(2);
  }
}

export default ProyectosMapus;
