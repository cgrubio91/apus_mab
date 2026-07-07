import { Injectable, inject } from '@angular/core';
import { Router } from '@angular/router';
import {
  HttpInterceptor,
  HttpRequest,
  HttpHandler,
  HttpEvent,
  HttpErrorResponse,
} from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { timeout, catchError } from 'rxjs/operators';
import { clearStoredSession, getStoredToken } from './auth.storage';

@Injectable()
export class ExtendedTimeoutInterceptor implements HttpInterceptor {
  private router = inject(Router);

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

    const timeoutMs =
      req.url.includes('/extract-file') || req.url.includes('/extract-file-async')
        ? 2 * 60 * 60 * 1000
        : 30 * 1000;

    return next.handle(req).pipe(
      timeout(timeoutMs),
      catchError((err: HttpErrorResponse) => {
        if (err.status === 401 && token) {
          clearStoredSession();
          this.router.navigate(['/login']);
        }
        return throwError(() => err);
      }),
    );
  }
}
