import { Component, OnInit, OnDestroy, HostListener, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApuService, ApuRecord, FilterOptions } from '../../services/apu';

interface ColumnDef {
  key: string;
  label: string;
  type: 'text' | 'number' | 'date';
  sortable: boolean;
  filterable: boolean;
  width?: string;
}

@Component({
  selector: 'app-consulta-apus',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './consulta-apus.html',
  styleUrl: './consulta-apus.scss',
})
export class ConsultaApus implements OnInit, OnDestroy {
  apus: ApuRecord[] = [];
  total = 0;
  isLoading = false;
  pageSize = 50;
  currentPage = 1;
  totalPages = 1;

  sortBy: string = '';
  sortOrder: 'asc' | 'desc' = 'asc';
  searchText: string = '';

  filterOptions: FilterOptions = { proyectos: [], ciudades: [], tipos_insumo: [], entidades: [], contratistas: [] };

  columns: ColumnDef[] = [
    { key: 'id', label: 'ID', type: 'number', sortable: true, filterable: false, width: '60px' },
    { key: 'nombre_proyecto', label: 'PROYECTO', type: 'text', sortable: true, filterable: true },
    { key: 'ciudad', label: 'CIUDAD', type: 'text', sortable: true, filterable: true },
    { key: 'pais', label: 'PAÍS', type: 'text', sortable: true, filterable: true },
    { key: 'entidad', label: 'ENTIDAD', type: 'text', sortable: true, filterable: true },
    { key: 'contratista', label: 'CONTRATISTA', type: 'text', sortable: true, filterable: true },
    { key: 'numero_contrato', label: 'No CONTRATO', type: 'text', sortable: true, filterable: true },
    { key: 'fecha_aprobacion_apu', label: 'FECHA APROB.', type: 'date', sortable: true, filterable: false },
    { key: 'fecha_analisis_apu', label: 'FECHA ANÁLISIS', type: 'date', sortable: true, filterable: false },
    { key: 'item', label: 'ITEM', type: 'text', sortable: true, filterable: true },
    { key: 'items_descripcion', label: 'ITEM DESCRIPCIÓN', type: 'text', sortable: true, filterable: true },
    { key: 'item_unidad', label: 'ITEM UND.', type: 'text', sortable: true, filterable: true },
    { key: 'precio_unitario', label: 'PRECIO UNIT.', type: 'number', sortable: true, filterable: false },
    { key: 'precio_unitario_sin_aiu', label: 'PRECIO S/ AIU', type: 'number', sortable: true, filterable: false },
    { key: 'codigo_insumo', label: 'CÓDIGO INSUMO', type: 'text', sortable: true, filterable: true },
    { key: 'tipo_insumo', label: 'TIPO INSUMO', type: 'text', sortable: true, filterable: true },
    { key: 'insumo_descripcion', label: 'INSUMO DESCRIPCIÓN', type: 'text', sortable: true, filterable: true },
    { key: 'insumo_unidad', label: 'INSUMO UND.', type: 'text', sortable: true, filterable: true },
    { key: 'rendimiento_insumo', label: 'RENDIMIENTO', type: 'number', sortable: true, filterable: false },
    { key: 'precio_unitario_apu', label: 'VR. UNIT. APU', type: 'number', sortable: true, filterable: false },
    { key: 'precio_parcial_apu', label: 'VR. PARCIAL APU', type: 'number', sortable: true, filterable: false },
    { key: 'observacion', label: 'OBSERVACIÓN', type: 'text', sortable: true, filterable: true },
  ];

  filters: Record<string, string> = {};
  activeFilterCol: string | null = null;
  filterSearchText: Record<string, string> = {};
  filteredOptionLists: Record<string, string[]> = {};

  constructor(
    private apuService: ApuService,
    private cdr: ChangeDetectorRef
  ) {}

  ngOnInit(): void {
    this.loadFilterOptions();
    this.loadApus();
  }

  ngOnDestroy(): void {
    this.activeFilterCol = null;
  }

  @HostListener('document:click')
  onDocumentClick(): void {
    this.activeFilterCol = null;
  }

  loadFilterOptions(): void {
    this.apuService.getFilterOptions().subscribe({
      next: (opts) => {
        this.filterOptions = opts;
        for (const [key, list] of Object.entries(opts)) {
          const mapKey = this.filterKeyFromOptionKey(key);
          this.filteredOptionLists[mapKey] = [...list];
        }
        const proyKey = 'nombre_proyecto';
        if (this.filters[proyKey] && !this.filteredOptionLists[proyKey]?.includes(this.filters[proyKey])) {
          this.filteredOptionLists[proyKey]?.push(this.filters[proyKey]);
          this.filteredOptionLists[proyKey]?.sort();
        }
        this.cdr.markForCheck();
      },
      error: () => {
        this.cdr.markForCheck();
      },
    });
  }

  private filterKeyFromOptionKey(optionKey: string): string {
    const map: Record<string, string> = {
      proyectos: 'nombre_proyecto',
      ciudades: 'ciudad',
      tipos_insumo: 'tipo_insumo',
      entidades: 'entidad',
      contratistas: 'contratista',
    };
    return map[optionKey] || optionKey;
  }

  get visibleColumns(): ColumnDef[] {
    return this.columns.filter(c => c.key !== 'id');
  }

  loadApus(): void {
    this.isLoading = true;
    const cleanFilters: any = { limit: this.pageSize, offset: (this.currentPage - 1) * this.pageSize };
    for (const [key, val] of Object.entries(this.filters)) {
      if (val) cleanFilters[key] = val;
    }
    if (this.sortBy) {
      cleanFilters.sort_by = this.sortBy;
      cleanFilters.sort_order = this.sortOrder;
    }
    if (this.searchText) {
      cleanFilters.search = this.searchText;
    }
    this.apuService.getApus(cleanFilters).subscribe({
      next: (response: any) => {
        this.apus = response.data || [];
        this.total = response.total || 0;
        this.totalPages = Math.ceil(this.total / this.pageSize);
        this.isLoading = false;
        this.cdr.markForCheck();
      },
      error: () => {
        this.isLoading = false;
        this.cdr.markForCheck();
      },
    });
  }

  sortByColumn(col: ColumnDef): void {
    if (!col.sortable) return;
    if (this.sortBy === col.key) {
      this.sortOrder = this.sortOrder === 'asc' ? 'desc' : 'asc';
    } else {
      this.sortBy = col.key;
      this.sortOrder = 'asc';
    }
    this.currentPage = 1;
    this.loadApus();
  }

  getSortIcon(col: ColumnDef): string {
    if (this.sortBy !== col.key) return '';
    return this.sortOrder === 'asc' ? '▲' : '▼';
  }

  toggleFilterDropdown(col: ColumnDef, event: MouseEvent): void {
    event.stopPropagation();
    if (!col.filterable) return;
    if (this.activeFilterCol === col.key) {
      this.activeFilterCol = null;
    } else {
      this.activeFilterCol = col.key;
      this.filterSearchText[col.key] = this.filters[col.key] || '';
      this.updateFilteredList(col);
    }
  }

  onFilterInputChange(col: ColumnDef): void {
    this.updateFilteredList(col);
  }

  private updateFilteredList(col: ColumnDef): void {
    const allOptions = this.getFilterOptionsFor(col);
    const search = (this.filterSearchText[col.key] || '').toLowerCase();
    if (search && allOptions.length) {
      this.filteredOptionLists[col.key] = allOptions.filter(o => o.toLowerCase().includes(search));
    } else {
      this.filteredOptionLists[col.key] = [...allOptions];
    }
  }

  selectFilterOption(col: ColumnDef, value: string): void {
    this.filters[col.key] = value;
    this.filterSearchText[col.key] = value;
    this.activeFilterCol = null;
    this.currentPage = 1;
    this.loadApus();
  }

  clearColumnFilter(col: ColumnDef, event: MouseEvent): void {
    event.stopPropagation();
    delete this.filters[col.key];
    delete this.filterSearchText[col.key];
    this.activeFilterCol = null;
    this.currentPage = 1;
    this.loadApus();
  }

  applyColumnTextFilter(col: ColumnDef): void {
    const val = this.filterSearchText[col.key]?.trim() || '';
    this.filters[col.key] = val;
    this.activeFilterCol = null;
    this.currentPage = 1;
    this.loadApus();
  }

  onSearch(): void {
    this.currentPage = 1;
    this.loadApus();
  }

  resetFilters(): void {
    this.filters = {};
    this.searchText = '';
    this.sortBy = '';
    this.sortOrder = 'asc';
    this.currentPage = 1;
    this.loadApus();
  }

  hasActiveFilters(): boolean {
    return Object.values(this.filters).some(v => !!v) || !!this.searchText;
  }

  goToPage(page: number): void {
    if (page < 1 || page > this.totalPages) return;
    this.currentPage = page;
    this.loadApus();
  }

  nextPage(): void {
    if (this.currentPage < this.totalPages) {
      this.goToPage(this.currentPage + 1);
    }
  }

  prevPage(): void {
    if (this.currentPage > 1) {
      this.goToPage(this.currentPage - 1);
    }
  }

  getPages(): number[] {
    const pages: number[] = [];
    const maxVisible = 5;
    let start = Math.max(1, this.currentPage - Math.floor(maxVisible / 2));
    let end = Math.min(this.totalPages, start + maxVisible - 1);
    if (end - start < maxVisible - 1) {
      start = Math.max(1, end - maxVisible + 1);
    }
    for (let i = start; i <= end; i++) {
      pages.push(i);
    }
    return pages;
  }

  getFilterOptionsFor(col: ColumnDef): string[] {
    switch (col.key) {
      case 'nombre_proyecto': return this.filterOptions.proyectos;
      case 'ciudad': return this.filterOptions.ciudades;
      case 'tipo_insumo': return this.filterOptions.tipos_insumo;
      case 'entidad': return this.filterOptions.entidades;
      case 'contratista': return this.filterOptions.contratistas;
      default: return [];
    }
  }

  hasFilterOptions(col: ColumnDef): boolean {
    return col.key === 'nombre_proyecto' || col.key === 'ciudad' ||
           col.key === 'tipo_insumo' || col.key === 'entidad' ||
           col.key === 'contratista';
  }

  getCellValue(apu: any, col: ColumnDef): any {
    return apu[col.key];
  }

  formatCellValue(apu: any, col: ColumnDef): string {
    const val = this.getCellValue(apu, col);
    if (val === null || val === undefined || val === '–' || val === '') return '—';
    if (col.type === 'number') {
      const num = Number(val);
      if (isNaN(num)) return val;
      if (['precio_unitario', 'precio_unitario_sin_aiu', 'precio_unitario_apu', 'precio_parcial_apu'].includes(col.key)) {
        return '$ ' + num.toLocaleString('es-CO', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
      }
      return num.toLocaleString('es-CO', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
    }
    if (col.type === 'date') {
      if (typeof val === 'string' && val.length === 10) {
        const d = new Date(val + 'T00:00:00');
        return d.toLocaleDateString('es-CO', { day: '2-digit', month: 'short', year: 'numeric' });
      }
      return val;
    }
    return val;
  }

  getCellClass(apu: any, col: ColumnDef): string {
    const val = this.getCellValue(apu, col);
    const classes: string[] = [];
    if (val === null || val === undefined || val === '–' || val === '') classes.push('empty-cell');
    if (col.type === 'number') classes.push('cell-numeric');
    if (col.key === 'codigo_insumo' || col.key === 'item') classes.push('cell-mono');
    return classes.join(' ');
  }
}

export default ConsultaApus;
