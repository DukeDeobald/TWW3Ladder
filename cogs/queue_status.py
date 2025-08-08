import discord
from discord.ext import commands, tasks
from database import Database
from utils.config import QUEUE_STATUS_CHANNEL_ID
from utils.maps import REVERSE_MODE_MAP

class QueueStatus(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.reverse_mode_map = REVERSE_MODE_MAP
        self.update_queue_status_message.start()

    def cog_unload(self):
        self.update_queue_status_message.cancel()

    @tasks.loop(seconds=15)
    async def update_queue_status_message(self):
        channel = self.bot.get_channel(QUEUE_STATUS_CHANNEL_ID)
        if not channel:
            return

        embed = discord.Embed(title="Current Queue Status", color=discord.Color.blue())

        for game_mode_id, mode_name in self.reverse_mode_map.items():
            queue_players = self.db.get_queue_players(game_mode_id)
            player_names = []
            for player_id in queue_players:
                try:
                    user = await self.bot.fetch_user(player_id[0])
                    player_names.append(user.display_name)
                except discord.NotFound:
                    player_names.append(f"Player {player_id[0]}")
            
            if player_names:
                embed.add_field(name=f"{mode_name.capitalize()} ({len(player_names)})", value="\n".join(player_names), inline=False)
            else:
                embed.add_field(name=f"{mode_name.capitalize()} (0)", value="No players in queue", inline=False)

        try:
            async for message in channel.history(limit=1):
                if message.author == self.bot.user:
                    await message.edit(embed=embed)
                    return
            await channel.send(embed=embed)
        except Exception as e:
            print(f"Error updating queue status message: {e}")

    @update_queue_status_message.before_loop
    async def before_update_queue_status_message(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(QueueStatus(bot))
