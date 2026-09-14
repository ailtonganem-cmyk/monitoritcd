import { Component, inject } from '@angular/core';
import { Router, RouterOutlet, RouterLink, NavigationEnd } from '@angular/router';
import { HttpClient } from '@angular/common/http';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatButtonModule } from '@angular/material/button';
import { CommonModule } from '@angular/common';
import { filter } from 'rxjs/operators';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, MatToolbarModule, MatButtonModule, CommonModule],
  templateUrl: './app.html',
  styleUrl: './app.scss'
})
export class App {
  router = inject(Router);
  http = inject(HttpClient);
  isLogin = true;

  constructor() {
    this.router.events.pipe(
      filter((e): e is NavigationEnd => e instanceof NavigationEnd)
    ).subscribe(e => {
      this.isLogin = e.urlAfterRedirects.split('?')[0] === '/';
    });
  }

  logout() {
    this.http.post('/api/auth/sair', {}).subscribe(() => {
      this.router.navigate(['/']);
    });
  }
}
