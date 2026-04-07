"""aiohttp client exception compatibility shim."""


class ClientError(Exception):
    """Base client transport error."""


class ContentTypeError(ClientError):
    """Raised when payload content type is not JSON."""
