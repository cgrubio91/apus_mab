import { vi } from 'vitest';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ConstructorApu } from './constructor-apu';
import { provideHttpClient } from '@angular/common/http';
import { provideRouter } from '@angular/router';
import { ApuService } from '../../services/apu';

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
      { incluir: true, tipo_insumo: 'Materiales', descripcion: 'Cemento', unidad: 'kg', rendimiento: 2, precio: 1000, fuente: '', fuente_link: '' },
      { incluir: false, tipo_insumo: 'Equipos', descripcion: 'Mixer', unidad: 'h', rendimiento: 1, precio: 99999, fuente: '', fuente_link: '' },
      { incluir: true, tipo_insumo: 'Materiales', descripcion: 'Arena', unidad: 'm3', rendimiento: 1, precio: null, fuente: '', fuente_link: '' },
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

  it('mapea sugerencias de proveedores al cargar la propuesta IA', () => {
    const proveedores = [{ nombre: 'INVERSIONES TJ', municipio: 'Bogotá', telefono: '3143941329' }];
    (component as any)._cargarPropuesta({
      propuesta: {
        insumos: [
          { tipo_insumo: 'Materiales', descripcion: 'Bordillo A80', unidad: 'UN', rendimiento: 1,
            precio: null, fuente: 'Pendiente cotización · Sugeridos: BORDILLOS Y LOSETAS',
            grupo_proveedores: 'BORDILLOS Y LOSETAS', proveedores_sugeridos: proveedores },
        ],
      },
    });
    expect(component.filas.length).toBe(1);
    expect(component.filas[0].grupoProveedores).toBe('BORDILLOS Y LOSETAS');
    expect(component.filas[0].proveedoresSugeridos).toEqual(proveedores);
  });

  it('normaliza proveedores_sugeridos que llega como string JSON desde la BD', () => {
    const insumoBruto = {
      id: 7, insumo_descripcion: 'Bordillo A80', insumo_unidad: 'UN', rendimiento_insumo: 1,
      precio_banco: null, fuente_precio: 'Pendiente cotización',
      grupo_proveedores: 'BORDILLOS Y LOSETAS',
      proveedores_sugeridos: '[{"nombre":"INVERSIONES TJ","municipio":"Bogotá"}]',
    };
    (component as any)._aplicarDetalleSolicitud({ insumos: [insumoBruto] });
    expect(component.insumosBorrador[0].proveedores_sugeridos[0].nombre).toBe('INVERSIONES TJ');
    expect(component.insumosBorrador[0].proveedores_sugeridos[0].municipio).toBe('Bogotá');
  });

  it('enviar estructura incluye grupo_proveedores y proveedores_sugeridos por fila', () => {
    const servicio = TestBed.inject(ApuService);
    const spy = vi.spyOn(servicio, 'aplicarEstructura').mockReturnValue({
      subscribe: (observer: any) => {
        observer.next?.({});
        return { unsubscribe() {} };
      },
    } as any);
    vi.spyOn(component as any, 'cargarBorrador').mockImplementation((cb?: () => void) => cb?.());
    (component as any).solicitudId = 3;
    (component as any).propuesta = { insumos: [] };
    component.filas = [
      { incluir: true, tipo_insumo: 'Materiales', descripcion: 'Bordillo A80', unidad: 'UN',
        rendimiento: 1, precio: null, fuente: 'Pendiente cotización', fuente_link: '',
        grupoProveedores: 'BORDILLOS Y LOSETAS',
        proveedoresSugeridos: [{ nombre: 'INVERSIONES TJ' }] },
    ];
    (component as any).aplicarEstructura();
    const cuerpo = spy.mock.calls[0][1];
    expect(cuerpo.insumos[0].grupo_proveedores).toBe('BORDILLOS Y LOSETAS');
    expect(cuerpo.insumos[0].proveedores_sugeridos).toEqual([{ nombre: 'INVERSIONES TJ' }]);
    expect(cuerpo.insumos[0].proveedores_sugeridos.length).toBeGreaterThan(0);
  });

  it('enlaceWeb convierte contactos sin protocolo en mailto', () => {
    expect(component.enlaceWeb('ventas@easy.co')).toBe('mailto:ventas@easy.co');
    expect(component.enlaceWeb('https://www.easy.co')).toBe('https://www.easy.co');
    expect(component.enlaceWeb('')).toBe('');
  });
});
