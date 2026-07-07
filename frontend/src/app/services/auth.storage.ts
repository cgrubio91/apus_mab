// Claves de almacenamiento de sesión compartidas entre AuthService,
// el interceptor HTTP y las llamadas fetch/EventSource que no pasan
// por HttpClient.
export const TOKEN_KEY = 'mapus_token';
export const USER_KEY = 'mapus_user';

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function clearStoredSession(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

/** Devuelve true si el token JWT almacenado está expirado o es ilegible. */
export function isTokenExpired(token?: string | null): boolean {
  const jwt = token ?? getStoredToken();
  if (!jwt) return true;
  try {
    const payload = JSON.parse(atob(jwt.split('.')[1]));
    if (typeof payload.exp !== 'number') return false;
    return payload.exp * 1000 <= Date.now();
  } catch {
    return true;
  }
}

/** Headers de autorización para llamadas fetch crudas. */
export function authHeaders(): Record<string, string> {
  const token = getStoredToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}
