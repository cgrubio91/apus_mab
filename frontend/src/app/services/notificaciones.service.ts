import { Injectable, inject, NgZone, OnDestroy } from '@angular/core';
import { BehaviorSubject, Subscription } from 'rxjs';
import { ApuService, Notificacion } from './apu';
import { AuthService } from './auth.service';

const POLL_INTERVAL_MS = 60_000;

/**
 * Servicio de notificaciones web: consulta periódicamente el backend y expone
 * la lista y el conteo de no leídas. Además dispara notificaciones del
 * navegador cuando llegan notificaciones nuevas.
 */
@Injectable({ providedIn: 'root' })
export class NotificacionesService implements OnDestroy {
  private apu = inject(ApuService);
  private auth = inject(AuthService);
  private zone = inject(NgZone);

  private timer: any = null;
  private authSub: Subscription;
  private conocidas = new Set<number>();
  private primeraCarga = true;

  notificaciones$ = new BehaviorSubject<Notificacion[]>([]);
  noLeidas$ = new BehaviorSubject<number>(0);

  constructor() {
    this.authSub = this.auth.isAuthenticated$.subscribe((logged) => {
      if (logged) {
        this.start();
      } else {
        this.stop();
      }
    });
  }

  ngOnDestroy(): void {
    this.stop();
    this.authSub.unsubscribe();
  }

  start(): void {
    if (this.timer) return;
    this.refresh();
    // El polling corre fuera de la zona de Angular para no disparar detección
    // de cambios cada minuto; solo se re-entra cuando llega la respuesta.
    this.zone.runOutsideAngular(() => {
      this.timer = setInterval(() => this.refresh(), POLL_INTERVAL_MS);
    });
  }

  stop(): void {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
    this.primeraCarga = true;
    this.conocidas.clear();
    this.notificaciones$.next([]);
    this.noLeidas$.next(0);
  }

  refresh(): void {
    if (!this.auth.isLoggedIn()) return;
    this.apu.getNotificaciones().subscribe({
      next: (res) => {
        this.zone.run(() => {
          const lista = res.notificaciones || [];
          this.notificarNuevas(lista);
          this.notificaciones$.next(lista);
          this.noLeidas$.next(res.no_leidas || 0);
        });
      },
      error: () => { /* silencioso: el polling reintenta en el siguiente ciclo */ },
    });
  }

  marcarLeida(n: Notificacion): void {
    if (n.leida) return;
    n.leida = true;
    this.noLeidas$.next(Math.max(0, this.noLeidas$.value - 1));
    this.apu.marcarNotificacionLeida(n.id).subscribe({ error: () => this.refresh() });
  }

  marcarTodas(): void {
    const lista = this.notificaciones$.value.map((n) => ({ ...n, leida: true }));
    this.notificaciones$.next(lista);
    this.noLeidas$.next(0);
    this.apu.marcarTodasLeidas().subscribe({ error: () => this.refresh() });
  }

  solicitarPermisoNavegador(): void {
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission();
    }
  }

  private notificarNuevas(lista: Notificacion[]): void {
    const nuevas = lista.filter((n) => !n.leida && !this.conocidas.has(n.id));
    lista.forEach((n) => this.conocidas.add(n.id));
    // En la primera carga no se muestran popups (serían notificaciones viejas).
    if (this.primeraCarga) {
      this.primeraCarga = false;
      return;
    }
    if (!('Notification' in window) || Notification.permission !== 'granted') return;
    for (const n of nuevas.slice(0, 3)) {
      try {
        new Notification(n.titulo, { body: n.mensaje, icon: '/favicon.ico', tag: `mapus-${n.id}` });
      } catch { /* algunos navegadores restringen Notification fuera de service workers */ }
    }
  }
}
