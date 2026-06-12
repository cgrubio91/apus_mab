import { ComponentFixture, TestBed } from '@angular/core/testing';

import { DashboardApus } from './dashboard-apus';

describe('DashboardApus', () => {
  let component: DashboardApus;
  let fixture: ComponentFixture<DashboardApus>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [DashboardApus]
    })
    .compileComponents();

    fixture = TestBed.createComponent(DashboardApus);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
