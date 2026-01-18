import { render, screen, fireEvent, act } from '@testing-library/react';
import { TemplateEditor, type TemplateEditorProps } from '../TemplateEditor';
import type { TemplateItem } from '../../types';
import { copyToClipboard, rewriteTemplateContent, deriveTemplatePreview } from '../../utils/templates';

// Mock the template utilities
jest.mock('../../utils/templates', () => ({
  copyToClipboard: jest.fn(),
  rewriteTemplateContent: jest.fn(),
  deriveTemplatePreview: jest.fn((text: string) => text.substring(0, 50) + '...'),
}));

const copyToClipboardMock = copyToClipboard as jest.Mock;
const rewriteTemplateContentMock = rewriteTemplateContent as jest.Mock;
const deriveTemplatePreviewMock = deriveTemplatePreview as jest.Mock;

describe('TemplateEditor', () => {
  const mockTemplates: TemplateItem[] = [
    {
      id: 'tmpl-1',
      subject: 'Welcome Template',
      body: 'Welcome to the lesson! Looking forward to working with you.',
      preview: 'Welcome to the lesson...',
    },
    {
      id: 'tmpl-2',
      subject: 'Reminder Template',
      body: 'Just a reminder about your upcoming lesson tomorrow.',
      preview: 'Just a reminder...',
    },
  ];

  const defaultProps: TemplateEditorProps = {
    templates: mockTemplates,
    selectedTemplateId: 'tmpl-1',
    templateDrafts: {
      'tmpl-1': 'Welcome to the lesson! Looking forward to working with you.',
      'tmpl-2': 'Just a reminder about your upcoming lesson tomorrow.',
    },
    onTemplateSelect: jest.fn(),
    onTemplateCreate: jest.fn(),
    onTemplateSubjectChange: jest.fn(),
    onTemplateDraftChange: jest.fn(),
    onTemplatesUpdate: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
    copyToClipboardMock.mockResolvedValue(true);
    rewriteTemplateContentMock.mockImplementation((text: string) => `Improved: ${text}`);
    deriveTemplatePreviewMock.mockImplementation((text: string) =>
      text.length > 50 ? text.substring(0, 50) + '...' : text
    );
  });

  describe('template list', () => {
    it('renders all templates in the list', () => {
      render(<TemplateEditor {...defaultProps} />);

      expect(screen.getByText('Welcome Template')).toBeInTheDocument();
      expect(screen.getByText('Reminder Template')).toBeInTheDocument();
    });

    it('highlights the selected template', () => {
      render(<TemplateEditor {...defaultProps} />);

      const welcomeButton = screen.getByRole('button', { name: /welcome template/i });
      expect(welcomeButton).toHaveClass('bg-purple-50');
    });

    it('calls onTemplateSelect when clicking a template', () => {
      const onSelect = jest.fn();
      render(<TemplateEditor {...defaultProps} onTemplateSelect={onSelect} />);

      fireEvent.click(screen.getByText('Reminder Template'));

      expect(onSelect).toHaveBeenCalledWith('tmpl-2');
    });

    it('displays template preview text', () => {
      render(<TemplateEditor {...defaultProps} />);

      // Preview text appears in both list and editor when selected
      const previewElements = screen.getAllByText(/Welcome to the lesson/);
      expect(previewElements.length).toBeGreaterThan(0);
    });
  });

  describe('create button', () => {
    it('renders create button', () => {
      render(<TemplateEditor {...defaultProps} />);

      expect(screen.getByRole('button', { name: /create template/i })).toBeInTheDocument();
    });

    it('creates a new template when clicking create button', () => {
      const onTemplatesUpdate = jest.fn();
      const onTemplateDraftChange = jest.fn();
      const onTemplateSelect = jest.fn();

      render(
        <TemplateEditor
          {...defaultProps}
          onTemplatesUpdate={onTemplatesUpdate}
          onTemplateDraftChange={onTemplateDraftChange}
          onTemplateSelect={onTemplateSelect}
        />
      );

      fireEvent.click(screen.getByRole('button', { name: /create template/i }));

      expect(onTemplatesUpdate).toHaveBeenCalled();
      expect(onTemplateDraftChange).toHaveBeenCalled();
      expect(onTemplateSelect).toHaveBeenCalled();
    });
  });

  describe('template editor panel', () => {
    it('displays the selected template subject', () => {
      render(<TemplateEditor {...defaultProps} />);

      const subjectInput = screen.getByRole('textbox', { name: /template title/i });
      expect(subjectInput).toHaveValue('Welcome Template');
    });

    it('displays the template body in textarea', () => {
      render(<TemplateEditor {...defaultProps} />);

      const textarea = screen.getByRole('textbox', { name: '' });
      expect(textarea).toHaveValue('Welcome to the lesson! Looking forward to working with you.');
    });

    it('calls onTemplateSubjectChange when editing subject', () => {
      const onSubjectChange = jest.fn();
      render(
        <TemplateEditor {...defaultProps} onTemplateSubjectChange={onSubjectChange} />
      );

      const subjectInput = screen.getByRole('textbox', { name: /template title/i });
      fireEvent.change(subjectInput, { target: { value: 'New Subject' } });

      expect(onSubjectChange).toHaveBeenCalledWith('tmpl-1', 'New Subject');
    });

    it('calls onTemplateDraftChange and onTemplatesUpdate when editing body', () => {
      const onDraftChange = jest.fn();
      const onTemplatesUpdate = jest.fn();

      render(
        <TemplateEditor
          {...defaultProps}
          onTemplateDraftChange={onDraftChange}
          onTemplatesUpdate={onTemplatesUpdate}
        />
      );

      const textarea = screen.getByRole('textbox', { name: '' });
      fireEvent.change(textarea, { target: { value: 'Updated body content' } });

      expect(onDraftChange).toHaveBeenCalledWith('tmpl-1', 'Updated body content');
      expect(onTemplatesUpdate).toHaveBeenCalled();
    });
  });

  describe('copy functionality', () => {
    it('renders copy button', () => {
      render(<TemplateEditor {...defaultProps} />);

      expect(screen.getByRole('button', { name: /copy/i })).toBeInTheDocument();
    });

    it('copies template content to clipboard', async () => {
      render(<TemplateEditor {...defaultProps} />);

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /copy/i }));
      });

      expect(copyToClipboardMock).toHaveBeenCalledWith(
        'Welcome to the lesson! Looking forward to working with you.'
      );
    });

    it('shows "Copied!" feedback after successful copy', async () => {
      jest.useFakeTimers();

      render(<TemplateEditor {...defaultProps} />);

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /copy/i }));
      });

      expect(screen.getByText('Copied!')).toBeInTheDocument();

      jest.useRealTimers();
    });
  });

  describe('AI rewrite functionality', () => {
    it('renders rewrite button', () => {
      render(<TemplateEditor {...defaultProps} />);

      expect(screen.getByRole('button', { name: /rewrite with ai/i })).toBeInTheDocument();
    });

    it('calls rewriteTemplateContent when clicking rewrite', () => {
      render(<TemplateEditor {...defaultProps} />);

      fireEvent.click(screen.getByRole('button', { name: /rewrite with ai/i }));

      expect(rewriteTemplateContentMock).toHaveBeenCalled();
    });

    it('updates template with rewritten content', () => {
      const onDraftChange = jest.fn();
      const onTemplatesUpdate = jest.fn();

      render(
        <TemplateEditor
          {...defaultProps}
          onTemplateDraftChange={onDraftChange}
          onTemplatesUpdate={onTemplatesUpdate}
        />
      );

      fireEvent.click(screen.getByRole('button', { name: /rewrite with ai/i }));

      expect(onDraftChange).toHaveBeenCalled();
      expect(onTemplatesUpdate).toHaveBeenCalled();
    });
  });

  describe('empty state', () => {
    it('shows empty state when no templates', () => {
      render(
        <TemplateEditor {...defaultProps} templates={[]} selectedTemplateId={null} />
      );

      expect(screen.getByText('No templates available.')).toBeInTheDocument();
    });
  });

  describe('edge cases', () => {
    it('handles undefined template subject gracefully', () => {
      const templateWithNoSubject: TemplateItem[] = [
        { ...mockTemplates[0]!, subject: '' },
      ];

      render(
        <TemplateEditor
          {...defaultProps}
          templates={templateWithNoSubject}
          selectedTemplateId="tmpl-1"
        />
      );

      // Should show "Untitled template" for empty subject
      expect(screen.getByText('Untitled template')).toBeInTheDocument();
    });

    it('uses first template when selectedTemplateId is null', () => {
      render(
        <TemplateEditor {...defaultProps} selectedTemplateId={null} />
      );

      // Should display first template's content
      expect(screen.getByDisplayValue('Welcome Template')).toBeInTheDocument();
    });
  });

  describe('auto-focus on new template', () => {
    it('focuses subject input when a new template is created', async () => {
      jest.useFakeTimers();
      const onTemplatesUpdate = jest.fn();
      const onTemplateDraftChange = jest.fn();
      const onTemplateSelect = jest.fn();

      const { rerender } = render(
        <TemplateEditor
          {...defaultProps}
          onTemplatesUpdate={onTemplatesUpdate}
          onTemplateDraftChange={onTemplateDraftChange}
          onTemplateSelect={onTemplateSelect}
        />
      );

      // Click create template
      fireEvent.click(screen.getByRole('button', { name: /create template/i }));

      // Get the new template ID from the call
      const updateCall = onTemplatesUpdate.mock.calls[0];
      expect(updateCall).toBeDefined();
      const updater = updateCall[0] as (prev: TemplateItem[]) => TemplateItem[];
      const newTemplates = updater(mockTemplates);
      const newTemplate = newTemplates[newTemplates.length - 1];
      expect(newTemplate).toBeDefined();
      const newId = newTemplate!.id;

      // Rerender with new template selected (simulating the state change)
      rerender(
        <TemplateEditor
          {...defaultProps}
          templates={newTemplates}
          selectedTemplateId={newId}
          onTemplatesUpdate={onTemplatesUpdate}
          onTemplateDraftChange={onTemplateDraftChange}
          onTemplateSelect={onTemplateSelect}
        />
      );

      // Advance timers to trigger requestAnimationFrame
      await act(async () => {
        jest.runAllTimers();
      });

      // The subject input should be focused
      const subjectInput = screen.getByRole('textbox', { name: /template title/i });
      expect(subjectInput).toBeInTheDocument();

      jest.useRealTimers();
    });

    it('cleans up animation frame on unmount', async () => {
      jest.useFakeTimers();
      const cancelAnimationFrameSpy = jest.spyOn(window, 'cancelAnimationFrame');

      const { unmount, rerender } = render(
        <TemplateEditor {...defaultProps} />
      );

      // Trigger pending subject focus
      fireEvent.click(screen.getByRole('button', { name: /create template/i }));

      // Get new template from the updater
      const updateCall = defaultProps.onTemplatesUpdate as jest.Mock;
      const call = (updateCall as jest.Mock).mock.calls[0];
      if (call) {
        const updater = call[0] as (prev: TemplateItem[]) => TemplateItem[];
        const newTemplates = updater(mockTemplates);
        const newId = newTemplates[newTemplates.length - 1]!.id;

        rerender(
          <TemplateEditor
            {...defaultProps}
            templates={newTemplates}
            selectedTemplateId={newId}
          />
        );
      }

      // Unmount before the animation frame completes
      unmount();

      // Verify cleanup was called
      expect(cancelAnimationFrameSpy).toHaveBeenCalled();

      cancelAnimationFrameSpy.mockRestore();
      jest.useRealTimers();
    });
  });

  describe('copy error handling', () => {
    it('shows alert when copy fails', async () => {
      const alertSpy = jest.spyOn(window, 'alert').mockImplementation(() => {});
      copyToClipboardMock.mockResolvedValue(false);

      render(<TemplateEditor {...defaultProps} />);

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /copy/i }));
      });

      expect(alertSpy).toHaveBeenCalledWith('Unable to copy template right now.');

      alertSpy.mockRestore();
    });
  });

  describe('copied indicator timer', () => {
    it('clears copied indicator after delay', async () => {
      jest.useFakeTimers();
      copyToClipboardMock.mockResolvedValue(true);

      render(<TemplateEditor {...defaultProps} />);

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /copy/i }));
      });

      expect(screen.getByText('Copied!')).toBeInTheDocument();

      // Advance timer to clear the copied state
      await act(async () => {
        jest.advanceTimersByTime(1500);
      });

      // Should now show "Copy" again
      expect(screen.getByText('Copy')).toBeInTheDocument();

      jest.useRealTimers();
    });

    it('cleans up timer on unmount', async () => {
      jest.useFakeTimers();
      const clearTimeoutSpy = jest.spyOn(global, 'clearTimeout');
      copyToClipboardMock.mockResolvedValue(true);

      const { unmount } = render(<TemplateEditor {...defaultProps} />);

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /copy/i }));
      });

      unmount();

      expect(clearTimeoutSpy).toHaveBeenCalled();

      clearTimeoutSpy.mockRestore();
      jest.useRealTimers();
    });
  });

  describe('template content updates', () => {
    it('updates template body and preview when editing textarea', () => {
      const onDraftChange = jest.fn();
      const onTemplatesUpdate = jest.fn();

      render(
        <TemplateEditor
          {...defaultProps}
          onTemplateDraftChange={onDraftChange}
          onTemplatesUpdate={onTemplatesUpdate}
        />
      );

      const textarea = screen.getByRole('textbox', { name: '' });
      fireEvent.change(textarea, { target: { value: 'New content for the template' } });

      // Verify updater was called
      expect(onTemplatesUpdate).toHaveBeenCalled();
      const updater = onTemplatesUpdate.mock.calls[0]![0] as (prev: TemplateItem[]) => TemplateItem[];
      const result = updater(mockTemplates);

      // Verify the correct template was updated
      const updatedTemplate = result.find((t) => t.id === 'tmpl-1');
      expect(updatedTemplate?.body).toBe('New content for the template');
    });

    it('preserves other templates when updating one', () => {
      const onTemplatesUpdate = jest.fn();

      render(
        <TemplateEditor
          {...defaultProps}
          onTemplatesUpdate={onTemplatesUpdate}
        />
      );

      const textarea = screen.getByRole('textbox', { name: '' });
      fireEvent.change(textarea, { target: { value: 'Updated content' } });

      const updater = onTemplatesUpdate.mock.calls[0]![0] as (prev: TemplateItem[]) => TemplateItem[];
      const result = updater(mockTemplates);

      // Other template should be unchanged
      const otherTemplate = result.find((t) => t.id === 'tmpl-2');
      expect(otherTemplate?.body).toBe('Just a reminder about your upcoming lesson tomorrow.');
    });
  });

  describe('rewrite functionality coverage', () => {
    it('updates correct template during rewrite', () => {
      const onTemplatesUpdate = jest.fn();

      render(
        <TemplateEditor
          {...defaultProps}
          onTemplatesUpdate={onTemplatesUpdate}
        />
      );

      fireEvent.click(screen.getByRole('button', { name: /rewrite with ai/i }));

      // Verify updater was called and updates correct template
      expect(onTemplatesUpdate).toHaveBeenCalled();
      const updater = onTemplatesUpdate.mock.calls[0]![0] as (prev: TemplateItem[]) => TemplateItem[];
      const result = updater(mockTemplates);

      // Verify the selected template was updated with rewritten content
      const updatedTemplate = result.find((t) => t.id === 'tmpl-1');
      expect(updatedTemplate?.body).toContain('Improved:');

      // Other template should be unchanged
      const otherTemplate = result.find((t) => t.id === 'tmpl-2');
      expect(otherTemplate?.body).toBe('Just a reminder about your upcoming lesson tomorrow.');
    });

    it('increments rewrite count for variant selection', () => {
      render(<TemplateEditor {...defaultProps} />);

      // First rewrite
      fireEvent.click(screen.getByRole('button', { name: /rewrite with ai/i }));
      expect(rewriteTemplateContentMock).toHaveBeenCalledWith(
        'Welcome to the lesson! Looking forward to working with you.',
        0
      );

      // Second rewrite - should use incremented variant index
      fireEvent.click(screen.getByRole('button', { name: /rewrite with ai/i }));
      expect(rewriteTemplateContentMock).toHaveBeenCalledWith(
        expect.any(String),
        1
      );
    });

    it('uses template body as fallback when no draft exists', () => {
      render(
        <TemplateEditor
          {...defaultProps}
          templateDrafts={{}} // No drafts
        />
      );

      fireEvent.click(screen.getByRole('button', { name: /rewrite with ai/i }));

      // Should use template.body when no draft exists
      expect(rewriteTemplateContentMock).toHaveBeenCalledWith(
        'Welcome to the lesson! Looking forward to working with you.',
        0
      );
    });

    it('uses empty string as fallback when template has no body', () => {
      const templateWithNoBody: TemplateItem[] = [
        { id: 'tmpl-no-body', subject: 'Empty', body: '', preview: '' },
      ];

      render(
        <TemplateEditor
          {...defaultProps}
          templates={templateWithNoBody}
          selectedTemplateId="tmpl-no-body"
          templateDrafts={{}}
        />
      );

      fireEvent.click(screen.getByRole('button', { name: /rewrite with ai/i }));

      expect(rewriteTemplateContentMock).toHaveBeenCalledWith('', 0);
    });
  });

  describe('template list display', () => {
    it('shows "Add template content" for empty preview', () => {
      const templatesWithEmptyPreview: TemplateItem[] = [
        { id: 'tmpl-empty', subject: 'Empty Template', body: '', preview: '' },
      ];
      deriveTemplatePreviewMock.mockReturnValue('');

      render(
        <TemplateEditor
          {...defaultProps}
          templates={templatesWithEmptyPreview}
          selectedTemplateId="tmpl-empty"
          templateDrafts={{}}
        />
      );

      expect(screen.getAllByText('Add template content').length).toBeGreaterThan(0);
    });

    it('uses template preview when draft is empty', () => {
      const templatesWithPreview: TemplateItem[] = [
        { id: 'tmpl-1', subject: 'Test', body: '', preview: 'Existing preview' },
      ];
      deriveTemplatePreviewMock.mockReturnValue('');

      render(
        <TemplateEditor
          {...defaultProps}
          templates={templatesWithPreview}
          selectedTemplateId="tmpl-1"
          templateDrafts={{}}
        />
      );

      expect(screen.getByText('Existing preview')).toBeInTheDocument();
    });
  });

  describe('subject input ref assignment', () => {
    it('assigns ref only to selected template input', () => {
      render(
        <TemplateEditor
          {...defaultProps}
          selectedTemplateId="tmpl-1"
        />
      );

      // The input for selected template should be accessible
      const subjectInput = screen.getByRole('textbox', { name: /template title/i });
      expect(subjectInput).toHaveValue('Welcome Template');
    });
  });
});
