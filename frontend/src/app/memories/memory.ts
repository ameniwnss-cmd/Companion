import { IconName } from '../ui/icon';

export type MemoryKind = 'preference' | 'goal' | 'commitment' | 'habit' | 'recent_context';

export interface Memory {
  id: string;
  kind: MemoryKind;
  content: string;
  created_at: string;
  updated_at: string;
  expires_at: string | null;
}

export interface MemoryChanges {
  kind?: MemoryKind;
  content?: string;
}

export interface MemoryKindInfo {
  kind: MemoryKind;
  label: string;
  tag: string;
  icon: IconName;
}

export const MEMORY_KINDS: readonly MemoryKindInfo[] = [
  { kind: 'goal', label: 'Goals', tag: 'A LITTLE DREAM', icon: 'star' },
  { kind: 'commitment', label: 'Commitments', tag: 'A PROMISE', icon: 'promise' },
  { kind: 'habit', label: 'Habits', tag: 'DAILY RITUAL', icon: 'coffee' },
  { kind: 'preference', label: 'Preferences', tag: 'A PIECE OF YOU', icon: 'heart' },
  { kind: 'recent_context', label: 'This week', tag: 'LATELY', icon: 'clock' },
];

export const MEMORY_KIND_INFO = Object.fromEntries(
  MEMORY_KINDS.map((info) => [info.kind, info]),
) as Record<MemoryKind, MemoryKindInfo>;
