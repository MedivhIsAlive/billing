from django.test import TestCase
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from accounts.models import Customer

User = get_user_model()


class CustomerUniqueConstraintsTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="user@example.com", password="pass123"
        )

    def test_duplicate_stripe_customer_id_rejected(self):
        Customer.objects.create(user=self.user, stripe_customer_id="cus_unique")
        user2 = User.objects.create_user(username="user2", email="u2@example.com", password="pass")
        with self.assertRaises(IntegrityError):
            Customer.objects.create(user=user2, stripe_customer_id="cus_unique")

    def test_duplicate_user_rejected(self):
        Customer.objects.create(user=self.user)
        with self.assertRaises(IntegrityError):
            Customer.objects.create(user=self.user)
