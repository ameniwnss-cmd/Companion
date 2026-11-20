import { DatePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { MenuPage } from '../layout/menu-page';
import { Button } from '../ui/button';
import { Empty } from '../ui/empty';
import { Filter, FilterOption } from '../ui/filter';
import { Icon } from '../ui/icon';
import { MemoriesService } from './memories.service';
import { MEMORY_KINDS, MEMORY_KIND_INFO, Memory, MemoryKind } from './memory';

type KindFilter = MemoryKind | 'all';

@Component({
  selector: 'app-memories-page',
  imports: [DatePipe, MenuPage, Button, Empty, Filter, Icon],
  templateUrl: './memories-page.html',
  styleUrl: './memories-page.scss',
  providers: [MemoriesService],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MemoriesPage implements OnInit {
  protected readonly store = inject(MemoriesService);
  protected readonly info = MEMORY_KIND_INFO;
  protected readonly kind = signal<KindFilter>('all');
  protected readonly editingId = signal<string | null>(null);
  protected readonly draft = signal('');

  protected readonly filters = computed<FilterOption<KindFilter>[]>(() => [
    { value: 'all', label: 'Everything' },
    ...MEMORY_KINDS.filter((k) => this.store.byKind().has(k.kind)).map((k) => ({
      value: k.kind,
      label: k.label,
    })),
  ]);
  protected readonly shown = computed(() => {
    const kind = this.kind();
    return this.store.memories().filter((m) => kind === 'all' || m.kind === kind);
  });

  ngOnInit(): void {
    void this.store.load();
  }

  protected edit(memory: Memory): void {
    this.editingId.set(memory.id);
    this.draft.set(memory.content);
  }

  protected async save(memory: Memory): Promise<void> {
    const content = this.draft().trim();
    if (content && content !== memory.content) {
      await this.store.update(memory.id, { content });
    }
    this.editingId.set(null);
  }

  protected async forgetEverything(): Promise<void> {
    if (window.confirm('Forget everything your companion remembers about you?')) {
      await this.store.forgetEverything();
      this.kind.set('all');
    }
  }
}
