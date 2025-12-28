export interface CheckoutResponse {
  success: boolean;
  payment_intent_id: string;
  status: string;
  amount: number;
  application_fee: number;
  client_secret?: string | null;
  requires_action?: boolean;
}
