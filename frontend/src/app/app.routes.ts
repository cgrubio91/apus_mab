import { Routes } from '@angular/router';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { DashboardApus } from './pages/dashboard-apus/dashboard-apus';
import { ConsultaApus } from './pages/consulta-apus/consulta-apus';
import { NuevosApuIa } from './pages/nuevos-apu-ia/nuevos-apu-ia';
import { ChatApus } from './pages/chat-apus/chat-apus';
import { AnalisisApu } from './pages/analisis-apu/analisis-apu';
import { HistoricoPrecios } from './pages/historico-precios/historico-precios';
import { Usuarios } from './pages/usuarios/usuarios';
import { Login } from './pages/login/login';
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

export const routes: Routes = [
  { path: '', redirectTo: '/dashboard-apus', pathMatch: 'full' },
  { path: 'login', component: Login },
  { path: 'dashboard-apus', component: DashboardApus, canActivate: [AuthGuard] },
  { path: 'nuevos-apu-ia', component: NuevosApuIa, canActivate: [AuthGuard] },
  { path: 'consulta-apus', component: ConsultaApus, canActivate: [AuthGuard] },
  { path: 'chat-apus', component: ChatApus, canActivate: [AuthGuard] },
  { path: 'analisis-apu', component: AnalisisApu, canActivate: [AuthGuard] },
  { path: 'historico-precios', component: HistoricoPrecios, canActivate: [AuthGuard] },
  { path: 'usuarios', component: Usuarios, canActivate: [AuthGuard, adminGuard] },
];
