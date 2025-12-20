import { logger } from '@/lib/logger';
import { withApiBase } from '@/lib/apiBase';
import { httpGet, httpPost } from '@/lib/http';

export interface PaymentMethod {
  id: string;
  last4: string;
  brand: string;
  is_default: boolean;
  created_at: string;
}

export interface SavePaymentMethodRequest {
  payment_method_id: string;
  set_as_default?: boolean;
}

export interface CreateCheckoutRequest {
  booking_id: string;
  payment_method_id?: string;
  save_payment_method?: boolean;
  requested_credit_cents?: number;
}

export interface Transaction {
  id: string;
  booking_id: string;
  service_name: string;
  instructor_name: string;
  booking_date: string;
  start_time: string;
  end_time: string;
  duration_minutes: number;
  hourly_rate: number;
  lesson_amount: number;
  service_fee: number;
  credit_applied: number;
  tip_amount: number;
  tip_paid: number;
  tip_status?: string | null;
  total_paid: number;
  status: string;
  created_at: string;
}

export interface CheckoutResponse {
  success: boolean;
  payment_intent_id: string;
  status: string;
  amount: number;
  application_fee: number;
  client_secret?: string;
  requires_action?: boolean;
}

export interface OnboardingResponse {
  account_id: string;
  onboarding_url: string;
  already_onboarded: boolean;
}

export interface OnboardingStatusResponse {
  has_account: boolean;
  onboarding_completed: boolean;
  charges_enabled: boolean;
  payouts_enabled: boolean;
  details_submitted: boolean;
  requirements: string[];
}

export interface EarningsResponse {
  total_earned: number;
  total_fees: number;
  booking_count: number;
  average_earning: number;
  hours_invoiced?: number;
  service_count?: number;
  period_start?: string;
  period_end?: string;
  invoices?: InstructorInvoice[];
  // Instructor-centric aggregate fields
  total_lesson_value?: number;
  total_platform_fees?: number;
  total_tips?: number;
}

export interface InstructorInvoice {
  booking_id: string;
  lesson_date: string;
  start_time?: string | null;
  service_name?: string | null;
  student_name?: string | null;
  duration_minutes?: number | null;
  total_paid_cents: number;
  tip_cents: number;
  instructor_share_cents: number;
  status: string;
  created_at: string;
  // Instructor-centric clarity fields
  lesson_price_cents: number;
  platform_fee_cents: number;
  platform_fee_rate: number;
  student_fee_cents: number;
}

export interface PayoutSummary {
  id: string;
  amount_cents: number;
  status: string;
  arrival_date?: string | null;
  failure_code?: string | null;
  failure_message?: string | null;
  created_at: string;
}

export interface PayoutHistoryResponse {
  payouts: PayoutSummary[];
  total_paid_cents: number;
  total_pending_cents: number;
  payout_count: number;
}

class PaymentService {
  private basePath = `/api/v1/payments`;

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = withApiBase(`${this.basePath}${endpoint}`);
    const method = (options.method || 'GET').toUpperCase();
    if (method === 'GET') {
      return (await httpGet(url)) as T;
    }
    return (await httpPost(url, options.body ? JSON.parse(options.body as string) : undefined)) as T;
  }

  // Payment Methods Management
  async listPaymentMethods(): Promise<PaymentMethod[]> {
    try {
      return await this.request<PaymentMethod[]>('/methods');
    } catch (error) {
      logger.error('Failed to list payment methods:', error);
      throw error;
    }
  }

  async savePaymentMethod(data: SavePaymentMethodRequest): Promise<PaymentMethod> {
    try {
      return await this.request<PaymentMethod>('/methods', {
        method: 'POST',
        body: JSON.stringify(data),
      });
    } catch (error) {
      logger.error('Failed to save payment method:', error);
      throw error;
    }
  }

  async deletePaymentMethod(id: string): Promise<{ success: boolean }> {
    try {
      return await this.request<{ success: boolean }>(`/methods/${id}`, {
        method: 'DELETE',
      });
    } catch (error) {
      logger.error('Failed to delete payment method:', error);
      throw error;
    }
  }

  async setDefaultPaymentMethod(id: string): Promise<PaymentMethod> {
    try {
      return await this.request<PaymentMethod>('/methods', {
        method: 'POST',
        body: JSON.stringify({
          payment_method_id: id,
          set_as_default: true,
        }),
      });
    } catch (error) {
      logger.error('Failed to set default payment method:', error);
      throw error;
    }
  }

  // Checkout
  async createCheckout(data: CreateCheckoutRequest): Promise<CheckoutResponse> {
    try {
      return await this.request<CheckoutResponse>('/checkout', {
        method: 'POST',
        body: JSON.stringify(data),
      });
    } catch (error) {
      logger.error('Failed to create checkout:', error);
      throw error;
    }
  }

  // Instructor Onboarding (Stripe Connect)
  async startOnboarding(): Promise<OnboardingResponse> {
    try {
      return await this.request<OnboardingResponse>('/connect/onboard', {
        method: 'POST',
      });
    } catch (error) {
      logger.error('Failed to start onboarding:', error);
      throw error;
    }
  }

  async startOnboardingWithReturn(return_to: string): Promise<OnboardingResponse> {
    try {
      return await this.request<OnboardingResponse>(`/connect/onboard${return_to ? `?return_to=${encodeURIComponent(return_to)}` : ''}`, {
        method: 'POST',
      });
    } catch (error) {
      logger.error('Failed to start onboarding with return:', error);
      throw error;
    }
  }

  async getOnboardingStatus(): Promise<OnboardingStatusResponse> {
    try {
      return await this.request<OnboardingStatusResponse>('/connect/status');
    } catch (error) {
      logger.error('Failed to get onboarding status:', error);
      throw error;
    }
  }

  async getDashboardLink(): Promise<{ dashboard_url: string; expires_in_minutes: number }> {
    try {
      return await this.request<{ dashboard_url: string; expires_in_minutes: number }>('/connect/dashboard');
    } catch (error) {
      logger.error('Failed to get dashboard link:', error);
      throw error;
    }
  }

  // Earnings
  async getEarnings(): Promise<EarningsResponse> {
    try {
      return await this.request<EarningsResponse>('/earnings');
    } catch (error) {
      logger.error('Failed to get earnings:', error);
      throw error;
    }
  }

  // Payouts
  async getPayouts(limit = 50): Promise<PayoutHistoryResponse> {
    try {
      return await this.request<PayoutHistoryResponse>(`/payouts?limit=${limit}`);
    } catch (error) {
      logger.error('Failed to get payouts:', error);
      throw error;
    }
  }

  // Transaction History
  async getTransactionHistory(limit = 20, offset = 0): Promise<Transaction[]> {
    try {
      return await this.request<Transaction[]>(`/transactions?limit=${limit}&offset=${offset}`);
    } catch (error) {
      logger.error('Failed to get transaction history:', error);
      throw error;
    }
  }

  // Credit Balance
  async getCreditBalance(): Promise<{ available: number; expires_at: string | null; pending: number }> {
    try {
      return await this.request<{ available: number; expires_at: string | null; pending: number }>('/credits');
    } catch (error) {
      logger.error('Failed to get credit balance:', error);
      throw error;
    }
  }

  // Apply Promo Code
  async applyPromoCode(code: string): Promise<{ success: boolean; credit_added: number }> {
    try {
      return await this.request<{ success: boolean; credit_added: number }>('/promo', {
        method: 'POST',
        body: JSON.stringify({ code }),
      });
    } catch (error) {
      logger.error('Failed to apply promo code:', error);
      throw error;
    }
  }

  // Download Transaction History
  async downloadTransactionHistory(): Promise<Blob> {
    const response = await fetch(withApiBase(`${this.basePath}/transactions/download`), {
      credentials: 'include',
    });
    if (!response.ok) throw new Error('Failed to download transaction history');
    return response.blob();
  }
}

// Export singleton instance
export const paymentService = new PaymentService();

// Export test card numbers for development
export const TEST_CARDS = {
  SUCCESS: '4242424242424242',
  DECLINE: '4000000000000002',
  REQUIRES_3D_SECURE: '4000002500003155',
  INSUFFICIENT_FUNDS: '4000000000009995',
} as const;
