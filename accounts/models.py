from django.conf import settings
from django.db import models


class Customer(models.Model):
    # you if you wanna add b2b, all you have to do is swap 121 with foreign key and add org model
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="customer")

    stripe_customer_id = models.CharField(max_length=255, unique=True, null=True, blank=True, db_index=True)

    billing_email = models.EmailField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "customers"

    def __str__(self):
        return self.user.email or self.user.username

    @property
    def email(self) -> str:
        return self.billing_email or self.user.email
