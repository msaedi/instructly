import { logger } from '@/lib/logger';
import { withApiBase, withApiBaseForRequest } from '@/lib/apiBase';
import { fetchWithSessionRefresh } from '@/lib/auth/sessionRefresh';
import { httpGet, httpPost } from '@/lib/http';
import type { CheckoutResponse } from '@/types/api/checkout';
import type {
  PaymentMethod,
  SavePaymentMethodRequest,
  CreateCheckoutRequest,
  Transaction,
  OnboardingResponse,
  OnboardingStatusResponse,
  EarningsResponse,
  InstructorInvoice,
  PayoutSummary,
  PayoutHistoryResponse,
} from '@/features/shared/api/types';

// Re-export types for convenience
export type {
  PaymentMethod,
  SavePaymentMethodRequest,
  CreateCheckoutRequest,
  Transaction,
  OnboardingResponse,
  OnboardingStatusResponse,
  EarningsResponse,
  InstructorInvoice,
  PayoutSummary,
  PayoutHistoryResponse,
};

class PaymentService {
  private basePath = `/api/v1/payments`;

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const method = (options.method || 'GET').toUpperCase();
    const url = withApiBaseForRequest(`${this.basePath}${endpoint}`, method);
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
    const response = await fetchWithSessionRefresh(withApiBase(`${this.basePath}/transactions/download`), {
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
