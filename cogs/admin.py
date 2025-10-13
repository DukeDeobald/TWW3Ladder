import discord
from discord.ext import commands
from database import Database
from logic import update_elo
import re

from utils.maps import MODE_MAP


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.mode_map = MODE_MAP

    

    @commands.command(aliases=["revert"])
    @commands.has_role("Admin")
    async def revert_result(self, ctx, match_id: int, silent: bool = False):
        try:
            self.db.cursor.execute("""
                SELECT player1, player2, winner, GameModeID, 
                       elo_before_winner, elo_after_winner,
                       elo_before_loser, elo_after_loser
                FROM match_history
                WHERE id = ?
            """, (match_id,))
            match = self.db.cursor.fetchone()

            if not match:
                await ctx.send(f"No match found with ID {match_id}")
                return

            player1, player2, winner, GameModeID, elo_before_winner, elo_after_winner, elo_before_loser, elo_after_loser = match

            self.db.cursor.execute("""
                UPDATE player_ratings 
                SET elo = ?, matches = matches - 1, wins = wins - 1
                WHERE player_id = ? AND GameModeID = ?
            """, (elo_before_winner, winner, GameModeID))

            self.db.cursor.execute("""
                UPDATE player_ratings 
                SET elo = ?, matches = matches - 1
                WHERE player_id = ? AND GameModeID = ?
            """, (elo_before_loser, player2 if winner == player1 else player1, GameModeID))

            self.db.cursor.execute("DELETE FROM bets WHERE match_id = ?", (match_id,))
            self.db.conn.commit()

            player1_discord_id = self.db.cursor.execute(
                "SELECT discord_id FROM players WHERE id = ?",
                (player1,)
            ).fetchone()[0]
            player2_discord_id = self.db.cursor.execute(
                "SELECT discord_id FROM players WHERE id = ?",
                (player2,)
            ).fetchone()[0]

            player1_user = await self.bot.fetch_user(player1_discord_id)
            player2_user = await self.bot.fetch_user(player2_discord_id)

            player1_name = player1_user.name
            player2_name = player2_user.name
            winner_name = player1_name if winner == player1 else player2_name

            if not silent:
                await ctx.send(
                    f"✅ Successfully reverted match #{match_id} ({player1_name} vs {player2_name}, winner: {winner_name})"
                )
            await self.bot.get_cog('Leaderboard').update_leaderboard(GameModeID)

        except (discord.HTTPException, discord.Forbidden) as e:
            await ctx.send(f"Error reverting match: {e}")
        except Exception as e:
            await ctx.send(f"An unexpected error occurred while reverting the match: {e}")

    @commands.command(aliases=["edit_match"])
    @commands.has_role("Admin")
    async def edit_match_result(self, ctx, match_id: int, new_winner: discord.Member):
        try:
            self.db.cursor.execute("""
                SELECT player1, player2, GameModeID
                FROM match_history
                WHERE id = ?
            """, (match_id,))
            match = self.db.cursor.fetchone()

            if not match:
                await ctx.send(f"No match found with ID {match_id}")
                return

            player1_db_id, player2_db_id, GameModeID = match

            player1_discord_id = self.db.get_discord_id(player1_db_id)
            player2_discord_id = self.db.get_discord_id(player2_db_id)

            await self.revert_result(ctx, match_id, silent=True)

            new_loser = None
            if new_winner.id == player1_discord_id:
                new_loser_id = player2_discord_id
            elif new_winner.id == player2_discord_id:
                new_loser_id = player1_discord_id
            else:
                await ctx.send(f"{new_winner.mention} was not a participant in match #{match_id}.")
                return
            
            new_loser = await self.bot.fetch_user(new_loser_id)

            winner_rating_before = self.db.get_player_rating(new_winner.id, GameModeID)
            loser_rating_before = self.db.get_player_rating(new_loser.id, GameModeID)

            new_winner_rating, new_loser_rating = update_elo(winner_rating_before, loser_rating_before)

            self.db.record_match_result(
                new_winner.id,
                new_loser.id,
                GameModeID,
                winner_rating_before,
                new_winner_rating,
                loser_rating_before,
                new_loser_rating,
                match_id=match_id
            )

            await ctx.send(
                f"✅ Match #{match_id} result edited: {new_winner.mention} is now the winner."
            )

            await self.bot.get_cog('Leaderboard').update_leaderboard(GameModeID)

        except Exception as e:
            await ctx.send(f"Error editing match result: {str(e)}")

    @commands.command(aliases=["list_matches"])
    @commands.has_role("Admin")
    async def admin_list_matches(self, ctx, limit: int = 10):
        try:
            self.db.cursor.execute("""
                SELECT mh.id, 
                       (SELECT discord_id FROM players WHERE id = mh.player1) as player1_id,
                       (SELECT discord_id FROM players WHERE id = mh.player2) as player2_id,
                       (SELECT discord_id FROM players WHERE id = mh.winner) as winner_id,
                       g.name as mode,
                       mh.datetime
                FROM match_history mh
                JOIN gamemode g ON mh.GameModeID = g.id
                ORDER BY mh.id DESC
                LIMIT ?
            """, (limit,))

            matches = self.db.cursor.fetchall()

            if not matches:
                await ctx.send("No matches found in history.")
                return

            response = ["📜 **Recent Matches (Admin View)**"]
            for match_id, player1_id, player2_id, winner_id, mode, datetime in matches:
                try:
                    player1 = await self.bot.fetch_user(player1_id)
                    player2 = await self.bot.fetch_user(player2_id)
                    winner = await self.bot.fetch_user(winner_id)

                    response.append(
                        f"`#{match_id}` {player1.name} vs {player2.name} | "
                        f"Winner: {winner.name} | Mode: {mode} | {datetime}"
                    )
                except:
                    response.append(
                        f"`#{match_id}` Player {player1_id} vs Player {player2_id} | "
                        f"Winner: Player {winner_id} | Mode: {mode} | {datetime}"
                    )

            await ctx.send("\n".join(response))

        except Exception as e:
            await ctx.send(f"Error fetching match history: {str(e)}")

    @commands.command(aliases=["adjust_elo"])
    @commands.has_role("Admin")
    async def admin_adjust_elo(self, ctx, member: discord.Member, mode: str, new_elo: int):
        try:
            GameModeID = self.mode_map.get(mode.lower())
            if not GameModeID:
                await ctx.send("Invalid mode. Valid modes: land, conquest, domination, luckydice")
                return

            old_elo = self.db.get_player_rating(member.id, GameModeID)
            self.db.update_elo(member.id, GameModeID, new_elo)

            await ctx.send(
                f"✅ Adjusted {member.mention}'s {mode} ELO from {old_elo} to {new_elo}"
            )

            await self.bot.get_cog('Leaderboard').update_leaderboard(GameModeID)

        except Exception as e:
            await ctx.send(f"Error adjusting ELO: {str(e)}")

    @commands.command(aliases=["edit_tokens"])
    @commands.has_role("Admin")
    async def edittokens(self, ctx, amount: int, member: discord.Member):
        try:
            player_id = self.db.get_player_id(member.id)
            if not player_id:
                await ctx.send(f"Player {member.mention} not found in the database.")
                return

            self.db.update_player_balance(player_id, amount)
            await ctx.send(f"✅ Successfully set {member.mention}'s tokens to {amount}.")

        except Exception as e:
            await ctx.send(f"Error editing tokens: {str(e)}")

    @commands.command(aliases=["checktokens"])
    @commands.has_role("Admin")
    async def check_tokens(self, ctx, member: discord.Member):
        try:
            player_id = self.db.get_player_id(member.id)
            if not player_id:
                await ctx.send(f"Player {member.mention} not found in the database.")
                return

            balance = self.db.get_player_balance(player_id)
            await ctx.send(f"{member.mention} has {balance} tokens.")

        except Exception as e:
            await ctx.send(f"Error checking tokens: {str(e)}")


async def setup(bot):
    await bot.add_cog(Admin(bot))

