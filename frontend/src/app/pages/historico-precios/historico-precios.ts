import { Component, OnInit, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApuService, FilterOptions, HistoricoPunto } from '../../services/apu';

@Component({
  selector: 'app-historico-precios',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './historico-precios.html',
  styleUrl: './historico-precios.scss',
})
export class HistoricoPrecios implements OnInit {
  insumo = '';
  ciudad = '';
  proyecto = '';

  ciudades: string[] = [];
  proyectos: string[] = [];

  puntos: HistoricoPunto[] = [];
  isLoading = false;
  buscado = false;
  errorMessage = '';

  constructor(
    private apuService: ApuService,
    private cdr: ChangeDetectorRef,
  ) {}

  ngOnInit(): void {
    this.apuService.getFilterOptions().subscribe({
      next: (opts: FilterOptions) => {
        this.ciudades = opts.ciudades || [];
        this.proyectos = opts.proyectos || [];
        this.cdr.markForCheck();
      },
      error: () => { /* los selects quedan vacíos; la búsqueda por insumo sigue funcionando */ },
    });
  }

  buscar(): void {
    const term = this.insumo.trim();
    if (term.length < 3) {
      this.errorMessage = 'Escribe al menos 3 caracteres del insumo (ej: "concreto", "acero").';
      return;
    }
    this.isLoading = true;
    this.errorMessage = '';
    this.apuService.getHistoricoPrecios(term, this.ciudad || undefined, this.proyecto || undefined).subscribe({
      next: (res) => {
        this.puntos = res.data || [];
        this.buscado = true;
        this.isLoading = false;
        this.cdr.markForCheck();
      },
      error: () => {
        this.errorMessage = 'No se pudo consultar el histórico. Intenta de nuevo.';
        this.isLoading = false;
        this.cdr.markForCheck();
      },
    });
  }

  get maxPrecio(): number {
    return Math.max(...this.puntos.map(p => p.precio_maximo), 1);
  }

  barHeight(p: HistoricoPunto): number {
    return Math.max(4, Math.round((p.precio_promedio / this.maxPrecio) * 100));
  }

  variacionTotal(): number | null {
    if (this.puntos.length < 2) return null;
    const primero = this.puntos[0].precio_promedio;
    const ultimo = this.puntos[this.puntos.length - 1].precio_promedio;
    if (!primero) return null;
    return ((ultimo - primero) / primero) * 100;
  }

  formatCOP(value: number): string {
    return new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 }).format(value);
  }

  trackByPeriodo(_i: number, p: HistoricoPunto): string {
    return p.periodo;
  }
}

export default HistoricoPrecios;
