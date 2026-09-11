import { Component, OnInit, ChangeDetectorRef, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { ApuService, FilterOptions, HistoricoDetalle, HistoricoInsumo, HistoricoPunto } from '../../services/apu';

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

  /** Respuesta cruda del backend, sin filtrar por año. */
  private puntosRaw: HistoricoPunto[] = [];
  private insumosRaw: HistoricoInsumo[] = [];

  /** Lo que pinta la plantilla: recalculado a partir de *Raw cada vez que cambia el año. */
  puntos: HistoricoPunto[] = [];
  insumos: HistoricoInsumo[] = [];

  /** Años presentes en la última búsqueda, más reciente primero. */
  anios: string[] = [];
  /** '' = todos los años. */
  anioSeleccionado = '';

  /** Descripciones desplegadas en la tabla, para ver su evolución mensual. */
  expandidos = new Set<string>();
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
        this.puntosRaw = res.data || [];
        this.insumosRaw = res.insumos || [];
        this.expandidos.clear();
        this.anioSeleccionado = '';
        this.anios = Array.from(new Set(this.puntosRaw.map(p => p.periodo.slice(0, 4))))
          .sort((a, b) => b.localeCompare(a));
        this.aplicarFiltroAnio();
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

  /** Recalcula `puntos` e `insumos` a partir de *Raw, limitados al año elegido. */
  onAnioChange(): void {
    this.aplicarFiltroAnio();
    this.cdr.markForCheck();
  }

  private aplicarFiltroAnio(): void {
    const anio = this.anioSeleccionado;

    this.puntos = anio ? this.puntosRaw.filter(p => p.periodo.startsWith(anio)) : this.puntosRaw;

    const insumos: HistoricoInsumo[] = [];
    for (const ins of this.insumosRaw) {
      const detalle = anio ? ins.detalle.filter(d => d.anio === anio) : ins.detalle;
      if (detalle.length === 0) continue; // el insumo no tuvo hallazgos en ese año
      insumos.push({
        insumo_descripcion: ins.insumo_descripcion,
        ...this.consolidarDetalle(detalle),
        ciudades: Array.from(new Set(detalle.map(d => d.ciudad))).sort(),
        detalle,
      });
    }
    insumos.sort((a, b) => b.precio_promedio - a.precio_promedio);
    this.insumos = insumos;
  }

  /** Mismo criterio de consolidación que el backend: el promedio se pondera por
   *  número de registros, no por cantidad de filas (un mes con 4.928 registros
   *  pesa más que uno con 4). */
  private consolidarDetalle(detalle: HistoricoDetalle[]): Pick<HistoricoInsumo, 'precio_promedio' | 'precio_minimo' | 'precio_maximo' | 'registros'> {
    const registros = detalle.reduce((acc, d) => acc + d.registros, 0);
    const suma = detalle.reduce((acc, d) => acc + d.precio_promedio * d.registros, 0);
    return {
      precio_promedio: registros ? suma / registros : 0,
      precio_minimo: Math.min(...detalle.map(d => d.precio_minimo)),
      precio_maximo: Math.max(...detalle.map(d => d.precio_maximo)),
      registros,
    };
  }

  /** Si la búsqueda trajo datos en algún año (independiente del filtro actual). */
  get tieneResultados(): boolean {
    return this.puntosRaw.length > 0;
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

  private router = inject(Router);

  /** Abre el Banco de APUs filtrado por el insumo, ciudad y proyecto buscados.
   *  Si se pasa una descripción concreta, filtra por ella y no por el término buscado. */
  verRegistros(descripcion?: string): void {
    const queryParams: Record<string, string> = { q: descripcion || this.insumo.trim() };
    if (this.ciudad) queryParams['ciudad'] = this.ciudad;
    if (this.proyecto) queryParams['proyecto'] = this.proyecto;
    this.router.navigate(['/consulta-apus'], { queryParams });
  }

  toggleInsumo(i: HistoricoInsumo): void {
    if (this.expandidos.has(i.insumo_descripcion)) {
      this.expandidos.delete(i.insumo_descripcion);
    } else {
      this.expandidos.add(i.insumo_descripcion);
    }
  }

  estaExpandido(i: HistoricoInsumo): boolean {
    return this.expandidos.has(i.insumo_descripcion);
  }

  trackByPeriodo(_i: number, p: HistoricoPunto): string {
    return p.periodo;
  }

  trackByInsumo(_i: number, item: HistoricoInsumo): string {
    return item.insumo_descripcion;
  }

  trackByDetalle(_i: number, d: HistoricoDetalle): string {
    return d.periodo + '|' + d.ciudad;
  }

  /** Resumen corto de ciudades para la fila del insumo (sin expandir). */
  resumenCiudades(i: HistoricoInsumo): string {
    if (i.ciudades.length <= 2) return i.ciudades.join(', ');
    return `${i.ciudades.slice(0, 2).join(', ')} +${i.ciudades.length - 2} más`;
  }
}

export default HistoricoPrecios;
