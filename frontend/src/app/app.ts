import { Component, signal } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { Sidebar } from './components/sidebar/sidebar';
import { Topbar } from './components/topbar/topbar';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, Sidebar, Topbar],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  protected readonly title = signal('apu-frontend');
  protected isMobileOpen = false;

  toggleMobileSidebar() {
    this.isMobileOpen = !this.isMobileOpen;
    document.body.style.overflow = this.isMobileOpen ? 'hidden' : '';
  }

  closeMobileSidebar() {
    this.isMobileOpen = false;
    document.body.style.overflow = '';
  }
}