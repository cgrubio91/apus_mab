import { Component, inject, HostListener } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, NavigationEnd } from '@angular/router';
import { filter } from 'rxjs';
import { AuthService } from '../../services/auth.service';
import { NotificacionesService } from '../../services/notificaciones.service';
import { Notificacion } from '../../services/apu';

@Component({
  selector: 'app-topbar',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './topbar.html',
  styleUrl: './topbar.scss',
})
export class Topbar {
  auth = inject(AuthService);
  notif = inject(NotificacionesService);
  private router = inject(Router);

  showNotifPanel = false;
  seccion = 'WORKSPACE';

  constructor() {
    this.router.events
      .pipe(filter((e) => e instanceof NavigationEnd))
      .subscribe((e) => {
        const url = (e as NavigationEnd).urlAfterRedirects || '';
        this.seccion = url.includes('/usuarios') ? 'ADMINISTRACIÓN' : 'WORKSPACE';
      });
  }

  get isLoggedIn() {
    return this.auth.isLoggedIn();
  }

  @HostListener('document:click', ['$event'])
  onDocClick(event: MouseEvent) {
    const target = event.target as HTMLElement;
    if (!target.closest('.topbar-notif')) {
      this.showNotifPanel = false;
    }
  }

  toggleNotifPanel(): void {
    this.showNotifPanel = !this.showNotifPanel;
    if (this.showNotifPanel) {
      this.notif.solicitarPermisoNavegador();
      this.notif.refresh();
    }
  }

  abrirNotificacion(n: Notificacion): void {
    this.notif.marcarLeida(n);
    this.showNotifPanel = false;
    if (n.solicitud_id) {
      this.router.navigate(['/analisis-apu']);
    }
  }

  marcarTodas(): void {
    this.notif.marcarTodas();
  }

  exportar(): void {
    window.print();
  }
}

export default Topbar;
