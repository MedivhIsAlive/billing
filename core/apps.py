from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        # Explicit imports — each one registers handlers via __init_subclass__.
        # 4 lines is a feature, not boilerplate. If any import fails,
        # the app crashes at startup, not at 3am when a webhook arrives.
        import subscriptions.stripe_handlers  # noqa: F401
        import purchases.stripe_handlers      # noqa: F401
        import accounts.stripe_handlers       # noqa: F401
