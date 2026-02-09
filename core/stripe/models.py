from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, computed_field


class StripePrice(BaseModel):
    id: str


class StripeSubscriptionItem(BaseModel):
    price: StripePrice


class StripeSubscription(BaseModel):
    id: str
    customer: str
    status: str
    items: dict
    current_period_start: int
    current_period_end: int
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
    def current_period_start_dt(self) -> datetime:
        return datetime.fromtimestamp(self.current_period_start)

    @computed_field
    @property
    def current_period_end_dt(self) -> datetime:
        return datetime.fromtimestamp(self.current_period_end)

    @computed_field
    @property
    def canceled_at_dt(self) -> Optional[datetime]:
        return datetime.fromtimestamp(self.canceled_at) if self.canceled_at else None

    @computed_field
    @property
    def trial_start_dt(self) -> Optional[datetime]:
        return datetime.fromtimestamp(self.trial_start) if self.trial_start else None

    @computed_field
    @property
    def trial_end_dt(self) -> Optional[datetime]:
        return datetime.fromtimestamp(self.trial_end) if self.trial_end else None


class StripeInvoiceLinePrice(BaseModel):
    id: str = ""


class StripeInvoiceLine(BaseModel):
    amount: int  # cents
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
    amount_refunded: int = 0  # cents

    @computed_field
    @property
    def amount_refunded_dollars(self) -> Decimal:
        return Decimal(self.amount_refunded) / 100
