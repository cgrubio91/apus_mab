import { ComponentFixture, TestBed } from '@angular/core/testing';

import { NuevosApuIa } from './nuevos-apu-ia';

describe('NuevosApuIa', () => {
  let component: NuevosApuIa;
  let fixture: ComponentFixture<NuevosApuIa>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [NuevosApuIa]
    })
    .compileComponents();

    fixture = TestBed.createComponent(NuevosApuIa);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
