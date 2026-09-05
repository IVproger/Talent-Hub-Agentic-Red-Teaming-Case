"""Configuration errors shared by the legacy pipeline and profile-based core."""


class PipelineConfigurationError(ValueError):
    """The supplied configuration cannot be used to execute a campaign."""
