/**
 * MessageInput - Message composition input area
 *
 * Includes:
 * - Typing indicator display
 * - Attachment list
 * - Text input with keyboard handling
 * - Send button
 */

import { useRef, type KeyboardEvent } from 'react';
import { Plus, Send, X } from 'lucide-react';

export type MessageInputProps = {
  messageText: string;
  pendingAttachments: File[];
  isSendDisabled: boolean;
  typingUserName: string | null;
  messageDisplay: 'inbox' | 'archived' | 'trash';
  hasUpcomingBookings?: boolean;
  onMessageChange: (value: string) => void;
  onKeyPress: (e: KeyboardEvent<HTMLTextAreaElement>) => void;
  onSend: () => void;
  onAttachmentAdd: (files: FileList | null) => void;
  onAttachmentRemove: (index: number) => void;
};

export function MessageInput({
  messageText,
  pendingAttachments,
  isSendDisabled,
  typingUserName,
  messageDisplay,
  hasUpcomingBookings = true,
  onMessageChange,
  onKeyPress,
  onSend,
  onAttachmentAdd,
  onAttachmentRemove,
}: MessageInputProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  if (messageDisplay !== 'inbox') {
    return (
      <div className="p-6 border-t border-gray-200 text-sm text-gray-500">
        {messageDisplay === 'archived'
          ? 'Archived messages are read-only.'
          : 'Trashed messages are read-only.'}
      </div>
    );
  }

  // Show read-only message when there are no upcoming bookings
  if (!hasUpcomingBookings) {
    return (
      <div className="p-6 border-t border-gray-200 text-center text-sm text-gray-500">
        This lesson has ended. Chat is view-only.
      </div>
    );
  }

  return (
    <div className="p-4 border-t border-gray-200 space-y-3">
      {/* Typing indicator */}
      {typingUserName && (
        <div className="px-1 pb-1 text-xs text-gray-500">
          {typingUserName} is typing...
        </div>
      )}

      {/* Pending attachments */}
      {pendingAttachments.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {pendingAttachments.map((file, index) => (
            <span
              key={`${file.name}-${index}`}
              className="inline-flex items-center gap-2 rounded-full bg-purple-50 border border-purple-200 px-3 py-1 text-xs text-[#7E22CE]"
            >
              <span className="max-w-[8rem] truncate" title={file.name}>
                {file.name}
              </span>
              <button
                type="button"
                className="text-[#7E22CE] hover:text-purple-800"
                aria-label={`Remove attachment ${file.name}`}
                onClick={() => onAttachmentRemove(index)}
              >
                <X className="w-3 h-3" />
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Input row */}
      <div className="flex items-center gap-2">
        <button
          type="button"
          className="h-10 w-10 flex items-center justify-center rounded-full border border-gray-300 text-gray-500 hover:text-[#7E22CE] hover:border-[#D4B5F0] transition-colors"
          title="Attach file"
          aria-label="Attach file"
          onClick={() => fileInputRef.current?.click()}
        >
          <Plus className="w-4 h-4" />
        </button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          aria-label="Attach file"
          onChange={(event) => {
            onAttachmentAdd(event.target.files);
            if (event.target.value) event.target.value = '';
          }}
        />
        <textarea
          value={messageText}
          onChange={(e) => onMessageChange(e.target.value)}
          onKeyPress={onKeyPress}
          aria-label="Type a message"
          placeholder="Type your message..."
          className="flex-1 resize-none border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#D4B5F0] focus:border-purple-500 min-h-[2.5rem]"
          rows={1}
        />
        <button
          type="button"
          onClick={onSend}
          disabled={isSendDisabled}
          aria-label="Send message"
          className="h-10 w-10 flex items-center justify-center bg-[#7E22CE] text-white rounded-full hover:bg-[#5f1aa4] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          <Send className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
