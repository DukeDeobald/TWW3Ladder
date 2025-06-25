

import discord
from discord.ext import commands
import matplotlib.pyplot as plt
import io
import seaborn as sns
import pandas as pd
from database import Database

from utils.maps import MODE_MAP, REVERSE_MODE_MAP

class Leaderboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.mode_map = MODE_MAP
        self.reverse_mode_map = REVERSE_MODE_MAP

    @commands.command(aliases=["lb", "leaderboard", "top"])
    async def leaders(self, ctx, mode: str = " "):
        mode_map = {"l": "land", "c": "conquest", "d": "domination", "ld": "luckydice"}
        mode = mode_map.get(mode.lower(), mode.lower())

        if mode not in ["land", "conquest", "domination", "luckydice"]:
            return await ctx.send(f"Invalid mode. Valid modes: {', '.join(mode_map.values())}")

        GameModeID = self.mode_map.get(mode)
        if not GameModeID:
            return await ctx.send("Invalid mode.")

        try:
            leaderboard = self.db.get_leaderboard(GameModeID)
            if not leaderboard:
                return await ctx.send(f"The leaderboard for {mode} mode is empty.")

            response = [f"🏆 **Top players ({mode})**"]

            for idx, (player_id, elo, matches, wins) in enumerate(leaderboard[:10], 1):
                try:
                    user = await self.bot.fetch_user(player_id)
                    display_name = user.display_name
                except discord.NotFound:
                    display_name = f"Player {player_id}"

                if matches > 0:
                    win_rate = round((wins / matches) * 100, 1)
                else:
                    win_rate = 0

                response.append(
                    f"{idx}. {display_name} - **{int(elo)}** ELO | 🏅 WR: **{win_rate}%** ({wins} / {matches})"
                )

            await ctx.send("\n".join(response))
        except (discord.HTTPException, discord.Forbidden) as e:
            await ctx.send(f"Error fetching leaderboard: {e}")
        except Exception as e:
            await ctx.send(f"An unexpected error occurred while fetching the leaderboard: {e}")

    @commands.command(aliases=["h"])
    async def history(self, ctx, limit: int = 11):
        try:
            matches = self.db.get_match_history(ctx.author.id, limit)
            if not matches:
                return await ctx.send("Match history is empty.")

            player_ids = set()
            for match in matches:
                player_ids.update([match[0], match[1], match[2]])

            users = {}
            for player_id in player_ids:
                if player_id is None:
                    continue
                try:
                    user = await self.bot.fetch_user(player_id)
                    users[player_id] = user.display_name
                except discord.NotFound:
                    users[player_id] = f"Player {player_id}"
                except discord.HTTPException as e:
                    print(f"Error fetching user {player_id}: {e}")
                    users[player_id] = f"Player {player_id}"

            response = ["📜 **Recent matches**"]
            for player1_discord_id, player2_discord_id, winner_discord_id, GameModeID, elo_before_winner, elo_after_winner, elo_before_loser, elo_after_loser in matches:
                if player1_discord_id is None or player2_discord_id is None or winner_discord_id is None:
                    continue

                player1_name = users.get(player1_discord_id, f"Player {player1_discord_id}")
                player2_name = users.get(player2_discord_id, f"Player {player2_discord_id}")

                result = "Win" if winner_discord_id == ctx.author.id else "Loss"
                mode_name = self.reverse_mode_map.get(GameModeID, "Unknown Mode")
                elo_change = elo_after_winner - elo_before_winner if winner_discord_id == ctx.author.id else elo_after_loser - elo_before_loser
                entry = (
                    f"- {mode_name}: {player1_name} vs {player2_name} | "
                    f"{result} ({elo_change} ELO)"
                )
                response.append(entry)

            await ctx.send("\n".join(response[:limit]))
        except Exception as e:
            await ctx.send(f"Error fetching history: {str(e)}")

    @commands.command(aliases=["elo"])
    async def elo_graph_cmd(self, ctx, mode: str = None):
        try:
            if mode is None:
                await ctx.send("Please specify a mode ('land', 'conquest', 'domination' or 'luckydice').")
                return

            mode = mode.lower()
            mode_map = {
                "land": 1, "l": 1,
                "conquest": 2, "c": 2,
                "domination": 3, "d": 3,
                "luckydice": 4, "ld": 4
            }

            GameModeID = mode_map.get(mode)
            if not GameModeID:
                await ctx.send(f"Invalid mode. Valid modes: {', '.join(mode_map.keys())}")
                return

            full_mode_name = {
                "l": "land",
                "c": "conquest",
                "d": "domination",
                "lt": "lucky-test"
            }.get(mode, mode)

            elo_data = self.db.get_player_elo_history(ctx.author.id, GameModeID)
            print(f"ELO data for {ctx.author.id} in GameModeID {GameModeID}: {elo_data}")

            if not elo_data:
                await ctx.send(f"No ELO history found for this player in {full_mode_name.capitalize()} mode.")
                return

            df = pd.DataFrame(elo_data, columns=["timestamp", "elo"])
            df["timestamp"] = pd.to_datetime(df["timestamp"])

            sns.set(style="darkgrid", context="talk")
            plt.style.use("dark_background")
            plt.rcParams.update({"grid.linewidth": 0.5, "grid.alpha": 0.5})
            plt.figure(figsize=(10, 5))

            ax = sns.lineplot(x=df["timestamp"], y=df["elo"], marker="o", linewidth=2, color="royalblue")
            ax.set_title(f"ELO Trend for {ctx.author.name} in {full_mode_name.capitalize()} Mode", fontsize=14)
            ax.set_xlabel("Time")
            ax.set_ylabel("ELO Rating")

            plt.xticks(rotation=45)
            plt.tight_layout()

            buf = io.BytesIO()
            plt.savefig(buf, format='png')
            buf.seek(0)

            await ctx.send(file=discord.File(buf, "elo_trend.png"))
        except Exception as e:
            await ctx.send(f"Error generating ELO graph: {str(e)}")

    @commands.command(aliases=["myelo"])
    async def my_elo(self, ctx):
        try:
            player_id = ctx.author.id

            elo_data = []
            for mode_name, GameModeID in self.mode_map.items():
                if len(mode_name) > 2:  # Only use full mode names (e.g., "land", "conquest", "domination")
                    elo = self.db.get_player_rating(player_id, GameModeID)

                    if elo == "N/A":
                        elo_data.append((mode_name.capitalize(), elo, "N/A", "N/A", "N/A"))
                    else:
                        win_rate = self.db.get_winrate(player_id, GameModeID)
                        player_rank, total_players = self.db.get_player_rank(player_id, GameModeID)
                        top_percentile = round((player_rank / total_players) * 100, 1) if total_players else 100
                        elo_data.append((mode_name.capitalize(), elo, win_rate, top_percentile, player_rank))

            response = [f"🏆 **{ctx.author.name}'s ELO Ratings**"]
            for mode_name, elo, win_rate, top_percentile, player_rank in elo_data:
                if elo == "N/A":
                    response.append(f"- {mode_name}: {elo}")
                else:
                    response.append(f"- {mode_name}: **{elo}** ELO | 🏅 WR: **{win_rate}%** | 🔝 Top **{top_percentile}%** (#{player_rank})")

            await ctx.send("\n".join(response))
        except Exception as e:
            await ctx.send(f"Error fetching ELO ratings: {str(e)}")

    async def update_leaderboard(self, GameModeID):
        channel_map = {
            1: 1347711976502984744,
            2: 1347712009181073429,
            3: 1347712036024483861,
            4: 1347712063753158796
        }

        channel_id = channel_map.get(GameModeID)
        if not channel_id:
            return

        channel = self.bot.get_channel(channel_id)
        if not channel:
            return

        try:
            leaderboard = self.db.get_leaderboard(GameModeID)

            if not leaderboard:
                await channel.send(f"The leaderboard for {GameModeID} mode is empty.")
                return

            response = [f"🏆 **Top players**"]

            for idx, (player_id, elo, matches, wins) in enumerate(leaderboard[:], 1):
                try:
                    user = await self.bot.fetch_user(player_id)
                    display_name = user.display_name
                except discord.NotFound:
                    display_name = f"Player {player_id}"

                if matches > 0:
                    win_rate = round((wins / matches) * 100, 1)
                else:
                    win_rate = 0

                response.append(
                    f"{idx}. {display_name} - **{int(elo)}** ELO | 🏅 WR: **{win_rate}%** ({wins} / {matches})"
                )

            async for message in channel.history(limit=1):
                await message.edit(content="\n".join(response))
                return

            await channel.send("\n".join(response))

        except Exception as e:
            await channel.send(f"Error fetching leaderboard: {str(e)}")

async def setup(bot):
    await bot.add_cog(Leaderboard(bot))

