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
  nuevo = { telefono: '', nombre: '', password: '', rol: 'user' };
  creando = false;

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
    this.creando = true;
    this.errorMessage = '';
    this.apuService.createUser(this.nuevo).subscribe({
      next: () => {
        this.successMessage = `Usuario ${this.nuevo.nombre} creado.`;
        this.nuevo = { telefono: '', nombre: '', password: '', rol: 'user' };
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
