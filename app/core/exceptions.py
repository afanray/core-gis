from typing import Any, Optional, Dict

class AppException(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Optional[Any] = None
    ):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)

class NotFoundException(AppException):
    def __init__(self, message: str = "Resource not found", details: Optional[Any] = None):
        super().__init__(status_code=404, code="NOT_FOUND", message=message, details=details)

class AuthenticationException(AppException):
    def __init__(self, message: str = "Authentication failed", details: Optional[Any] = None):
        super().__init__(status_code=401, code="UNAUTHENTICATED", message=message, details=details)

class ForbiddenException(AppException):
    def __init__(self, message: str = "Permission denied", details: Optional[Any] = None):
        super().__init__(status_code=403, code="FORBIDDEN", message=message, details=details)

class ConflictException(AppException):
    def __init__(self, message: str = "Resource conflict", details: Optional[Any] = None):
        super().__init__(status_code=409, code="CONFLICT", message=message, details=details)

class ValidationException(AppException):
    def __init__(self, message: str = "Validation error", details: Optional[Any] = None):
        super().__init__(status_code=422, code="VALIDATION_ERROR", message=message, details=details)

class RateLimitException(AppException):
    def __init__(self, message: str = "Rate limit exceeded", details: Optional[Any] = None):
        super().__init__(status_code=429, code="RATE_LIMIT_EXCEEDED", message=message, details=details)
