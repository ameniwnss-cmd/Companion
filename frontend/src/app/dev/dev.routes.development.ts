import { Routes } from '@angular/router';

export const devRoutes: Routes = [
  {
    path: 'dev',
    title: 'Dev chat',
    loadComponent: () => import('./dev-chat').then((m) => m.DevChat),
  },
];
