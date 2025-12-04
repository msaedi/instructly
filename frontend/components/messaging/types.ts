export interface NormalizedReaction {
  emoji: string;
  count: number;
  isMine: boolean;
}

export interface NormalizedAttachment {
  id: string;
  url: string;
  type: string;
  name?: string;
}

export interface NormalizedMessage {
  id: string;
  content: string;
  timestamp: Date;
  timestampLabel: string;
  isOwn: boolean;
  senderName?: string | undefined;
  isEdited: boolean;
  isDeleted: boolean;
  readStatus?: 'sent' | 'delivered' | 'read' | undefined;
  readTimestampLabel?: string | undefined;
  reactions: NormalizedReaction[];
  currentUserReaction?: string | null | undefined;
  attachments?: NormalizedAttachment[] | undefined;
  _raw?: unknown;
}
