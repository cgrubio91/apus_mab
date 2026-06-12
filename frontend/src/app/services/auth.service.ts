import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { Observable, BehaviorSubject, throwError } from 'rxjs';
import { tap, catchError } from 'rxjs/operators';
import { environment } from '../../environments/environment';

export interface AuthUser {
  id: number;
  nombre: string;
  rol: string;
  telefono: string;
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private http = inject(HttpClient);
  private router = inject(Router);

  private readonly TOKEN_KEY = 'mapus_token';
  private readonly USER_KEY = 'mapus_user';

  private isAuthenticatedSubject = new BehaviorSubject<boolean>(this._hasToken());
  isAuthenticated$ = this.isAuthenticatedSubject.asObservable();

  private currentUserSubject = new BehaviorSubject<AuthUser | null>(this._getStoredUser());
  currentUser$ = this.currentUserSubject.asObservable();

  getToken(): string | null {
    return localStorage.getItem(this.TOKEN_KEY);
  }

  getCurrentUser(): AuthUser | null {
    return this.currentUserSubject.value;
  }

  isLoggedIn(): boolean {
    return !!this.getToken();
  }

  login(telefono: string, password: string): Observable<any> {
    return this.http.post(`${environment.apiUrl}/auth/login`, { telefono, password }).pipe(
      tap((res: any) => {
        localStorage.setItem(this.TOKEN_KEY, res.access_token);
        localStorage.setItem(this.USER_KEY, JSON.stringify(res.user));
        this.isAuthenticatedSubject.next(true);
        this.currentUserSubject.next(res.user);
      }),
      catchError(err => {
        this.isAuthenticatedSubject.next(false);
        return throwError(() => err);
      }),
    );
  }

  logout(): void {
    localStorage.removeItem(this.TOKEN_KEY);
    localStorage.removeItem(this.USER_KEY);
    this.isAuthenticatedSubject.next(false);
    this.currentUserSubject.next(null);
    this.router.navigate(['/login']);
  }

  private _hasToken(): boolean {
    return !!localStorage.getItem(this.TOKEN_KEY);
  }

  private _getStoredUser(): AuthUser | null {
    try {
      const raw = localStorage.getItem(this.USER_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  }
}
