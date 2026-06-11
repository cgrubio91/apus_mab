import { ComponentFixture, TestBed } from '@angular/core/testing';
import { AnalisisApu } from './analisis-apu';
import { provideHttpClient } from '@angular/common/http';
import { provideRouter } from '@angular/router';

describe('AnalisisApu', () => {
  let component: AnalisisApu;
  let fixture: ComponentFixture<AnalisisApu>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AnalisisApu],
      providers: [
        provideHttpClient(),
        provideRouter([]),
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(AnalisisApu);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
