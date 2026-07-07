import { Component, inject } from '@angular/core';
import { Router, RouterLink, RouterLinkActive } from '@angular/router';
import { CommonModule } from '@angular/common';
import { AuthService } from '../../services/auth.service';
import { NotificacionesService } from '../../services/notificaciones.service';
import { Notificacion } from '../../services/apu';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [RouterLink, RouterLinkActive, CommonModule],
  templateUrl: './sidebar.html',
  styleUrl: './sidebar.scss',
})
export class Sidebar {
  auth = inject(AuthService);
  notif = inject(NotificacionesService);
  private router = inject(Router);

  isCollapsed = false;
  apuExpanded = true;
  showNotifPanel = false;

  get currentUser() {
    return this.auth.getCurrentUser();
  }

  get isLoggedIn() {
    return this.auth.isLoggedIn();
  }

  get isAdmin() {
    return (this.currentUser?.rol || '').toLowerCase() === 'admin';
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

  logout(): void {
    this.auth.logout();
  }
}

export default Sidebar;
