"""Registry for webhook providers (WhatsApp, Meta, etc.)."""

from app.modules.integrations.protocols import WebhookProvider

_providers: dict[str, WebhookProvider] = {}


def register_provider(provider: WebhookProvider) -> None:
    """Register a WebhookProvider implementation."""
    _providers[provider.name] = provider


def get_provider(name: str) -> WebhookProvider | None:
    """Retrieve a registered provider by name (e.g. 'whatsapp', 'meta')."""
    return _providers.get(name)

