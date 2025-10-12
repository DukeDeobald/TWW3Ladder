import discord
from discord.ext import commands
from database import Database
from utils.maps import factions

class FactionStats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.channel_id = 1424864456063848608

    async def update_faction_stats_message(self):
        stats = self.db.get_faction_stats()
        channel = self.bot.get_channel(self.channel_id)

        if not channel:
            print(f"Channel with ID {self.channel_id} not found.")
            return

        if not stats:
            await channel.send("No faction stats available yet.")
            return

        message = "**Global Faction Win Rates (Lucky Dice):**\n\n"
        sorted_stats = sorted(stats, key=lambda x: (x[1] / (x[1] + x[2])) if (x[1] + x[2]) > 0 else 0, reverse=True)

        for faction_name, wins, losses in sorted_stats:
            total_games = wins + losses
            win_rate = (wins / total_games) * 100 if total_games > 0 else 0
            message += f"{factions[faction_name]} **{faction_name}** {factions[faction_name]}: {win_rate:.2f}% [ {wins}W / {losses}L ]\n"

        async for msg in channel.history(limit=100):
            if msg.author == self.bot.user:
                await msg.delete()

        await channel.send(message)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def factionstats(self, ctx):
        try:
            await self.update_faction_stats_message()
            await ctx.send(f"Faction stats updated in <#{self.channel_id}>")
        except Exception as e:
            await ctx.send(f"⚠️ Error: `{e}`")

    @commands.Cog.listener()
    async def on_luckydice_match_finished(self):
        await self.update_faction_stats_message()

    @commands.command(aliases=["mfs"])
    async def myfactionstats(self, ctx):
        stats = self.db.get_player_faction_stats(ctx.author.id)

        if not stats:
            await ctx.send("You have no faction stats available yet.")
            return

        message = f"**{ctx.author.display_name}'s Faction Win Rates (Lucky Dice):**\n\n"
        sorted_stats = sorted(stats, key=lambda x: (x[1] / (x[1] + x[2])) if (x[1] + x[2]) > 0 else 0, reverse=True)

        for faction_name, wins, losses in sorted_stats:
            total_games = wins + losses
            win_rate = (wins / total_games) * 100 if total_games > 0 else 0
            message += f"{factions[faction_name]} **{faction_name}** {factions[faction_name]}: {win_rate:.2f}% [ {wins}W / {losses}L ]\n"

        await ctx.send(message)

async def setup(bot):
    await bot.add_cog(FactionStats(bot))