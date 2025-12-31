/**
 * useTemplates - Hook for managing message templates
 *
 * Handles:
 * - Loading templates from cookies
 * - Persisting templates to cookies
 * - Template CRUD operations
 */

import { useState, useEffect, useCallback } from 'react';
import type { TemplateItem } from '../types';
import { loadStoredTemplates, saveTemplatesToCookie, deriveTemplatePreview } from '../utils/templates';

export type UseTemplatesResult = {
  templates: TemplateItem[];
  setTemplates: React.Dispatch<React.SetStateAction<TemplateItem[]>>;
  selectedTemplateId: string | null;
  setSelectedTemplateId: React.Dispatch<React.SetStateAction<string | null>>;
  templateDrafts: Record<string, string>;
  setTemplateDrafts: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  handleTemplateSubjectChange: (templateId: string, subject: string) => void;
  handleTemplateDraftChange: (templateId: string, body: string) => void;
};

export function useTemplates(): UseTemplatesResult {
  const initialTemplates = loadStoredTemplates();

  const [templates, setTemplates] = useState<TemplateItem[]>(() => initialTemplates);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(
    () => initialTemplates[0]?.id ?? null
  );
  const [templateDrafts, setTemplateDrafts] = useState<Record<string, string>>(() => {
    const entries = initialTemplates.map((template) => [template.id, template.body]) as [string, string][];
    return Object.fromEntries(entries);
  });

  // Persist templates to cookie on change
  useEffect(() => {
    saveTemplatesToCookie(templates);
  }, [templates]);

  const handleTemplateSubjectChange = useCallback((templateId: string, nextSubject: string) => {
    setTemplates((prev) =>
      prev.map((template) =>
        template.id === templateId
          ? { ...template, subject: nextSubject }
          : template
      )
    );
  }, []);

  const handleTemplateDraftChange = useCallback((templateId: string, body: string) => {
    setTemplateDrafts((prev) => ({ ...prev, [templateId]: body }));
    setTemplates((prev) =>
      prev.map((template) =>
        template.id === templateId
          ? { ...template, body, preview: deriveTemplatePreview(body) }
          : template
      )
    );
  }, []);

  return {
    templates,
    setTemplates,
    selectedTemplateId,
    setSelectedTemplateId,
    templateDrafts,
    setTemplateDrafts,
    handleTemplateSubjectChange,
    handleTemplateDraftChange,
  };
}
