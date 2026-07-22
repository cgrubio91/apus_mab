import { Component, inject, Input, Output, EventEmitter, HostListener, OnInit, OnDestroy } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, NavigationEnd } from '@angular/router';
import { CommonModule } from '@angular/common';
import { AuthService } from '../../services/auth.service';
import { NotificacionesService } from '../../services/notificaciones.service';
import { Notificacion } from '../../services/apu';
import { filter, Subscription } from 'rxjs';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [RouterLink, RouterLinkActive, CommonModule],
  templateUrl: './sidebar.html',
  styleUrl: './sidebar.scss',
})
export class Sidebar implements OnInit, OnDestroy {
  auth = inject(AuthService);
  notif = inject(NotificacionesService);
  private router = inject(Router);

  @Input() isMobileOpen = false;
  @Output() closeMobileEvent = new EventEmitter<void>();

  isCollapsed = false;
  apuExpanded = true;
  showNotifPanel = false;
  private routerSub?: Subscription;

  ngOnInit() {
    this.routerSub = this.router.events
      .pipe(filter(e => e instanceof NavigationEnd))
      .subscribe(() => {
        if (this.isMobileOpen) {
          this.closeMobileEvent.emit();
          document.body.style.overflow = '';
        }
      });
  }

  ngOnDestroy() {
    this.routerSub?.unsubscribe();
  }

  get currentUser() {
    return this.auth.getCurrentUser();
  }

  get isLoggedIn() {
    return this.auth.isLoggedIn();
  }

  get isAdmin() {
    return (this.currentUser?.rol || '').toLowerCase() === 'admin';
  }

  get iniciales(): string {
    const nombre = (this.currentUser?.nombre || '').trim();
    if (!nombre) return '?';
    const partes = nombre.split(/\s+/);
    const primera = partes[0]?.charAt(0) ?? '';
    const segunda = partes.length > 1 ? partes[partes.length - 1].charAt(0) : '';
    return (primera + segunda).toUpperCase() || '?';
  }

  @HostListener('document:click', ['$event'])
  onDocClick(event: MouseEvent) {
    const target = event.target as HTMLElement;
    if (!target.closest('.notif-item') && !target.closest('.notif-panel')) {
      this.showNotifPanel = false;
    }
  }

  closeMobile() {
    this.closeMobileEvent.emit();
    document.body.style.overflow = '';
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
