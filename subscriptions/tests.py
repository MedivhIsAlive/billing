from django.urls import reverse
from django.contrib.auth.models import User, Permission
from rest_framework import status
from rest_framework.test import APITestCase
from subscriptions.models import Subscription, SubscriptionPlan

class BaseSubscriptionTest(APITestCase):
    """
    Base class containing helper functions to reduce code duplication.
    """

    def setUp(self):
        # Create standard users
        self.user_a = self._create_user("user_a", "password123")
        self.user_b = self._create_user("user_b", "password123")
        self.admin_user = self._create_user("admin", "adminpass", is_staff=True)

        # Create plans
        self.basic_plan = self._create_plan(name="Basic", price=10.00)
        self.pro_plan = self._create_plan(name="Pro", price=50.00)

    # --- Helper Functions ---

    def _create_user(self, username, password, is_staff=False):
        user = User.objects.create_user(username=username, password=password)
        if is_staff:
            user.is_staff = True
            user.save()
        return user

    def _create_plan(self, name, price, is_active=True):
        return SubscriptionPlan.objects.create(
            name=name,
            price_monthly=price,
            is_active=is_active
        )

    def _create_subscription(self, user, plan, status="active"):
        return Subscription.objects.create(
            user=user,
            plan=plan,
            status=status
        )

    def _grant_permission(self, user, model_cls, codename):
        """Helper to assign Django permissions dynamically."""
        from django.contrib.contenttypes.models import ContentType
        content_type = ContentType.objects.get_for_model(model_cls)
        permission = Permission.objects.get(
            content_type=content_type,
            codename=codename
        )
        user.user_permissions.add(permission)


class SubscriptionPlanTests(BaseSubscriptionTest):
    """
    Tests for public endpoints: /subscriptions/plans
    """

    def test_list_plans_public(self):
        url = reverse("subscriptions:plans")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)  # Basic + Pro

    def test_filter_plans_by_price(self):
        """Test the 'gte' filter configured in filterset_fields"""
        # Url looks like: /subscriptions/plans?price_monthly__gte=40
        url = reverse("subscriptions:plans")
        response = self.client.get(url, {"price_monthly__gte": 40})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], "Pro")

    def test_search_plans(self):
        """Test the SearchFilter on 'name'"""
        url = reverse("subscriptions:plans")
        response = self.client.get(url, {"search": "Basic"})

        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], "Basic")


class MySubscriptionTests(BaseSubscriptionTest):
    """
    Tests for the 'Me' endpoint: /subscriptions/me/
    """

    def setUp(self):
        super().setUp()
        # Create a subscription for User A only
        self.sub_a = self._create_subscription(self.user_a, self.basic_plan)

    def test_anonymous_access_denied(self):
        url = reverse("subscriptions:me")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_user_can_see_own_subscription(self):
        self.client.force_authenticate(user=self.user_a)
        url = reverse("subscriptions:me")

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], f"{self.sub_a.id}")

    def test_user_cannot_see_others_subscription(self):
        """Crucial security test: User B should not see User A's data"""
        self.client.force_authenticate(user=self.user_b)
        url = reverse("subscriptions:me")

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)  # User B has no subs


class SubscriptionViewSetTests(BaseSubscriptionTest):
    """
    Tests for the administrative ViewSet: /subscriptions/
    """

    def setUp(self):
        super().setUp()
        self.sub_a = self._create_subscription(self.user_a, self.basic_plan)
        self.url_list = reverse("subscriptions:subscription-list")
        self.url_detail = reverse("subscriptions:subscription-detail", args=[self.sub_a.id])

    def test_list_permissions_enforced(self):
        """
        Assuming StrictDjangoModelPermissions requires 'view_subscription'
        or generally staff status depending on implementation.
        """
        # 1. Anonymous -> 401/403
        response = self.client.get(self.url_list)
        self.assertTrue(response.status_code in [401, 403])

        # 2. Regular User -> 403 (Standard DjangoModelPermissions behavior)
        self.client.force_authenticate(user=self.user_a)
        response = self.client.get(self.url_list)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_view_all(self):
        """
        Admin with permissions should see all subscriptions.
        """
        self.client.force_authenticate(user=self.admin_user)
        # Grant the django 'view_subscription' permission to the admin
        self._grant_permission(self.admin_user, Subscription, "view_subscription")

        response = self.client.get(self.url_list)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should see subscription created in setUp
        self.assertGreaterEqual(len(response.data), 1)

    def test_filter_by_status(self):
        """Test exact match filtering on status"""
        # Create a canceled sub to test against
        self._create_subscription(self.user_b, self.pro_plan, status="canceled")

        self.client.force_authenticate(user=self.admin_user)
        self._grant_permission(self.admin_user, Subscription, "view_subscription")

        # Filter for 'canceled'
        response = self.client.get(self.url_list, {"status": "canceled"})

        print(response.text)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # We should only find the one we just created
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["status"], "canceled")
