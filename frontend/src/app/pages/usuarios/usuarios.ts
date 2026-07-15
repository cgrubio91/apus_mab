import { Component, OnInit, ChangeDetectorRef, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApuService, UsuarioAdmin } from '../../services/apu';
import { AuthService } from '../../services/auth.service';

const ROLES = ['admin', 'subgerente', 'legal', 'analista', 'contraparte', 'user'];

@Component({
  selector: 'app-usuarios',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './usuarios.html',
  styleUrl: './usuarios.scss',
})
export class Usuarios implements OnInit {
  private apuService = inject(ApuService);
  private auth = inject(AuthService);
  private cdr = inject(ChangeDetectorRef);

  roles = ROLES;
  usuarios: UsuarioAdmin[] = [];
  isLoading = true;
  errorMessage = '';
  successMessage = '';

  showCreateForm = false;
  showRoleInfo = false;
  nuevo = { telefono: '', nombre: '', email: '', password: '', rol: 'user' };
  creando = false;

  roleDescriptions = [
    { rol: 'admin', desc: 'Acceso total: gestiona usuarios, roles, proyectos y toda la configuración del sistema.' },
    { rol: 'subgerente', desc: 'Aprueba APUs en segunda instancia. Supervisa el flujo de aprobación y revisa análisis.' },
    { rol: 'legal', desc: 'Firma legalmente los APUs aprobados. Revisa y da el visto bueno final.' },
    { rol: 'analista', desc: 'Crea y analiza APUs, sube cotizaciones, preaprueba o rechaza solicitudes en primera instancia.' },
    { rol: 'contraparte', desc: 'Visualiza APUs y análisis completos. Consulta el banco de precios e históricos.' },
    { rol: 'user', desc: 'Acceso básico de solo lectura al banco de APUs y chat asistente.' },
  ];

  get currentUserId(): number | undefined {
    return this.auth.getCurrentUser()?.id;
  }

  ngOnInit(): void {
    this.loadUsers();
  }

  loadUsers(): void {
    this.isLoading = true;
    this.errorMessage = '';
    this.apuService.getUsers().subscribe({
      next: (res) => {
        this.usuarios = res.users || [];
        this.isLoading = false;
        this.cdr.markForCheck();
      },
      error: (err) => {
        this.errorMessage = err.status === 403
          ? 'No tienes permisos para gestionar usuarios.'
          : 'No se pudieron cargar los usuarios.';
        this.isLoading = false;
        this.cdr.markForCheck();
      },
    });
  }

  crear(): void {
    if (!this.nuevo.telefono || !this.nuevo.nombre || this.nuevo.password.length < 6) {
      this.errorMessage = 'Completa teléfono, nombre y una contraseña de mínimo 6 caracteres.';
      return;
    }
    if (this.nuevo.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(this.nuevo.email)) {
      this.errorMessage = 'El correo electrónico no es válido.';
      return;
    }
    this.creando = true;
    this.errorMessage = '';
    this.apuService.createUser(this.nuevo).subscribe({
      next: () => {
        this.successMessage = `Usuario ${this.nuevo.nombre} creado.`;
        this.nuevo = { telefono: '', nombre: '', email: '', password: '', rol: 'user' };
        this.showCreateForm = false;
        this.creando = false;
        this.loadUsers();
      },
      error: (err) => {
        this.errorMessage = err.error?.detail || 'No se pudo crear el usuario.';
        this.creando = false;
        this.cdr.markForCheck();
      },
    });
  }

  cambiarRol(u: UsuarioAdmin, rol: string): void {
    const anterior = u.rol;
    u.rol = rol;
    this.apuService.updateUser(u.id, { rol }).subscribe({
      next: () => {
        this.successMessage = `Rol de ${u.nombre} actualizado a ${rol}.`;
        this.cdr.markForCheck();
      },
      error: (err) => {
        u.rol = anterior;
        this.errorMessage = err.error?.detail || 'No se pudo cambiar el rol.';
        this.cdr.markForCheck();
      },
    });
  }

  toggleActivo(u: UsuarioAdmin): void {
    const nuevoEstado = !u.activo;
    this.apuService.updateUser(u.id, { activo: nuevoEstado }).subscribe({
      next: () => {
        u.activo = nuevoEstado;
        this.successMessage = `${u.nombre} ${nuevoEstado ? 'activado' : 'desactivado'}.`;
        this.cdr.markForCheck();
      },
      error: (err) => {
        this.errorMessage = err.error?.detail || 'No se pudo cambiar el estado.';
        this.cdr.markForCheck();
      },
    });
  }

  trackById(_i: number, u: UsuarioAdmin): number {
    return u.id;
  }
}

export default Usuarios;
