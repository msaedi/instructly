import { renderHook, act } from '@testing-library/react';
import { useTemplates } from '../useTemplates';
import {
  loadStoredTemplates,
  saveTemplatesToCookie,
  deriveTemplatePreview,
} from '../../utils/templates';

// Mock the template utilities
jest.mock('../../utils/templates', () => ({
  loadStoredTemplates: jest.fn(),
  saveTemplatesToCookie: jest.fn(),
  deriveTemplatePreview: jest.fn(),
}));

const loadStoredTemplatesMock = loadStoredTemplates as jest.Mock;
const saveTemplatesToCookieMock = saveTemplatesToCookie as jest.Mock;
const deriveTemplatePreviewMock = deriveTemplatePreview as jest.Mock;

describe('useTemplates', () => {
  const mockTemplates = [
    { id: 'tmpl-1', subject: 'Welcome', body: 'Welcome to our class!', preview: 'Welcome to our...' },
    { id: 'tmpl-2', subject: 'Reminder', body: 'Lesson reminder text', preview: 'Lesson reminder...' },
  ];

  beforeEach(() => {
    jest.clearAllMocks();
    loadStoredTemplatesMock.mockReturnValue(mockTemplates);
    deriveTemplatePreviewMock.mockImplementation((text: string) => text.substring(0, 20) + '...');
  });

  it('initializes with templates from storage', () => {
    const { result } = renderHook(() => useTemplates());

    expect(result.current.templates).toEqual(mockTemplates);
    expect(loadStoredTemplatesMock).toHaveBeenCalled();
  });

  it('initializes selectedTemplateId to first template', () => {
    const { result } = renderHook(() => useTemplates());

    expect(result.current.selectedTemplateId).toBe('tmpl-1');
  });

  it('initializes selectedTemplateId to null when no templates', () => {
    loadStoredTemplatesMock.mockReturnValue([]);

    const { result } = renderHook(() => useTemplates());

    expect(result.current.selectedTemplateId).toBeNull();
  });

  it('initializes template drafts from template bodies', () => {
    const { result } = renderHook(() => useTemplates());

    expect(result.current.templateDrafts).toEqual({
      'tmpl-1': 'Welcome to our class!',
      'tmpl-2': 'Lesson reminder text',
    });
  });

  it('persists templates to cookie on change', () => {
    const { result } = renderHook(() => useTemplates());

    act(() => {
      result.current.setTemplates([
        { id: 'tmpl-new', subject: 'New', body: 'New body', preview: 'New...' },
      ]);
    });

    expect(saveTemplatesToCookieMock).toHaveBeenCalled();
  });

  it('handleTemplateSubjectChange updates subject', () => {
    const { result } = renderHook(() => useTemplates());

    act(() => {
      result.current.handleTemplateSubjectChange('tmpl-1', 'New Welcome Subject');
    });

    const updated = result.current.templates.find((t) => t.id === 'tmpl-1');
    expect(updated?.subject).toBe('New Welcome Subject');
  });

  it('handleTemplateSubjectChange does not affect other templates', () => {
    const { result } = renderHook(() => useTemplates());

    act(() => {
      result.current.handleTemplateSubjectChange('tmpl-1', 'Updated Subject');
    });

    const unchanged = result.current.templates.find((t) => t.id === 'tmpl-2');
    expect(unchanged?.subject).toBe('Reminder');
  });

  it('handleTemplateDraftChange updates body and draft', () => {
    const { result } = renderHook(() => useTemplates());

    act(() => {
      result.current.handleTemplateDraftChange('tmpl-1', 'Updated body content');
    });

    expect(result.current.templateDrafts['tmpl-1']).toBe('Updated body content');
    const updated = result.current.templates.find((t) => t.id === 'tmpl-1');
    expect(updated?.body).toBe('Updated body content');
  });

  it('handleTemplateDraftChange updates preview via deriveTemplatePreview', () => {
    const { result } = renderHook(() => useTemplates());

    act(() => {
      result.current.handleTemplateDraftChange('tmpl-1', 'New body for preview test');
    });

    expect(deriveTemplatePreviewMock).toHaveBeenCalledWith('New body for preview test');
  });

  it('setSelectedTemplateId changes selected template', () => {
    const { result } = renderHook(() => useTemplates());

    act(() => {
      result.current.setSelectedTemplateId('tmpl-2');
    });

    expect(result.current.selectedTemplateId).toBe('tmpl-2');
  });

  it('setSelectedTemplateId can set to null', () => {
    const { result } = renderHook(() => useTemplates());

    act(() => {
      result.current.setSelectedTemplateId(null);
    });

    expect(result.current.selectedTemplateId).toBeNull();
  });

  it('setTemplateDrafts allows direct draft updates', () => {
    const { result } = renderHook(() => useTemplates());

    act(() => {
      result.current.setTemplateDrafts({
        'tmpl-1': 'Draft 1 updated',
        'tmpl-2': 'Draft 2 updated',
      });
    });

    expect(result.current.templateDrafts).toEqual({
      'tmpl-1': 'Draft 1 updated',
      'tmpl-2': 'Draft 2 updated',
    });
  });

  it('setTemplates allows direct template list updates', () => {
    const { result } = renderHook(() => useTemplates());
    const newTemplates = [
      { id: 'new-1', subject: 'Brand New', body: 'Brand new body', preview: 'Brand new...' },
    ];

    act(() => {
      result.current.setTemplates(newTemplates);
    });

    expect(result.current.templates).toEqual(newTemplates);
  });

  it('returns stable callback references', () => {
    const { result, rerender } = renderHook(() => useTemplates());

    const initialSubjectChange = result.current.handleTemplateSubjectChange;
    const initialDraftChange = result.current.handleTemplateDraftChange;

    rerender();

    expect(result.current.handleTemplateSubjectChange).toBe(initialSubjectChange);
    expect(result.current.handleTemplateDraftChange).toBe(initialDraftChange);
  });
});
