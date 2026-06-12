import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ChatApus } from './chat-apus';
import { provideHttpClient } from '@angular/common/http';

describe('ChatApus', () => {
  let component: ChatApus;
  let fixture: ComponentFixture<ChatApus>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ChatApus],
      providers: [provideHttpClient()],
    }).compileComponents();

    fixture = TestBed.createComponent(ChatApus);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
