/**
 * MessageBubble - Single message display component
 *
 * Pure UI component for rendering a chat message bubble with:
 * - Sender-appropriate styling (instructor/student/platform)
 * - Attachment previews
 * - Delivery status
 */

import { Paperclip } from 'lucide-react';
import type { MessageWithAttachments } from '../types';
import { formatShortDate } from '../utils/formatters';

export type MessageBubbleProps = {
  message: MessageWithAttachments;
  isLastInstructor: boolean;
  showSenderName?: boolean;
  senderName?: string;
};

export function MessageBubble({
  message,
  isLastInstructor,
  showSenderName = false,
  senderName,
}: MessageBubbleProps) {
  const attachmentList = message.attachments || [];
  const displayText = message.text?.trim();

  const bubbleClasses =
    message.sender === 'instructor'
      ? 'bg-[#7E22CE] text-white'
      : message.sender === 'platform'
        ? 'bg-blue-100 text-blue-800'
        : 'bg-gray-100 text-gray-800';

  const attachmentWrapper =
    message.sender === 'instructor'
      ? 'bg-white/10 border border-white/20'
      : 'bg-white border border-gray-200';

  const delivery = message.delivery;
  const deliveryLabel = (() => {
    if (!delivery) return 'Delivered';
    if (delivery.status === 'read') return `Read ${delivery.timeLabel}`;
    if (delivery.status === 'delivered') return `Delivered ${delivery.timeLabel}`;
    return 'Delivered';
  })();

  const shortDate =
    formatShortDate(message.createdAt) ||
    formatShortDate((message as { timestamp?: string }).timestamp ?? null) ||
    '';

  return (
    <div className={`flex ${message.sender === 'instructor' ? 'justify-end' : 'justify-start'}`}>
      <div className={`flex flex-col ${message.sender === 'instructor' ? 'items-end' : 'items-start'}`}>
        {/* Sender name */}
        {showSenderName && senderName && (
          <div className={`text-xs text-gray-500 mb-1 ${message.sender === 'instructor' ? 'mr-2' : 'ml-2'}`}>
            {senderName}
          </div>
        )}

        <div
          className={`group relative max-w-xs lg:max-w-md rounded-lg px-4 pt-6 pb-3 pr-14 ${bubbleClasses}`}
        >
        {shortDate && (
          <div
            className={`absolute top-2 right-3 flex flex-col items-end text-[11px] ${
              message.sender === 'instructor'
                ? 'text-white/80'
                : message.sender === 'platform'
                  ? 'text-blue-700'
                  : 'text-gray-500'
            }`}
          >
            <span className="leading-none mb-2">{shortDate}</span>
          </div>
        )}

        {displayText && <p className="text-sm whitespace-pre-line">{displayText}</p>}

        {attachmentList.length > 0 && (
          <div className="mt-2 flex flex-col gap-2">
            {attachmentList.map((attachment, index) => {
              const isImage = attachment.type.startsWith('image/');
              if (isImage && attachment.dataUrl) {
                return (
                  <div
                    key={`${attachment.name}-${index}`}
                    className={`overflow-hidden rounded-lg ${attachmentWrapper}`}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={attachment.dataUrl}
                      alt={attachment.name}
                      className="max-w-[240px] rounded-md object-cover"
                    />
                    <p className="text-xs opacity-80 mt-1 truncate px-2 pb-1">{attachment.name}</p>
                  </div>
                );
              }
              return (
                <div
                  key={`${attachment.name}-${index}`}
                  className={`flex items-center gap-2 rounded-lg px-3 py-2 ${attachmentWrapper}`}
                >
                  <Paperclip className="w-4 h-4 opacity-80" />
                  <span className="text-xs truncate max-w-[12rem]" title={attachment.name}>
                    {attachment.name}
                  </span>
                </div>
              );
            })}
          </div>
        )}

        {!shortDate && <p className="text-xs opacity-70 mt-1">{message.timestamp}</p>}

        {isLastInstructor && (
          <p
            className={`text-[10px] opacity-80 mt-0.5 ${
              message.sender === 'instructor' ? 'text-right' : ''
            }`}
          >
            {deliveryLabel}
          </p>
        )}
        </div>
      </div>
    </div>
  );
}
