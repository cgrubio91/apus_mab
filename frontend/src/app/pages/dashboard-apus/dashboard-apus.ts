import { Component, OnInit, ChangeDetectorRef, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { ApuService } from '../../services/apu';

interface PuntoTendencia {
  periodo: string;
  cantidad: number;
}

interface CiudadGeo {
  ciudad: string;
  count: number;
  x: number;
  y: number;
  r: number;
}

interface MapaColombia {
  w: number;
  h: number;
  bounds: [number, number, number, number]; // minLon, minLat, maxLon, maxLat
  paths: string[];
}

// Coordenadas [lon, lat] de las principales ciudades de Colombia (provistas por IA).
const CITY_COORDS: Record<string, [number, number]> = {
  'bogota': [-74.08, 4.61], 'medellin': [-75.56, 6.25], 'cali': [-76.52, 3.44],
  'barranquilla': [-74.80, 10.96], 'cartagena': [-75.51, 10.39], 'bucaramanga': [-73.13, 7.12],
  'manizales': [-75.52, 5.07], 'pereira': [-75.69, 4.81], 'cucuta': [-72.50, 7.89],
  'ibague': [-75.24, 4.44], 'santa marta': [-74.20, 11.24], 'villavicencio': [-73.63, 4.14],
  'pasto': [-77.28, 1.21], 'neiva': [-75.28, 2.93], 'armenia': [-75.68, 4.53],
  'popayan': [-76.61, 2.44], 'monteria': [-75.88, 8.75], 'sincelejo': [-75.40, 9.30],
  'valledupar': [-73.25, 10.46], 'tunja': [-73.36, 5.53], 'riohacha': [-72.91, 11.54],
  'quibdo': [-76.66, 5.69], 'florencia': [-75.61, 1.61], 'yopal': [-72.40, 5.34],
  'leticia': [-69.94, -4.21], 'mocoa': [-76.65, 1.15], 'sonson': [-75.31, 5.71],
  'girardot': [-74.80, 4.30], 'duitama': [-73.03, 5.83], 'sogamoso': [-72.93, 5.71],
  'buenaventura': [-77.03, 3.88], 'tumaco': [-78.79, 1.79], 'apartado': [-76.63, 7.88],
  'turbo': [-76.73, 8.09], 'magangue': [-74.76, 9.24], 'barrancabermeja': [-73.85, 7.06],
  'palmira': [-76.30, 3.54], 'tulua': [-76.20, 4.09], 'cartago': [-75.91, 4.75],
  'zipaquira': [-74.00, 5.03], 'fusagasuga': [-74.36, 4.34], 'facatativa': [-74.36, 4.81],
  'chia': [-74.03, 4.86], 'soacha': [-74.22, 4.58], 'bello': [-75.55, 6.34],
  'itagui': [-75.61, 6.18], 'envigado': [-75.59, 6.17], 'rionegro': [-75.37, 6.15],
  'floridablanca': [-73.09, 7.06], 'giron': [-73.17, 7.07], 'piedecuesta': [-73.05, 6.99],
  'arauca': [-70.76, 7.09], 'inirida': [-67.92, 3.87], 'mitu': [-70.23, 1.25],
  'puerto carreno': [-67.49, 6.19], 'san jose del guaviare': [-72.64, 2.57], 'caucasia': [-75.20, 7.98],
  'la dorada': [-74.66, 5.45], 'espinal': [-74.88, 4.15], 'honda': [-74.74, 5.20],
  'chiquinquira': [-73.82, 5.62],
};

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

    apusPorTipoInsumo: {} as Record<string, number>,
    apusNuevosMes: 0,
    apusMesAnterior: 0,
    proyectosNuevosMes: 0,
    proyectosMesAnterior: 0,
    apusPorMes: [] as PuntoTendencia[],
  };
  isLoading = true;
  errorMessage = '';
  isExporting = false;

  // Mapa
  mapW = 340;
  mapH = 465;
  deptPaths: string[] = [];
  private bounds: [number, number, number, number] | null = null;
  private porCiudadRaw: Record<string, number> = {};
  ciudadesGeo: CiudadGeo[] = [];

  private http = inject(HttpClient);

  constructor(
    private apuService: ApuService,
    private cdr: ChangeDetectorRef
  ) {}

  ngOnInit(): void {
    this.loadMapa();
    this.loadStats();
  }

  private loadMapa(): void {
    this.http.get<MapaColombia>('geo/colombia-paths.json').subscribe({
      next: (m) => {
        this.mapW = m.w;
        this.mapH = m.h;
        this.deptPaths = m.paths || [];
        this.bounds = m.bounds;
        this.rebuildGeo();
        this.cdr.markForCheck();
      },
      error: () => { /* sin mapa: las burbujas no se proyectan */ },
    });
  }

  loadStats(): void {
    this.errorMessage = '';
    this.apuService.getDashboard().subscribe({
      next: (data: any) => {
        this.stats.totalApus = data.total_apus || 0;
        this.stats.totalProyectos = data.total_projects || 0;
        this.stats.totalCiudades = data.total_cities || 0;

        this.stats.apusPorTipoInsumo = data.apus_por_tipo_insumo || {};
        this.stats.apusNuevosMes = data.apus_nuevos_mes || 0;
        this.stats.apusMesAnterior = data.apus_mes_anterior || 0;
        this.stats.proyectosNuevosMes = data.proyectos_nuevos_mes || 0;
        this.stats.proyectosMesAnterior = data.proyectos_mes_anterior || 0;
        this.stats.apusPorMes = data.apus_por_mes || [];
        this.porCiudadRaw = data.apus_por_ciudad || {};
        this.rebuildGeo();
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

  private proj(lon: number, lat: number): [number, number] {
    const b = this.bounds!;
    const PAD = 8;
    const x = PAD + ((lon - b[0]) / (b[2] - b[0])) * (this.mapW - 2 * PAD);
    const y = PAD + ((b[3] - lat) / (b[3] - b[1])) * (this.mapH - 2 * PAD);
    return [Math.round(x * 10) / 10, Math.round(y * 10) / 10];
  }

  private normalizar(nombre: string): string {
    return (nombre || '')
      .toLowerCase()
      .normalize('NFD').replace(/[̀-ͯ]/g, '') // quita tildes
      .replace(/\bd\.?\s?c\.?\b/g, '')
      .replace(/distrito.*$/g, '')
      .replace(/[^a-z\s]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  private rebuildGeo(): void {
    if (!this.bounds || !Object.keys(this.porCiudadRaw).length) return;

    // Unifica variantes del mismo nombre (Bogotá / BOGOTA / Bogotá D.C. → una sola).
    const agrupado = new Map<string, { count: number; coord: [number, number] }>();
    for (const [ciudad, count] of Object.entries(this.porCiudadRaw)) {
      const norm = this.normalizar(ciudad);
      const directo = CITY_COORDS[norm];
      const primera = CITY_COORDS[norm.split(' ')[0]];
      const coord = directo || primera;
      if (!coord) continue;
      const key = directo ? norm : norm.split(' ')[0];
      const prev = agrupado.get(key);
      agrupado.set(key, { count: (prev?.count || 0) + count, coord });
    }

    const max = Math.max(1, ...Array.from(agrupado.values(), (v) => v.count));
    const geo: CiudadGeo[] = [];
    for (const [key, { count, coord }] of agrupado) {
      const [x, y] = this.proj(coord[0], coord[1]);
      const r = 4 + Math.sqrt(count / max) * 16;
      geo.push({ ciudad: this.nombreCanonico(key), count, x, y, r: Math.round(r * 10) / 10 });
    }
    this.ciudadesGeo = geo.sort((a, b) => b.r - a.r);
  }

  private nombreCanonico(norm: string): string {
    const especiales: Record<string, string> = {
      'bogota': 'Bogotá', 'medellin': 'Medellín', 'cucuta': 'Cúcuta', 'ibague': 'Ibagué',
      'monteria': 'Montería', 'popayan': 'Popayán', 'quibdo': 'Quibdó', 'tulua': 'Tuluá',
      'facatativa': 'Facatativá', 'chia': 'Chía', 'itagui': 'Itagüí', 'giron': 'Girón',
      'inirida': 'Inírida', 'mitu': 'Mitú', 'puerto carreno': 'Puerto Carreño',
      'san jose del guaviare': 'San José del Guaviare',
    };
    return especiales[norm] || norm.replace(/\b\w/g, (m) => m.toUpperCase());
  }

  get deltaProyectos(): number {
    return this.stats.proyectosNuevosMes - this.stats.proyectosMesAnterior;
  }

  get maxApusPorMes(): number {
    return Math.max(1, ...this.stats.apusPorMes.map((p) => p.cantidad));
  }

  barHeightMes(p: PuntoTendencia): number {
    return Math.max(4, Math.round((p.cantidad / this.maxApusPorMes) * 100));
  }

  async exportarReporte(): Promise<void> {
    this.isExporting = true;
    try {
      await this.apuService.exportApus({}, 'xlsx');
    } catch {
      this.errorMessage = 'No se pudo exportar el reporte. Intenta de nuevo.';
    } finally {
      this.isExporting = false;
      this.cdr.markForCheck();
    }
  }
}

export default DashboardApus;
