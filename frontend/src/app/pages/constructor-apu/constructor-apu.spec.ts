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
});
