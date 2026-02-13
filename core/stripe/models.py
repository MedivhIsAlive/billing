from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, computed_field


def _ensure_datetime(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc)


class StripePrice(BaseModel):
    id: str


class StripeSubscriptionItem(BaseModel):
    price: StripePrice


class StripeSubscription(BaseModel):
    id: str
    customer: str
    status: str
    items: dict
    current_period_start: Optional[int] = None
    current_period_end: Optional[int] = None
    cancel_at_period_end: bool = False
    canceled_at: Optional[int] = None
    trial_start: Optional[int] = None
    trial_end: Optional[int] = None

    @computed_field
    @property
    def price_id(self) -> str:
        return self.items["data"][0]["price"]["id"]

    @computed_field
    @property
    def current_period_start_dt(self) -> Optional[datetime]:
        return _ensure_datetime(self.current_period_start) if self.current_period_start else None

    @computed_field
    @property
    def current_period_end_dt(self) -> Optional[datetime]:
        return _ensure_datetime(self.current_period_end) if self.current_period_end else None

    @computed_field
    @property
    def canceled_at_dt(self) -> Optional[datetime]:
        return _ensure_datetime(self.canceled_at) if self.canceled_at else None

    @computed_field
    @property
    def trial_start_dt(self) -> Optional[datetime]:
        return _ensure_datetime(self.trial_start) if self.trial_start else None

    @computed_field
    @property
    def trial_end_dt(self) -> Optional[datetime]:
        return _ensure_datetime(self.trial_end) if self.trial_end else None


class StripeInvoiceLinePrice(BaseModel):
    id: str = ""


class StripeInvoiceLine(BaseModel):
    amount: int
    description: str = ""
    price: Optional[StripeInvoiceLinePrice] = None

    @computed_field
    @property
    def amount_dollars(self) -> Decimal:
        return Decimal(self.amount) / 100

    @computed_field
    @property
    def price_id(self) -> str:
        return self.price.id if self.price else ""


class StripeInvoiceLines(BaseModel):
    data: list[StripeInvoiceLine] = Field(default_factory=list)


class StripeInvoice(BaseModel):
    id: str
    customer: str
    billing_reason: Optional[str] = None
    lines: StripeInvoiceLines = Field(default_factory=StripeInvoiceLines)


class StripeCharge(BaseModel):
    id: str
    invoice: Optional[str] = None
    amount_refunded: int = 0

    @computed_field
    @property
    def amount_refunded_dollars(self) -> Decimal:
        return Decimal(self.amount_refunded) / 100


class StripeCheckoutSession(BaseModel):
    id: str
    customer: Optional[str] = None
    mode: str
    payment_status: str
    subscription: Optional[str] = None
    payment_intent: Optional[str] = None
    amount_total: Optional[int] = None
    currency: Optional[str] = None
    metadata: dict = Field(default_factory=dict)

    @computed_field
    @property
    def amount_total_dollars(self) -> Optional[Decimal]:
        return Decimal(self.amount_total) / 100 if self.amount_total is not None else None


class StripeDispute(BaseModel):
    id: str
    charge: str
    amount: int
    currency: str
    reason: str = ""
    status: str
    payment_intent: Optional[str] = None

    @computed_field
    @property
    def amount_dollars(self) -> Decimal:
        return Decimal(self.amount) / 100


class StripeCustomer(BaseModel):
    id: str
    email: Optional[str] = None
    name: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class StripePaymentIntent(BaseModel):
    id: str
    customer: Optional[str] = None
    invoice: Optional[str] = None
    amount: int = 0
    status: str = ""

    @computed_field
    @property
    def amount_dollars(self) -> Decimal:
        return Decimal(self.amount) / 100
