/**
 * TemplateEditor - Template management UI
 *
 * Two-panel layout with:
 * - Left: Template list with create button
 * - Right: Template editor with AI rewrite
 */

import { useRef, useEffect, useState } from 'react';
import { Copy, Plus, Sparkles } from 'lucide-react';
import type { TemplateItem } from '../types';
import { deriveTemplatePreview, copyToClipboard, rewriteTemplateContent } from '../utils/templates';

export type TemplateEditorProps = {
  templates: TemplateItem[];
  selectedTemplateId: string | null;
  templateDrafts: Record<string, string>;
  onTemplateSelect: (templateId: string) => void;
  onTemplateCreate: () => void;
  onTemplateSubjectChange: (templateId: string, subject: string) => void;
  onTemplateDraftChange: (templateId: string, body: string) => void;
  onTemplatesUpdate: (updater: (prev: TemplateItem[]) => TemplateItem[]) => void;
};

export function TemplateEditor({
  templates,
  selectedTemplateId,
  templateDrafts,
  onTemplateSelect,
  onTemplateCreate: _onTemplateCreate,
  onTemplateSubjectChange,
  onTemplateDraftChange,
  onTemplatesUpdate,
}: TemplateEditorProps) {
  const subjectInputRef = useRef<HTMLInputElement | null>(null);
  const [pendingSubjectFocusId, setPendingSubjectFocusId] = useState<string | null>(null);
  const [copiedTemplateId, setCopiedTemplateId] = useState<string | null>(null);
  const [rewritingTemplateId, setRewritingTemplateId] = useState<string | null>(null);
  const [templateRewriteCounts, setTemplateRewriteCounts] = useState<Record<string, number>>({});

  // Auto-focus subject input when a new template is created
  useEffect(() => {
    if (!pendingSubjectFocusId || pendingSubjectFocusId !== selectedTemplateId) return;
    const frame = requestAnimationFrame(() => {
      if (subjectInputRef.current) {
        subjectInputRef.current.focus();
        subjectInputRef.current.select();
      }
      setPendingSubjectFocusId(null);
    });
    return () => cancelAnimationFrame(frame);
  }, [pendingSubjectFocusId, selectedTemplateId]);

  // Clear copied indicator after delay
  useEffect(() => {
    if (!copiedTemplateId) return;
    const timer = setTimeout(() => setCopiedTemplateId(null), 1500);
    return () => clearTimeout(timer);
  }, [copiedTemplateId]);

  const handleCreate = () => {
    const newId = `template-${Date.now()}`;
    onTemplatesUpdate((prev) => [
      ...prev,
      {
        id: newId,
        subject: 'Untitled template',
        preview: '',
        body: '',
      },
    ]);
    onTemplateDraftChange(newId, '');
    onTemplateSelect(newId);
    setPendingSubjectFocusId(newId);
    setTemplateRewriteCounts((prev) => ({ ...prev, [newId]: 0 }));
  };

  const handleRewrite = (templateId: string) => {
    const base = templateDrafts[templateId] ?? templates.find((t) => t.id === templateId)?.body ?? '';
    const variantIndex = templateRewriteCounts[templateId] ?? 0;
    setRewritingTemplateId(templateId);
    try {
      const improved = rewriteTemplateContent(base, variantIndex);
      onTemplateDraftChange(templateId, improved);
      onTemplatesUpdate((prev) =>
        prev.map((template) =>
          template.id === templateId
            ? { ...template, body: improved, preview: deriveTemplatePreview(improved) }
            : template
        )
      );
      setTemplateRewriteCounts((prev) => ({ ...prev, [templateId]: variantIndex + 1 }));
    } finally {
      setRewritingTemplateId(null);
    }
  };

  const handleCopy = async (templateId: string, content: string) => {
    const ok = await copyToClipboard(content);
    if (ok) {
      setCopiedTemplateId(templateId);
    } else {
      alert('Unable to copy template right now.');
    }
  };

  const current = templates.find((item) => item.id === selectedTemplateId) || templates[0];
  const content = current ? templateDrafts[current.id] ?? current.body : '';

  return (
    <div className="insta-surface-card overflow-hidden">
      <div className="flex h-[600px]">
        {/* Template list */}
        <div className="w-full md:w-1/3 border-r border-gray-200 flex flex-col">
          <div className="p-4 border-b border-gray-200 flex items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold insta-onboarding-strong-text">Templates</h3>
              <p className="text-xs insta-onboarding-subtitle mt-1">Choose a template to view or copy.</p>
            </div>
            <button
              type="button"
              onClick={handleCreate}
              className="insta-secondary-btn inline-flex items-center justify-center rounded-full p-2 transition-colors"
              aria-label="Create template"
            >
              <Plus className="w-4 h-4" />
            </button>
          </div>
          <div className="insta-thread-list flex-1 overflow-y-auto">
            {templates.map((template) => {
              const isActive = template.id === selectedTemplateId;
              const templateContent = templateDrafts[template.id] ?? template.body ?? '';
              const previewText =
                deriveTemplatePreview(templateContent) || template.preview || 'Add template content';
              const subjectLabel = template.subject?.trim() || 'Untitled template';
              return (
                <button
                  key={template.id}
                  type="button"
                  onClick={() => onTemplateSelect(template.id)}
                  className={`w-full text-left px-5 py-4 transition-none ${
                    isActive
                      ? 'bg-purple-50 dark:bg-purple-900/40 border-l-4 border-l-[#7E22CE]'
                      : 'hover:bg-gray-50 dark:hover:bg-gray-800/60'
                  }`}
                  >
                  <h4 className="text-sm font-medium insta-onboarding-strong-text truncate">{subjectLabel}</h4>
                  <p className="text-xs insta-onboarding-subtitle mt-1 truncate">
                    {previewText || 'Add template content'}
                  </p>
                </button>
              );
            })}
          </div>
        </div>

        {/* Template editor */}
        <div className="flex-1 flex flex-col">
          {current ? (
            <div className="flex-1 p-6 flex flex-col gap-4">
              <div className="flex items-center justify-between gap-4 flex-wrap">
                <div className="flex-1 min-w-[200px]">
                  <div className="rounded-md border border-transparent bg-white px-3 py-2 transition-all focus-within:border-[#E7DCF9] focus-within:shadow-[0_0_0_2px_rgba(219,201,246,0.25)]">
                    <input
                      ref={(element) => {
                        if (current.id === selectedTemplateId) {
                          subjectInputRef.current = element;
                        }
                      }}
                      value={current.subject}
                      onChange={(event) => onTemplateSubjectChange(current.id, event.target.value)}
                      placeholder="Template title"
                      aria-label="Template title"
                      className="template-title-input w-full bg-transparent text-lg font-semibold insta-onboarding-strong-text border-none outline-none focus:outline-none focus:ring-0 focus-visible:outline-none focus-visible:ring-0 placeholder:text-gray-400"
                    />
                  </div>
                  <p className="text-xs insta-onboarding-subtitle mt-1">Last updated manually.</p>
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  <button
                    type="button"
                    onClick={() => handleRewrite(current.id)}
                    disabled={rewritingTemplateId === current.id}
                    className="insta-primary-btn inline-flex items-center gap-2 rounded-full text-white px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
                  >
                    <Sparkles className="w-3.5 h-3.5" />
                    <span>{rewritingTemplateId === current.id ? 'Rewriting...' : 'Rewrite with AI'}</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => handleCopy(current.id, content)}
                    className="insta-secondary-btn inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium transition-colors"
                  >
                    <Copy className="w-3.5 h-3.5" />
                    <span>{copiedTemplateId === current.id ? 'Copied!' : 'Copy'}</span>
                  </button>
                </div>
              </div>
              <textarea
                value={content}
                onChange={(event) => {
                  const nextValue = event.target.value;
                  onTemplateDraftChange(current.id, nextValue);
                  onTemplatesUpdate((prev) =>
                    prev.map((template) =>
                      template.id === current.id
                        ? { ...template, body: nextValue, preview: deriveTemplatePreview(nextValue) }
                        : template
                    )
                  );
                }}
                className="flex-1 border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#D4B5F0] focus:border-purple-500"
              />
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center insta-onboarding-subtitle text-sm">
              No templates available.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
