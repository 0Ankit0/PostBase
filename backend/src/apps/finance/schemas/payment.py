"""
Payment schemas — request/response validation for the finance API.
Includes generic schemas usable across all providers, plus provider-specific
schemas for Khalti and eSewa.
"""
from typing import Any, Optional
from pydantic import BaseModel, model_validator, field_serializer, field_validator

from src.apps.finance.models.payment import PaymentProvider, PaymentStatus
from src.apps.iam.utils.hashid import decode_id, encode_id


# ---------------------------------------------------------------------------
# Generic / provider-agnostic schemas
# ---------------------------------------------------------------------------

class InitiatePaymentRequest(BaseModel):
    """Request body to initiate a payment regardless of provider."""
    provider: PaymentProvider
    amount: int  # canonical contract: smallest currency unit (e.g. paisa/cents)
    currency: str
    purchase_order_id: str
    purchase_order_name: str
    return_url: str
    website_url: str = ""
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    customer_phone: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("amount must be a positive integer (in smallest currency unit)")
        return v

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        currency = value.strip().upper()
        if len(currency) != 3 or not currency.isalpha():
            raise ValueError("currency must be a valid 3-letter ISO 4217 code")
        return currency

    @model_validator(mode="after")
    def validate_provider_constraints(self) -> "InitiatePaymentRequest":
        accepted_currency_by_provider: dict[PaymentProvider, set[str]] = {
            PaymentProvider.KHALTI: {"NPR"},
            PaymentProvider.ESEWA: {"NPR"},
            PaymentProvider.STRIPE: {"USD"},
            PaymentProvider.PAYPAL: {"USD"},
        }
        minimum_minor_units_by_provider: dict[PaymentProvider, int] = {
            PaymentProvider.KHALTI: 1000,
            PaymentProvider.ESEWA: 1,
            PaymentProvider.STRIPE: 50,
            PaymentProvider.PAYPAL: 1,
        }

        accepted = accepted_currency_by_provider.get(self.provider, set())
        if accepted and self.currency not in accepted:
            allowed = ", ".join(sorted(accepted))
            raise ValueError(f"{self.provider.value} only supports currency: {allowed}")

        minimum = minimum_minor_units_by_provider.get(self.provider)
        if minimum is not None and self.amount < minimum:
            raise ValueError(
                f"{self.provider.value} amount must be at least {minimum} in minor units."
            )
        return self


class InitiatePaymentResponse(BaseModel):
    """Response after successfully initiating a payment."""
    transaction_id: int          # our internal DB id
    provider: PaymentProvider
    status: PaymentStatus
    amount: int
    currency: str
    payment_url: Optional[str] = None   # URL to redirect the user to
    provider_pidx: Optional[str] = None # Khalti pidx / eSewa ref
    extra: Optional[dict[str, Any]] = None  # provider-specific extras

    @field_serializer("transaction_id")
    def serialize_transaction_id(self, value: int) -> str:
        return encode_id(value)


class VerifyPaymentRequest(BaseModel):
    """Request body to verify / confirm a payment callback."""
    provider: PaymentProvider
    currency: str
    pidx: Optional[str] = None          # Khalti uses pidx
    oid: Optional[str] = None           # eSewa uses oid (our purchase_order_id)
    refId: Optional[str] = None         # eSewa legacy refId
    # eSewa v2 passes a base64-encoded `data` query param from callback
    data: Optional[str] = None
    transaction_id: Optional[int] = None  # our internal transaction id

    @field_validator("transaction_id", mode="before")
    @classmethod
    def decode_transaction_id(cls, value: int | str | None) -> int | None:
        if isinstance(value, str):
            decoded = decode_id(value)
            if decoded is None:
                raise ValueError("Invalid transaction_id")
            return decoded
        return value

    @field_validator("currency")
    @classmethod
    def normalize_verify_currency(cls, value: str) -> str:
        currency = value.strip().upper()
        if len(currency) != 3 or not currency.isalpha():
            raise ValueError("currency must be a valid 3-letter ISO 4217 code")
        return currency


class VerifyPaymentResponse(BaseModel):
    """Normalised verification response from any provider."""
    transaction_id: int
    provider: PaymentProvider
    status: PaymentStatus
    amount: Optional[int] = None
    currency: Optional[str] = None
    provider_transaction_id: Optional[str] = None
    extra: Optional[dict[str, Any]] = None

    @field_serializer("transaction_id")
    def serialize_transaction_id(self, value: int) -> str:
        return encode_id(value)


class PaymentTransactionRead(BaseModel):
    """Read schema for a stored PaymentTransaction (used in GET endpoints)."""
    id: int
    provider: PaymentProvider
    status: PaymentStatus
    amount: int
    currency: str
    purchase_order_id: str
    purchase_order_name: str
    provider_transaction_id: Optional[str]
    provider_pidx: Optional[str]
    return_url: str
    website_url: str
    failure_reason: Optional[str]

    model_config = {"from_attributes": True}

    @field_serializer("id")
    def serialize_id(self, value: int) -> str:
        return encode_id(value)


# ---------------------------------------------------------------------------
# Khalti-specific schemas (v2 API)
# ---------------------------------------------------------------------------

class KhaltiInitiateRequest(BaseModel):
    """Payload sent to Khalti /epayment/initiate/ endpoint."""
    return_url: str
    website_url: str
    amount: int
    purchase_order_id: str
    purchase_order_name: str
    customer_info: Optional[dict[str, str]] = None


class KhaltiInitiateResponse(BaseModel):
    """Response from Khalti /epayment/initiate/."""
    pidx: str
    payment_url: str
    expires_at: Optional[str] = None
    expires_in: Optional[int] = None


class KhaltiLookupRequest(BaseModel):
    """Payload sent to Khalti /epayment/lookup/."""
    pidx: str


class KhaltiLookupResponse(BaseModel):
    """Response from Khalti /epayment/lookup/."""
    pidx: str
    total_amount: int
    status: str          # Completed | Pending | Expired | User canceled
    transaction_id: Optional[str] = None
    fee: Optional[int] = None
    refunded: bool = False


# ---------------------------------------------------------------------------
# eSewa-specific schemas (v2 API)
# ---------------------------------------------------------------------------

class EsewaInitiateData(BaseModel):
    """
    Fields required to build the eSewa v2 form POST.
    The merchant must compute the HMAC-SHA256 signature before submitting.
    """
    amount: int                  # in paisa  (e.g. 100 = 1 NPR? No, eSewa uses rupees directly)
    tax_amount: int = 0
    total_amount: int
    transaction_uuid: str        # our unique order id
    product_code: str            # merchant code e.g. EPAYTEST
    product_service_charge: int = 0
    product_delivery_charge: int = 0
    success_url: str
    failure_url: str
    signed_field_names: str = "total_amount,transaction_uuid,product_code"
    signature: str               # HMAC-SHA256 of signed_field_names values


class EsewaCallbackData(BaseModel):
    """
    Decoded payload from eSewa's base64-encoded callback `data` param.
    eSewa sends this to success_url?data=<base64>
    """
    transaction_code: Optional[str] = None
    status: Optional[str] = None           # COMPLETE / PENDING / FULL_REFUND
    total_amount: Optional[str] = None
    transaction_uuid: Optional[str] = None
    product_code: Optional[str] = None
    signed_field_names: Optional[str] = None
    signature: Optional[str] = None
