import { Component, inject, OnInit } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Router } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { catchError, of } from 'rxjs';

declare var google: any;

@Component({
  selector: 'app-login',
  imports: [MatCardModule, MatButtonModule],
  templateUrl: './login.html',
  styleUrl: './login.scss',
})
export class Login implements OnInit {
  private http = inject(HttpClient);
  private router = inject(Router);
  hmlLocal = false;

  ngOnInit() {
    this.http.get<{email?: string, client_id?: string}>('/api/me').pipe(
      catchError((err: HttpErrorResponse) => {
        return of(err.error || {});
      })
    ).subscribe((res: any) => {
      const host = location.hostname;
      this.hmlLocal =
        Boolean(res.hml_local) || host === '127.0.0.1' || host === 'localhost';
      if (res.email) {
        this.router.navigate(['/fontes']);
      } else if (res.client_id) {
        this.initGoogleAuth(res.client_id);
      }
    });
  }

  private initGoogleAuth(clientId: string) {
    const script = document.createElement('script');
    script.src = 'https://accounts.google.com/gsi/client';
    script.async = true;
    script.defer = true;
    script.onload = () => {
      google.accounts.id.initialize({
        client_id: clientId,
        callback: this.handleCredentialResponse.bind(this)
      });
      google.accounts.id.renderButton(
        document.getElementById('google-btn'),
        { theme: 'outline', size: 'large' }
      );
    };
    document.body.appendChild(script);
  }

  entrarHml() {
    this.http.post('/api/auth/hml', {}, { withCredentials: true }).subscribe({
      next: () => this.router.navigate(['/fontes']),
      error: () => alert('Login HML recusado (só 127.0.0.1 e ENV≠production).'),
    });
  }

  handleCredentialResponse(response: any) {
    this.http.post('/api/auth/google', { id_token: response.credential }, { withCredentials: true })
      .subscribe({
        next: () => {
          this.router.navigate(['/fontes']);
        },
        error: (err) => {
          console.error('Erro de login', err);
          alert('Acesso negado. Verifique as permissões da conta.');
        }
      });
  }
}
