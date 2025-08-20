import { logger } from '@/lib/logger';

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
  payment_method_id: string;
  save_payment_method?: boolean;
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
  period_start?: string;
  period_end?: string;
}

class PaymentService {
  private baseUrl = '/api/payments';

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const token = localStorage.getItem('token');

    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': token ? `Bearer ${token}` : '',
        ...options.headers,
      },
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Request failed' }));
      throw new Error(error.detail || `Request failed with status ${response.status}`);
    }

    return response.json();
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
