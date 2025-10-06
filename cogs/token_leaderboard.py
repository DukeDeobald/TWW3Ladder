
import discord
from discord.ext import commands
from database import Database

class TokenLeaderboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()

    @commands.command(aliases=["tb", "tokenboard"])
    async def token_leaderboard(self, ctx):
        leaderboard_data = self.db.get_token_leaderboard()

        if not leaderboard_data:
            await ctx.send("The token leaderboard is currently empty.")
            return

        embed = discord.Embed(title="Token Leaderboard", color=discord.Color.gold())
        
        for rank, (discord_id, tokens) in enumerate(leaderboard_data, start=1):
            try:
                user = await self.bot.fetch_user(discord_id)
                embed.add_field(name=f"#{rank} {user.name}", value=f"{tokens} tokens", inline=False)
            except discord.NotFound:
                embed.add_field(name=f"#{rank} Unknown User ({discord_id})", value=f"{tokens} tokens", inline=False)

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(TokenLeaderboard(bot))
