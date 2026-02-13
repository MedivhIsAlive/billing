from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from entitlement.models import Entitlement, GrantedBy
from entitlement import services as entitlement_services
from testing_utils import make_customer, make_subscription


class EntitlementValidityTest(TestCase):

    def setUp(self):
        self.customer = make_customer()

    def test_revoke_sets_fields_and_invalidates(self):
        ent = Entitlement.objects.create(customer=self.customer, feature="pro")
        ent.revoke(reason="Test revocation")
        ent.refresh_from_db()
        self.assertFalse(ent.is_active)
        self.assertFalse(ent.is_valid)
        self.assertEqual(ent.revoke_reason, "Test revocation")
        self.assertIsNotNone(ent.revoked_at)

    def test_increment_usage_atomically(self):
        ent = Entitlement.objects.create(
            customer=self.customer,
            feature="api_calls",
            usage_limit=5,
            usage_count=0,
        )
        result = ent.increment_usage()
        self.assertTrue(result)
        ent.refresh_from_db()
        self.assertEqual(ent.usage_count, 1)

    def test_increment_usage_blocked_at_limit(self):
        ent = Entitlement.objects.create(
            customer=self.customer,
            feature="api_calls",
            usage_limit=1,
            usage_count=1,
        )
        result = ent.increment_usage()
        self.assertFalse(result)


class EntitlementQuerySetTest(TestCase):

    def setUp(self):
        self.customer = make_customer()

    def test_active_excludes_revoked_and_expired(self):
        Entitlement.objects.create(customer=self.customer, feature="active_feat")
        Entitlement.objects.create(customer=self.customer, feature="revoked", is_active=False)
        Entitlement.objects.create(
            customer=self.customer,
            feature="expired",
            expires_at=timezone.now() - timedelta(days=1),
        )
        active = Entitlement.objects.active()
        self.assertEqual(active.count(), 1)
        self.assertEqual(active.first().feature, "active_feat")

    def test_revoke_all_bulk(self):
        Entitlement.objects.create(customer=self.customer, feature="feat1")
        Entitlement.objects.create(customer=self.customer, feature="feat2")
        Entitlement.objects.all().revoke_all(reason="bulk")
        self.assertEqual(Entitlement.objects.filter(is_active=True).count(), 0)
        self.assertTrue(all(e.revoke_reason == "bulk" for e in Entitlement.objects.all()))


class EntitlementServicesTest(TestCase):

    def setUp(self):
        self.customer = make_customer()

    def test_has_access_true(self):
        Entitlement.objects.create(customer=self.customer, feature="pro")
        self.assertTrue(entitlement_services.has_access(self.customer, "pro"))

    def test_has_access_false_when_revoked(self):
        Entitlement.objects.create(customer=self.customer, feature="pro", is_active=False)
        self.assertFalse(entitlement_services.has_access(self.customer, "pro"))

    def test_has_access_false_when_missing(self):
        self.assertFalse(entitlement_services.has_access(self.customer, "nonexistent"))

    def test_get_active_entitlements(self):
        Entitlement.objects.create(customer=self.customer, feature="pro")
        Entitlement.objects.create(customer=self.customer, feature="api_access")
        Entitlement.objects.create(customer=self.customer, feature="revoked", is_active=False)
        active = entitlement_services.get_active_entitlements(self.customer)
        self.assertEqual(sorted(active), ["api_access", "pro"])

    def test_grant_creates_entitlement(self):
        ent = entitlement_services.grant(self.customer, "new_feature")
        self.assertEqual(ent.feature, "new_feature")
        self.assertTrue(ent.is_active)

    def test_grant_reactivates_revoked(self):
        ent = entitlement_services.grant(self.customer, "feature")
        ent.revoke(reason="test")
        ent2 = entitlement_services.grant(self.customer, "feature")
        self.assertTrue(ent2.is_active)
        self.assertEqual(ent.pk, ent2.pk)

    def test_grant_trial(self):
        ent = entitlement_services.grant_trial(self.customer, "trial_feat", days=7)
        self.assertEqual(ent.granted_by, GrantedBy.TRIAL)
        self.assertIsNotNone(ent.expires_at)

    def test_revoke_feature(self):
        Entitlement.objects.create(customer=self.customer, feature="pro")
        count = entitlement_services.revoke(self.customer, "pro", reason="canceled")
        self.assertEqual(count, 1)
        self.assertFalse(entitlement_services.has_access(self.customer, "pro"))

    def test_sync_from_subscription_adds_and_removes(self):
        sub = make_subscription(customer=self.customer)

        entitlement_services.sync_from_subscription(sub, ["pro", "api_access"])
        self.assertEqual(Entitlement.objects.filter(subscription=sub, is_active=True).count(), 2)

        entitlement_services.sync_from_subscription(sub, ["pro", "priority_support"])
        active = set(
            Entitlement.objects.filter(subscription=sub, is_active=True).values_list("feature", flat=True)
        )
        self.assertEqual(active, {"pro", "priority_support"})
        api_ent = Entitlement.objects.get(subscription=sub, feature="api_access")
        self.assertFalse(api_ent.is_active)

    def test_revoke_for_subscription(self):
        sub = make_subscription(customer=self.customer)
        entitlement_services.sync_from_subscription(sub, ["pro", "api_access"])

        count = entitlement_services.revoke_for_subscription(sub, reason="canceled")
        self.assertEqual(count, 2)
        self.assertEqual(Entitlement.objects.filter(subscription=sub, is_active=True).count(), 0)
