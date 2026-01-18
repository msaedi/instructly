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
});
