import { Routes } from '@angular/router';
import { devRoutes } from './dev/dev.routes';
import { TalkPage } from './talk/talk-page';

export const routes: Routes = [
  { path: '', component: TalkPage, title: 'Companion' },
  {
    path: 'plans',
    title: 'Plans',
    loadComponent: () => import('./plans/plans-page').then((m) => m.PlansPage),
  },
  {
    path: 'memories',
    title: 'Memories',
    loadComponent: () => import('./memories/memories-page').then((m) => m.MemoriesPage),
  },
  ...devRoutes,
  { path: '**', redirectTo: '' },
];
