import { Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Orb, OrbState } from './orb';

@Component({
  imports: [Orb],
  template: `<app-orb [state]="state()" [level]="level" />`,
})
class Host {
  readonly state = signal<OrbState>('idle');
  loudness = 0;
  readonly level = (): number => this.loudness;
}

describe('Orb', () => {
  async function render() {
    const fixture = TestBed.createComponent(Host);
    await fixture.whenStable();
    const orb = (fixture.nativeElement as HTMLElement).querySelector('app-orb') as HTMLElement;
    return { fixture, orb };
  }

  it('exposes its state for styling and hides itself from screen readers', async () => {
    const { fixture, orb } = await render();

    expect(orb.dataset['state']).toBe('idle');
    expect(orb.getAttribute('aria-hidden')).toBe('true');

    fixture.componentInstance.state.set('thinking');
    await fixture.whenStable();
    expect(orb.dataset['state']).toBe('thinking');
  });

  it('shows sound bars only while listening', async () => {
    const { fixture, orb } = await render();
    expect(orb.querySelector('.bars')).toBeNull();

    fixture.componentInstance.state.set('listening');
    await fixture.whenStable();
    expect(orb.querySelectorAll('.bars i')).toHaveLength(5);
  });

  it('follows the voice level through a CSS variable', async () => {
    const { fixture, orb } = await render();
    fixture.componentInstance.loudness = 5;

    await new Promise((resolve) => setTimeout(resolve, 100));

    const level = Number(orb.style.getPropertyValue('--level'));
    expect(level).toBeGreaterThan(0);
    expect(level).toBeLessThanOrEqual(1);
  });
});
