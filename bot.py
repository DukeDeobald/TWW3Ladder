import discord
from discord.ext import commands
import asyncio
import os
import os
from utils import config
from utils.errors import CustomError

class TWWLadderBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)
        self.config = config

    async def setup_hook(self):
        cogs_folder = "cogs"
        for filename in os.listdir(cogs_folder):
            if filename.endswith(".py"):
                await self.load_extension(f'{cogs_folder}.{filename[:-3]}')
        print("Cogs loaded.")

    async def on_command_error(self, ctx, error):
        if isinstance(error, CustomError):
            await ctx.send(error.message)
        elif isinstance(error, commands.CommandNotFound):
            await ctx.send("Invalid command.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Missing required argument.")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("Invalid argument.")
        elif isinstance(error, commands.CheckFailure):
            await ctx.send("You do not have permission to use this command.")
        else:
            print(f"Unhandled error: {error}")
            await ctx.send("An unexpected error occurred.")

async def main():
    bot = TWWLadderBot()
    await bot.start(bot.config.TOKEN)

if __name__ == "__main__":
    asyncio.run(main())