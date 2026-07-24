import { Component, inject, OnInit, OnDestroy, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from '../../services/auth.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './login.html',
  styleUrl: './login.scss',
})
export class Login implements OnInit, OnDestroy {
  private auth = inject(AuthService);
  private router = inject(Router);
  private cdr = inject(ChangeDetectorRef);

  username = '';
  password = '';
  loading = false;
  error: string | null = null;
  showPassword = false;
  rememberMe = false;

  // Carrusel de fondo del panel izquierdo. Las imágenes se sirven desde public/login/.
  slides = ['login/slide1.webp', 'login/slide2.webp', 'login/slide3.webp', 'login/slide4.webp'];
  current = 0;
  logoOk = true;
  private timer?: ReturnType<typeof setInterval>;

  ngOnInit(): void {
    this.startCarousel();
  }

  ngOnDestroy(): void {
    if (this.timer) clearInterval(this.timer);
  }

  private startCarousel(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = setInterval(() => {
      this.current = (this.current + 1) % this.slides.length;
      this.cdr.detectChanges();
    }, 5500);
  }

  goTo(i: number): void {
    this.current = i;
    this.startCarousel();
  }

  togglePassword(): void {
    this.showPassword = !this.showPassword;
  }

  login(): void {
    if (!this.username || !this.password) {
      this.error = 'Ingrese usuario y contraseña';
      return;
    }

    this.loading = true;
    this.error = null;

    this.auth.login(this.username, this.password).subscribe({
      next: () => {
        this.router.navigate(['/dashboard-apus']);
      },
      error: (err) => {
        this.loading = false;
        this.error = err.error?.detail || 'Error al iniciar sesión';
      },
    });
  }
}
