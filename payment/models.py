from django.db import models
from django_fsm import FSMField, transition


class InvoiceStatus(models.TextChoices):
    UNPAID = "UNPAID", "Unpaid"
    PAID = "PAID", "Paid"


class Invoice(models.Model):
    state = FSMField(default="new")

    PAID = "PAID", "Paid"
    PAID = "PAID", "Paid"
