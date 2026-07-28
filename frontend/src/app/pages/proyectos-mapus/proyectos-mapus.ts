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

interface ItemProyecto {
  id: number;
  parent_id: number | null;
  nivel: number;
  codigo: string;
  nombre: string;
  unidad_medida: string;
  cantidad_presupuestada: number;
  valor_unitario: number;
  valor_presupuestado: number;
  orden: number;
  tipo_item: string;
  apu_solicitud_id: number | null;
  aprobado_por: string | null;
  aprobado_rol: string | null;
  aprobado_en: string | null;
  // derivados en frontend
  hijos?: ItemProyecto[];
  expandido?: boolean;
}

interface DetalleProyecto {
  cargando: boolean;
  error: string;
  capitulos: ItemProyecto[];
  itemsApu: ItemProyecto[];
  totalApu: number;
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

  // Presupuesto desplegable
  expandidoId: number | null = null;
  detalles: { [proyectoId: number]: DetalleProyecto } = {};
  infoAprobacionId: number | null = null;

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
    return new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', minimumFractionDigits: 0 }).format(Number(valor) || 0);
  }

  porcentajePresupuesto(p: ProyectoMapus): string {
    const total = Number(p.presupuesto_total) || 0;
    if (!total) return '0.00';
    return ((Number(p.total_apu_cargado) || 0) / total * 100).toFixed(2);
  }

  // --- Presupuesto desplegable ---

  toggleProyecto(p: ProyectoMapus): void {
    if (this.expandidoId === p.id) {
      this.expandidoId = null;
      return;
    }
    this.expandidoId = p.id;
    this.infoAprobacionId = null;
    if (!this.detalles[p.id]) {
      this.cargarDetalle(p.id);
    }
  }

  cargarDetalle(proyectoId: number): void {
    this.detalles[proyectoId] = { cargando: true, error: '', capitulos: [], itemsApu: [], totalApu: 0 };
    this.apuService.getProyectoDetalle(proyectoId).subscribe({
      next: (data: any) => {
        const items: ItemProyecto[] = (data.items || []).map((i: any) => ({
          ...i,
          valor_presupuestado: Number(i.valor_presupuestado) || 0,
          valor_unitario: Number(i.valor_unitario) || 0,
          cantidad_presupuestada: Number(i.cantidad_presupuestada) || 0,
        }));
        // Presupuesto base: capítulos (nivel 1, PREVISTO) con sus ítems hijos.
        const capitulos = items.filter((i) => i.nivel === 1 && !i.apu_solicitud_id);
        for (const cap of capitulos) {
          cap.hijos = items.filter((i) => i.parent_id === cap.id);
          cap.expandido = false;
        }
        // Ítems cargados desde un APU aprobado (No Previstos).
        const itemsApu = items.filter((i) => i.apu_solicitud_id);
        this.detalles[proyectoId] = {
          cargando: false, error: '', capitulos, itemsApu,
          totalApu: itemsApu.reduce((s, i) => s + i.valor_presupuestado, 0),
        };
        this.cdr.markForCheck();
      },
      error: () => {
        this.detalles[proyectoId] = { cargando: false, error: 'No se pudo cargar el detalle del presupuesto.', capitulos: [], itemsApu: [], totalApu: 0 };
        this.cdr.markForCheck();
      },
    });
  }

  toggleCapitulo(cap: ItemProyecto): void {
    cap.expandido = !cap.expandido;
  }

  toggleInfoAprobacion(itemId: number): void {
    this.infoAprobacionId = this.infoAprobacionId === itemId ? null : itemId;
  }

  formatearFecha(fecha: string | null): string {
    if (!fecha) return '—';
    const d = new Date(fecha.includes('T') || fecha.includes('Z') ? fecha : fecha.replace(' ', 'T') + 'Z');
    return isNaN(d.getTime()) ? fecha : new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium', timeStyle: 'short' }).format(d);
  }
}

export default ProyectosMapus;
