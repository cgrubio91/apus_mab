import { Injectable, inject } from '@angular/core';
import { Router } from '@angular/router';
import {
  HttpBackend,
  HttpClient,
  HttpInterceptor,
  HttpRequest,
  HttpHandler,
  HttpEvent,
  HttpErrorResponse,
} from '@angular/common/http';
import { Observable, throwError, from } from 'rxjs';
import { timeout, catchError, switchMap } from 'rxjs/operators';
import { clearStoredSession, getStoredToken, TOKEN_KEY, REFRESH_KEY } from './auth.storage';
import { environment } from '../../environments/environment';

@Injectable()
export class ExtendedTimeoutInterceptor implements HttpInterceptor {
  private router = inject(Router);
  private backend = inject(HttpBackend);

  // Promesa compartida: si varias peticiones fallan a la vez, solo se refresca una vez.
  private refreshEnCurso: Promise<string | null> | null = null;

  intercept(
    request: HttpRequest<any>,
    next: HttpHandler,
  ): Observable<HttpEvent<any>> {
    const token = getStoredToken();
    let req = request;

    if (token) {
      req = request.clone({
        setHeaders: { Authorization: `Bearer ${token}` },
      });
    }

    const isAiOrLongTask =
      req.url.includes('/extract-file') ||
      req.url.includes('/extract-file-async') ||
      req.url.includes('/constructor-apu') ||
      req.url.includes('/analisis-apu') ||
      req.url.includes('/chat-assistant');

    const timeoutMs = isAiOrLongTask
      ? 180 * 1000 // 3 minutos para operaciones con IA / scraping / análisis
      : 30 * 1000;

    return next.handle(req).pipe(
      timeout(timeoutMs),
      catchError((err: HttpErrorResponse) => {
        const esAuth = req.url.includes('/auth/');
        const yaReintentado = req.headers.has('X-Refrescado');
        if (err.status === 401 && token && !esAuth && !yaReintentado) {
          // El access expiró: se intenta renovar una vez con el refresh token.
          return from(this.refrescarToken()).pipe(
            switchMap(nuevo => {
              if (!nuevo) {
                this.salir();
                return throwError(() => err);
              }
              const reintentado = req.clone({
                setHeaders: { Authorization: `Bearer ${nuevo}`, 'X-Refrescado': '1' },
              });
              return next.handle(reintentado);
            }),
            catchError(() => {
              this.salir();
              return throwError(() => err);
            }),
          );
        }
        if (err.status === 401 && token) {
          this.salir();
        }
        return throwError(() => err);
      }),
    );
  }

  private refrescarToken(): Promise<string | null> {
    if (!this.refreshEnCurso) {
      this.refreshEnCurso = new Promise(resolve => {
        const rt = localStorage.getItem(REFRESH_KEY);
        if (!rt) {
          this.refreshEnCurso = null;
          resolve(null);
          return;
        }
        // HttpBackend directo: evita pasar por los interceptores (sin ciclos).
        new HttpClient(this.backend)
          .post<any>(`${environment.apiUrl}/auth/refresh`, { refresh_token: rt })
          .subscribe({
            next: res => {
              localStorage.setItem(TOKEN_KEY, res.access_token);
              if (res.refresh_token) localStorage.setItem(REFRESH_KEY, res.refresh_token);
              this.refreshEnCurso = null;
              resolve(res.access_token as string);
            },
            error: () => {
              this.refreshEnCurso = null;
              resolve(null);
            },
          });
      });
    }
    return this.refreshEnCurso;
  }

  private salir(): void {
    clearStoredSession();
    this.router.navigate(['/login']);
  }
}
