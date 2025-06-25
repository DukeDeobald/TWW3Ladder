
from discord.ext import commands

class CustomError(commands.CommandError):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

class NotInQueueError(CustomError):
    pass

class AlreadyInQueueError(CustomError):
    pass

class NotInMatchError(CustomError):
    pass

class AlreadyInMatchError(CustomError):
    pass

class InvalidModeError(CustomError):
    pass

class InsufficientFundsError(CustomError):
    pass
