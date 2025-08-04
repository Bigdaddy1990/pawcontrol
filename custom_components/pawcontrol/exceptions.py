"""Exceptions for Paw Control integration."""


class PawControlError(Exception):
    """Base exception for Paw Control."""
    pass


class InvalidCoordinates(PawControlError):
    """Exception for invalid GPS coordinates."""
    pass


class DataValidationError(PawControlError):
    """Exception for data validation errors."""
    pass


class EntityCreationError(PawControlError):
    """Exception for entity creation errors."""
    pass


class ServiceCallError(PawControlError):
    """Exception for service call errors."""
    pass