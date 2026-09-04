import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ConstructorApu } from './constructor-apu';
import { provideHttpClient } from '@angular/common/http';
import { provideRouter } from '@angular/router';

describe('ConstructorApu', () => {
  let component: ConstructorApu;
  let fixture: ComponentFixture<ConstructorApu>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ConstructorApu],
      providers: [
        provideHttpClient(),
        provideRouter([]),
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(ConstructorApu);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('inicia el wizard en el paso 1', () => {
    expect(component.paso).toBe(1);
  });

  it('rechaza actividad demasiado corta', () => {
    component.descripcionActividad = 'abc';
    component.crearYSugerir();
    expect(component.errorMessage).toContain('al menos 5 caracteres');
  });

  it('recalcula el costo directo al editar filas', () => {
    component.filas = [
      { incluir: true, tipo_insumo: 'Materiales', descripcion: 'Cemento', unidad: 'kg', rendimiento: 2, precio: 1000, fuente: '' },
      { incluir: false, tipo_insumo: 'Equipos', descripcion: 'Mixer', unidad: 'h', rendimiento: 1, precio: 99999, fuente: '' },
      { incluir: true, tipo_insumo: 'Materiales', descripcion: 'Arena', unidad: 'm3', rendimiento: 1, precio: null, fuente: '' },
    ];
    expect(component.costoDirectoPreliminar).toBe(2000);
    expect(component.desgloseAiuVivo.costo_directo).toBe(2000);
  });

  it('no incorpora si aún no hay firma legal', () => {
    component.solicitudId = 1;
    component.estadoSolicitud = 'borrador';
    component.incorporarAPU();
    expect(component.errorMessage).toContain('firma legal');
  });
});
