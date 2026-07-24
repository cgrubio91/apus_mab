import { Component, signal, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterOutlet, Router, NavigationEnd } from '@angular/router';
import { filter } from 'rxjs';
import { Sidebar } from './components/sidebar/sidebar';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, RouterOutlet, Sidebar],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  protected readonly title = signal('apu-frontend');
  protected isMobileOpen = false;
  protected sidebarCollapsed = false;
  // Rutas que se muestran como ventana completa, sin el shell (sidebar/topbar).
  protected isAuthRoute = false;

  private router = inject(Router);

  constructor() {
    this.isAuthRoute = this.router.url.startsWith('/login');
    this.router.events
      .pipe(filter((e) => e instanceof NavigationEnd))
      .subscribe((e) => {
        this.isAuthRoute = (e as NavigationEnd).urlAfterRedirects.startsWith('/login');
      });
  }

  toggleMobileSidebar() {
    this.isMobileOpen = !this.isMobileOpen;
    document.body.style.overflow = this.isMobileOpen ? 'hidden' : '';
  }

  closeMobileSidebar() {
    this.isMobileOpen = false;
    document.body.style.overflow = '';
  }
}
