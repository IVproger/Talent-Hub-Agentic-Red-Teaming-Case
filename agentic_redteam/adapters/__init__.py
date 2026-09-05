"""Target transport contracts and implementations."""

from .base import (
    AdapterFeature, Principal, TargetAdapter, TargetSession, TargetUnavailable,
    UnsupportedFeature,
)

__all__ = [
    "AdapterFeature", "Principal", "TargetAdapter", "TargetSession",
    "TargetUnavailable", "UnsupportedFeature",
]
