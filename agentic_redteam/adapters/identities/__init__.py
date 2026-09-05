"""Profile-configured identity acquisition at the target boundary."""

from .base import Credential, IdentityProvider
from .static import StaticIdentityProvider

__all__ = ["Credential", "IdentityProvider", "StaticIdentityProvider"]
