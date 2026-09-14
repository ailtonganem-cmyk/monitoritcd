import { Component, inject, OnInit } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Router } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { catchError, of } from 'rxjs';

@Component({
  selector: 'app-login',
  imports: [MatButtonModule],
  templateUrl: './login.html',
  styleUrl: './login.scss',
})
export class Login implements OnInit {
  private http = inject(HttpClient);
  private router = inject(Router);
  hmlLocal = false;
  googleEmCurso = false;

  ngOnInit() {
    void this.completarRedirectGoogle();
    this.http.get<{email?: string, client_id?: string}>('/api/me').pipe(
      catchError((err: HttpErrorResponse) => {
        const raw = err.error;
        if (raw && typeof raw === 'object') {
          return of(raw);
        }
        if (typeof raw === 'string') {
          try {
            return of(JSON.parse(raw));
          } catch {
            return of({});
          }
        }
        return of({});
      })
    ).subscribe((res: any) => {
      const host = location.hostname;
      this.hmlLocal =
        Boolean(res.hml_local) || host === '127.0.0.1' || host === 'localhost';
      if (res.email) {
        this.router.navigate(['/fontes']);
      }
    });
  }

  entrarHml() {
    this.http.post('/api/auth/hml', {}, { withCredentials: true }).subscribe({
      next: () => this.router.navigate(['/fontes']),
      error: () => alert('Login HML recusado (só 127.0.0.1 e ENV≠production).'),
    });
  }

  async entrarGoogle() {
    if (this.googleEmCurso) {
      return;
    }
    this.googleEmCurso = true;
    try {
      const fb = await this.firebaseAuth();
      const provider = new fb.GoogleAuthProvider();
      provider.addScope('email');
      provider.addScope('profile');
      const result = await fb.signInWithPopup(fb.auth, provider);
      const cred = fb.GoogleAuthProvider.credentialFromResult(result);
      const googleTok = cred?.idToken;
      const fbTok = await result.user.getIdToken();
      this.enviarIdToken(googleTok || fbTok);
    } catch (err) {
      const code = (err as {code?: string}).code || '';
      if (code !== 'auth/popup-closed-by-user' && code !== 'auth/cancelled-popup-request') {
        alert(
          code === 'auth/popup-blocked'
            ? 'O navegador bloqueou a janela do Google. Permita pop-ups neste site.'
            : 'Login Google cancelado ou recusado.',
        );
      }
    } finally {
      this.googleEmCurso = false;
    }
  }

  private async completarRedirectGoogle() {
    try {
      const fb = await this.firebaseAuth();
      const result = await fb.getRedirectResult(fb.auth);
      if (!result) {
        return;
      }
      const cred = fb.GoogleAuthProvider.credentialFromResult(result);
      const googleTok = cred?.idToken;
      const fbTok = await result.user.getIdToken();
      this.enviarIdToken(googleTok || fbTok);
    } catch {
      /* sem redirect em andamento */
    }
  }

  private async firebaseAuth() {
    const cfgResp = await fetch('/__/firebase/init.json');
    if (!cfgResp.ok) {
      throw new Error('firebase-init');
    }
    const cfg = await cfgResp.json();
    const { initializeApp, getApps } = await import('firebase/app');
    const { getAuth, GoogleAuthProvider, signInWithPopup, getRedirectResult } =
      await import('firebase/auth');
    const app = getApps()[0] ?? initializeApp(cfg);
    return {
      auth: getAuth(app),
      GoogleAuthProvider,
      signInWithPopup,
      getRedirectResult,
    };
  }

  private enviarIdToken(idToken: string) {
    this.http.post('/api/auth/google', { id_token: idToken }, { withCredentials: true })
      .subscribe({
        next: () => this.router.navigate(['/fontes']),
        error: () => alert('Acesso negado. Só ailtonganem@gmail.com.'),
      });
  }
}
