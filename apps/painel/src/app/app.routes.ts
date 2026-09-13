import { Routes } from '@angular/router';
import { Login } from './login/login';
import { Fontes } from './fontes/fontes';
import { Parametros } from './parametros/parametros';
import { Coleta } from './coleta/coleta';
import { Ia } from './ia/ia';
import { authGuard } from './auth-guard';

export const routes: Routes = [
  { path: '', component: Login },
  { path: 'fontes', component: Fontes, canActivate: [authGuard] },
  { path: 'parametros', component: Parametros, canActivate: [authGuard] },
  { path: 'coleta', component: Coleta, canActivate: [authGuard] },
  { path: 'ia', component: Ia, canActivate: [authGuard] },
  { path: '**', redirectTo: '' }
];
