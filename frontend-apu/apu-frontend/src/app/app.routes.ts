import { Routes } from '@angular/router';
import { DashboardApus } from './pages/dashboard-apus/dashboard-apus';
import { ConsultaApus } from './pages/consulta-apus/consulta-apus';
import { NuevosApuIa } from './pages/nuevos-apu-ia/nuevos-apu-ia';
import { ChatApus } from './pages/chat-apus/chat-apus';

export const routes: Routes = [
  { path: '', redirectTo: '/dashboard-apus', pathMatch: 'full' },
  { path: 'dashboard-apus', component: DashboardApus },
  { path: 'nuevos-apu-ia', component: NuevosApuIa },
  { path: 'consulta-apus', component: ConsultaApus },
  { path: 'chat-apus', component: ChatApus },
];