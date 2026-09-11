import { ComponentFixture, TestBed } from '@angular/core/testing';

import { provideHttpClient } from '@angular/common/http';
import { provideRouter } from '@angular/router';

import { ConsultaApus } from './consulta-apus';

describe('ConsultaApus', () => {
  let component: ConsultaApus;
  let fixture: ComponentFixture<ConsultaApus>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ConsultaApus],
      providers: [
        provideHttpClient(),
        provideRouter([]),
      ],
    })
    .compileComponents();

    fixture = TestBed.createComponent(ConsultaApus);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
