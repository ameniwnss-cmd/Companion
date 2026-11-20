export type Mode = 'normal' | 'supportive' | 'crisis';
export type ActionKind = 'task' | 'reminder' | 'weekly_plan';
export type ActionStatus = 'pending' | 'confirmed' | 'cancelled' | 'expired' | 'undone';

export interface UserMessageEvent {
  type: 'user_message';
  text: string;
}

export interface ResolveActionEvent {
  type: 'resolve_action';
  id: string;
  confirm: boolean;
}

export interface UndoActionEvent {
  type: 'undo_action';
  id: string;
}

export interface StatusEvent {
  type: 'status';
  state: 'idle' | 'thinking' | 'speaking';
}

export interface UserTranscriptEvent {
  type: 'user_transcript';
  text: string;
}

export interface AssistantMessageEvent {
  type: 'assistant_message';
  text: string;
  mode: Mode;
  teasing_allowed: boolean;
}

export interface PendingItem {
  kind: ActionKind;
  summary: string;
}

export interface PendingActionEvent {
  type: 'pending_action';
  id: string;
  items: PendingItem[];
}

export interface ActionResolvedEvent {
  type: 'action_resolved';
  id: string;
  status: ActionStatus;
}

export interface ReminderDueEvent {
  type: 'reminder_due';
  id: string;
  title: string;
  text: string;
}

export interface ErrorEvent {
  type: 'error';
  detail: string;
}

export interface AudioFrame {
  type: 'audio';
  data: ArrayBuffer;
}

export type ServerEvent =
  | StatusEvent
  | UserTranscriptEvent
  | AssistantMessageEvent
  | PendingActionEvent
  | ActionResolvedEvent
  | ReminderDueEvent
  | ErrorEvent;
export type ClientEvent = UserMessageEvent | ResolveActionEvent | UndoActionEvent;
export type Incoming = ServerEvent | AudioFrame;
export type Outgoing = ClientEvent | Blob;
