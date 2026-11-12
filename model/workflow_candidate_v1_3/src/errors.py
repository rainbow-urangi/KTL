"""Only fixed product validation reasons may be emitted by the CLI."""


class ValidationError(ValueError):
    def __init__(self, code, reason):
        super().__init__(reason)
        self.code = code
        self.safe_reason = reason
