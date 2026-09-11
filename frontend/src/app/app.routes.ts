import { Routes } from '@angular/router';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { AuthGuard } from './services/auth.guard';
import { AuthService } from './services/auth.service';

const adminGuard = () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  if (auth.isLoggedIn() && (auth.getCurrentUser()?.rol || '').toLowerCase() === 'admin') {
    return true;
  }
  return router.parseUrl(auth.isLoggedIn() ? '/dashboard-apus' : '/login');
};

// H14: lazy loading con loadComponent — cada página se carga bajo demanda
// en lugar de inflar el bundle inicial (antes 681 KB).
export const routes: Routes = [
  { path: '', redirectTo: '/dashboard-apus', pathMatch: 'full' },
  {
    path: 'login',
    loadComponent: () => import('./pages/login/login').then(m => m.Login),
  },
  {
    path: 'dashboard-apus',
    loadComponent: () => import('./pages/dashboard-apus/dashboard-apus').then(m => m.DashboardApus),
    canActivate: [AuthGuard],
  },
  // H13: el flujo legacy "Nuevos APU IA" se retiró (ver plan.md); se conserva
  // solo la redirección para no romper marcadores antiguos.
  { path: 'nuevos-apu-ia', redirectTo: 'constructor-apu', pathMatch: 'full' },
  {
    path: 'consulta-apus',
    loadComponent: () => import('./pages/consulta-apus/consulta-apus').then(m => m.ConsultaApus),
    canActivate: [AuthGuard],
  },
  {
    path: 'chat-apus',
    loadComponent: () => import('./pages/chat-apus/chat-apus').then(m => m.ChatApus),
    canActivate: [AuthGuard],
  },
  {
    path: 'analisis-apu',
    loadComponent: () => import('./pages/analisis-apu/analisis-apu').then(m => m.AnalisisApu),
    canActivate: [AuthGuard],
  },
  {
    path: 'constructor-apu',
    loadComponent: () => import('./pages/constructor-apu/constructor-apu').then(m => m.ConstructorApu),
    canActivate: [AuthGuard],
  },
  {
    path: 'historico-precios',
    loadComponent: () => import('./pages/historico-precios/historico-precios').then(m => m.HistoricoPrecios),
    canActivate: [AuthGuard],
  },
  {
    path: 'proyectos-mapus',
    loadComponent: () => import('./pages/proyectos-mapus/proyectos-mapus').then(m => m.ProyectosMapus),
    canActivate: [AuthGuard],
  },
  {
    path: 'proyectos-mapus/:id',
    loadComponent: () => import('./pages/proyecto-detalle/proyecto-detalle').then(m => m.ProyectoDetalle),
    canActivate: [AuthGuard],
  },
  {
    path: 'usuarios',
    loadComponent: () => import('./pages/usuarios/usuarios').then(m => m.Usuarios),
    canActivate: [AuthGuard, adminGuard],
  },
  // Ruta catch-all: una URL inválida vuelve al dashboard (o al login vía AuthGuard).
  { path: '**', redirectTo: '/dashboard-apus' },
];
