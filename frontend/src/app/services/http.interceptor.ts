import { Injectable } from '@angular/core';
import {
  HttpInterceptor,
  HttpRequest,
  HttpHandler,
  HttpEvent,
  HttpErrorResponse,
} from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { timeout, catchError } from 'rxjs/operators';

@Injectable()
export class ExtendedTimeoutInterceptor implements HttpInterceptor {
  intercept(
    request: HttpRequest<any>,
    next: HttpHandler,
  ): Observable<HttpEvent<any>> {
    const token = localStorage.getItem('mapus_token');
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
          localStorage.removeItem('mapus_token');
          localStorage.removeItem('mapus_user');
          window.location.href = '/login';
        }
        return throwError(() => err);
      }),
    );
  }
}
