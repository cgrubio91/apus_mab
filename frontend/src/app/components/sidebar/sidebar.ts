import { Component, inject } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { CommonModule } from '@angular/common';
import { AuthService } from '../../services/auth.service';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [RouterLink, RouterLinkActive, CommonModule],
  templateUrl: './sidebar.html',
  styleUrl: './sidebar.scss',
})
export class Sidebar {
  auth = inject(AuthService);
  isCollapsed = false;
  apuExpanded = true;

  get currentUser() {
    return this.auth.getCurrentUser();
  }

  get isLoggedIn() {
    return this.auth.isLoggedIn();
  }

  logout(): void {
    this.auth.logout();
  }
}

export default Sidebar;