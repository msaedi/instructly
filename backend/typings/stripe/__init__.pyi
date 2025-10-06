from typing import Any, Dict, List, Optional

api_key: Optional[str]
default_http_client: Any
max_network_retries: int
verify_ssl_certs: bool

class StripeError(Exception): ...

class SignatureVerificationError(StripeError): ...

class AuthenticationError(StripeError): ...

class CardError(StripeError):
    user_message: Optional[str]
    code: Optional[str]

class InvalidRequestError(StripeError): ...

class error:
    AuthenticationError = AuthenticationError
    CardError = CardError
    SignatureVerificationError = SignatureVerificationError
    InvalidRequestError = InvalidRequestError

class _IdentitySession:
    id: Optional[str]
    client_secret: Optional[str]
    metadata: Dict[str, Any]
    created: int
    status: Optional[str]

class _IdentitySessionList(Dict[str, Any]):
    data: List[_IdentitySession]

class identity:
    class VerificationSession:
        @staticmethod
        def create(**kwargs: Any) -> _IdentitySession: ...

        @staticmethod
        def list(**kwargs: Any) -> _IdentitySessionList: ...

class _Customer:
    id: str

class Customer:
    @staticmethod
    def create(**kwargs: Any) -> _Customer: ...

class _Account:
    id: str
    requirements: Dict[str, Any]

class Account:
    @staticmethod
    def create(**kwargs: Any) -> _Account: ...

    @staticmethod
    def modify(account_id: str, **kwargs: Any) -> _Account: ...

    @staticmethod
    def retrieve(account_id: str) -> _Account: ...

    @staticmethod
    def create_login_link(account_id: str, **kwargs: Any) -> Dict[str, Any]: ...

class _AccountLink:
    url: str
    expires_at: int

class AccountLink:
    @staticmethod
    def create(**kwargs: Any) -> _AccountLink: ...

class _PaymentIntent(Dict[str, Any]):
    id: str
    status: str
    client_secret: Optional[str]
    amount: Optional[int]
    amount_received: Optional[int]
    application_fee_amount: Optional[int]

class PaymentIntent:
    @staticmethod
    def create(**kwargs: Any) -> _PaymentIntent: ...

    @staticmethod
    def confirm(payment_intent_id: str, **kwargs: Any) -> _PaymentIntent: ...

    @staticmethod
    def capture(payment_intent_id: str, *, idempotency_key: Optional[str] = ...) -> _PaymentIntent: ...

    @staticmethod
    def cancel(payment_intent_id: str, *, idempotency_key: Optional[str] = ...) -> _PaymentIntent: ...

    @staticmethod
    def retrieve(payment_intent_id: str) -> _PaymentIntent: ...

class _CardDetails:
    last4: Optional[str]
    brand: Optional[str]


class _PaymentMethod(Dict[str, Any]):
    id: str
    customer: Optional[str]
    card: Optional[_CardDetails]

class PaymentMethod:
    @staticmethod
    def retrieve(payment_method_id: str) -> _PaymentMethod: ...

    @staticmethod
    def attach(payment_method_id: str, **kwargs: Any) -> _PaymentMethod: ...

    @staticmethod
    def detach(payment_method_id: str) -> _PaymentMethod: ...

class _TransferReversal(Dict[str, Any]):
    id: str

class Transfer:
    @staticmethod
    def create_reversal(transfer_id: str, **kwargs: Any) -> _TransferReversal: ...

class Payout:
    id: str
    status: str

    @staticmethod
    def create(**kwargs: Any) -> "Payout": ...


class SetupIntent:
    id: str
    status: str
    client_secret: Optional[str]

    @staticmethod
    def create(**kwargs: Any) -> "SetupIntent": ...

class Webhook:
    @staticmethod
    def construct_event(payload: str | bytes, sig_header: str, secret: str) -> Dict[str, Any]: ...

class http_client:
    class RequestsClient:
        def __init__(self, timeout: int) -> None: ...
