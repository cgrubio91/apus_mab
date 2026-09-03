import { Component, OnInit, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { ApuService, ApuRecord } from '../../services/apu';

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
  hijos?: ItemProyecto[];
  expandido?: boolean;
}

@Component({
  selector: 'app-proyecto-detalle',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './proyecto-detalle.html',
  styleUrl: './proyecto-detalle.scss',
})
export class ProyectoDetalle implements OnInit {
  proyectoId!: number;
  proyecto: { id: number; id_proy: number; descripcion: string; presupuesto_total: number } | null = null;

  cargando = true;
  error = '';
  capitulos: ItemProyecto[] = [];
  itemsApu: ItemProyecto[] = [];
  totalApu = 0;
  infoAprobacionId: number | null = null;

  apusBanco: ApuRecord[] = [];
  apusBancoTotal = 0;
  cargandoApusBanco = true;

  constructor(
    private route: ActivatedRoute,
    private apuService: ApuService,
    private cdr: ChangeDetectorRef
  ) {}

  ngOnInit(): void {
    this.proyectoId = Number(this.route.snapshot.paramMap.get('id'));
    this.cargarDetalle();
    this.cargarApusBanco();
  }

  cargarDetalle(): void {
    this.cargando = true;
    this.error = '';
    this.apuService.getProyectoDetalle(this.proyectoId).subscribe({
      next: (data: any) => {
        this.proyecto = data.proyecto || null;
        const items: ItemProyecto[] = (data.items || []).map((i: any) => ({
          ...i,
          valor_presupuestado: Number(i.valor_presupuestado) || 0,
          valor_unitario: Number(i.valor_unitario) || 0,
          cantidad_presupuestada: Number(i.cantidad_presupuestada) || 0,
        }));
        const capitulos = items.filter((i) => i.nivel === 1 && !i.apu_solicitud_id);
        for (const cap of capitulos) {
          cap.hijos = items.filter((i) => i.parent_id === cap.id);
          cap.expandido = false;
        }
        this.capitulos = capitulos;
        this.itemsApu = items.filter((i) => i.apu_solicitud_id);
        this.totalApu = this.itemsApu.reduce((s, i) => s + i.valor_presupuestado, 0);
        this.cargando = false;
        this.cdr.markForCheck();
      },
      error: () => {
        this.error = 'No se pudo cargar el detalle del proyecto.';
        this.cargando = false;
        this.cdr.markForCheck();
      },
    });
  }

  cargarApusBanco(): void {
    this.cargandoApusBanco = true;
    this.apuService.getApusDeProyecto(this.proyectoId).subscribe({
      next: (data: any) => {
        this.apusBanco = data.apus || [];
        this.apusBancoTotal = data.total || 0;
        this.cargandoApusBanco = false;
        this.cdr.markForCheck();
      },
      error: () => {
        this.cargandoApusBanco = false;
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

  formatearMoneda(valor: number): string {
    return new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', minimumFractionDigits: 0 }).format(Number(valor) || 0);
  }

  formatearFecha(fecha: string | null): string {
    if (!fecha) return '—';
    const d = new Date(fecha.includes('T') || fecha.includes('Z') ? fecha : fecha.replace(' ', 'T') + 'Z');
    return isNaN(d.getTime()) ? fecha : new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium', timeStyle: 'short' }).format(d);
  }
}

export default ProyectoDetalle;
