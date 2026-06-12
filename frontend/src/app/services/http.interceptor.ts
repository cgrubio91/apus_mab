import { Injectable } from '@angular/core';
import {
  HttpInterceptor,
  HttpRequest,
  HttpHandler,
  HttpEvent,
} from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { timeout, catchError } from 'rxjs/operators';

@Injectable()
export class ExtendedTimeoutInterceptor implements HttpInterceptor {
  intercept(
    request: HttpRequest<any>,
    next: HttpHandler
  ): Observable<HttpEvent<any>> {
    // Timeout de 2 horas para operaciones de extracción de archivos
    // (70+ minutos observados)
    const timeoutMs = request.url.includes('/extract-file') || request.url.includes('/extract-file-async')
      ? 2 * 60 * 60 * 1000  // 2 horas
      : 30 * 1000; // 30 segundos para otras solicitudes

    return next.handle(request).pipe(
      timeout(timeoutMs),
      catchError((err) => {
        console.error('HTTP Request Timeout or Error:', err);
        return throwError(() => err);
      })
    );
  }
}
