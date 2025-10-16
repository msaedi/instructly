import type { PricingConfig, PricingPreviewResponse } from '@/lib/api/pricing';

interface ComputeStudentFeePercentArgs {
  preview?: PricingPreviewResponse | null;
  config?: Pick<PricingConfig, 'student_fee_pct'> | null;
}

export function computeStudentFeePercent({ preview = null, config = null }: ComputeStudentFeePercentArgs = {}): number | null {
  const baseCents = preview?.base_price_cents;
  const feeCents = preview?.student_fee_cents;

  if (typeof baseCents === 'number' && baseCents > 0 && typeof feeCents === 'number') {
    const pct = Math.round((feeCents / baseCents) * 100);
    if (Number.isFinite(pct)) {
      return pct;
    }
  }

  const fallbackPct = config?.student_fee_pct;
  if (typeof fallbackPct === 'number') {
    const pct = Math.round(fallbackPct * 100);
    if (Number.isFinite(pct)) {
      return pct;
    }
  }

  return null;
}

interface FormatServiceSupportLabelOptions {
  includeFeeWord?: boolean;
}

export function formatServiceSupportLabel(
  percent: number | null,
  { includeFeeWord = true }: FormatServiceSupportLabelOptions = {}
): string {
  const baseLabel = includeFeeWord ? 'Service & Support fee' : 'Service & Support';
  return percent !== null ? `${baseLabel} (${percent}%)` : baseLabel;
}

const FALLBACK_PERCENT_TEXT = 'a percentage';

export function formatServiceSupportTooltip(percent: number | null): string {
  const percentText = percent !== null ? `${percent}%` : FALLBACK_PERCENT_TEXT;
  return [
    'This fee helps fund:',
    '• Secure, instant booking & payments',
    '• Verified, background-checked instructors',
    '• Customer support & incident assistance',
    '• Platform operations that keep lessons reliable',
    `It’s calculated at ${percentText} of the lesson price. Credits reduce your total.`,
  ].join('\n');
}
