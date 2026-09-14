import { bootstrapApplication } from '@angular/platform-browser';
import { appConfig } from './app/app.config';
import { App } from './app/app';

const host = window.location.hostname;
if (host === 'monitoritcd.web.app') {
  const dest =
    'https://monitoritcd.firebaseapp.com' +
    window.location.pathname +
    window.location.search +
    window.location.hash;
  window.location.replace(dest);
} else {
  bootstrapApplication(App, appConfig).catch((err) => console.error(err));
}
