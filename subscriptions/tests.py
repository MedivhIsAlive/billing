from datetime import timedelta
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from subscriptions.models import SubscriptionStatus
from testing_utils import make_customer, make_subscription, make_user

User = get_user_model()


class MySubscriptionViewTest(TestCase):

    def setUp(self):
        self.user_a = make_user(email="a@test.com", username="user_a")
        self.user_b = make_user(email="b@test.com", username="user_b")
        self.customer_a = make_customer(user=self.user_a, stripe_customer_id="cus_a")
        self.customer_b = make_customer(user=self.user_b, stripe_customer_id="cus_b")

        self.sub_a = make_subscription(
            customer=self.customer_a, stripe_subscription_id="sub_a",
        )
        self.sub_b = make_subscription(
            customer=self.customer_b, stripe_subscription_id="sub_b",
        )
        self.client: APIClient = APIClient()

    def test_returns_only_own_subscriptions(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.get("/api/subscriptions/me/")
        self.assertEqual(response.status_code, 200)

        ids = [s["stripe_subscription_id"] for s in response.data["results"]]
        self.assertIn("sub_a", ids)
        self.assertNotIn("sub_b", ids)

    def test_returns_empty_for_user_with_no_subscriptions(self):
        user_c = make_user(email="c@test.com", username="user_c")
        self.client.force_authenticate(user=user_c)
        response = self.client.get("/api/subscriptions/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], [])

    def test_rejects_unauthenticated(self):
        response = self.client.get("/api/subscriptions/me/")
        self.assertEqual(response.status_code, 403)


class AdminSubscriptionViewSetTest(TestCase):
    def setUp(self):
        self.admin = make_user(email="admin@test.com", username="admin")
        self.regular = make_user(email="regular@test.com", username="regular")
        self.customer = make_customer(
            user=make_user(email="sub@test.com", username="subuser"),
            stripe_customer_id="cus_admin_test",
        )
        make_subscription(customer=self.customer, stripe_subscription_id="sub_admin")

        perm = Permission.objects.get(
            codename="view_subscription",
            content_type__app_label="subscriptions",
        )
        self.admin.user_permissions.add(perm)

        self.client: APIClient = APIClient()

    def test_admin_with_permission_can_list(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get("/api/subscriptions/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)

    def test_user_without_permission_is_denied(self):
        self.client.force_authenticate(user=self.regular)
        response = self.client.get("/api/subscriptions/")
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_is_denied(self):
        response = self.client.get("/api/subscriptions/")
        self.assertEqual(response.status_code, 403)

    def test_filter_by_status(self):
        make_subscription(
            customer=self.customer,
            stripe_subscription_id="sub_canceled",
            status=SubscriptionStatus.CANCELED,
        )
        self.client.force_authenticate(user=self.admin)

        response = self.client.get("/api/subscriptions/", {"status": "active"})
        ids = [s["stripe_subscription_id"] for s in response.data["results"]]
        self.assertIn("sub_admin", ids)
        self.assertNotIn("sub_canceled", ids)

    def test_viewset_is_read_only(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post("/api/subscriptions/", {})
        self.assertIn(response.status_code, [403, 405])
