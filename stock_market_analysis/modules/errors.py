"""Custom error types, so the rest of the app can show friendly messages."""


class DataError(Exception):
    """Market data could not be retrieved or is not usable."""


class RateLimitError(DataError):
    """Too many requests were sent to the data provider."""


class ProviderConfigError(DataError):
    """The data provider is not configured correctly (e.g. missing API key)."""
