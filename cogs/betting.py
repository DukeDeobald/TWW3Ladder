import discord
from discord.ext import commands
from database import Database

class Betting(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()

    @commands.command()
    async def balance(self, ctx):
        user_id = self.db.get_player_id(ctx.author.id)
        if user_id:
            balance = self.db.get_player_balance(user_id)
            await ctx.send(f"{ctx.author.mention}, you have {balance} tokens.")
        else:
            await ctx.send("You are not registered in the system.")

    @commands.command()
    async def bet(self, ctx, amount: int = None, member: discord.Member = None):
        if amount is None or member is None:
            await ctx.send("Incorrect usage! Please use the correct format:\n"
                       "```!bet <amount> @player```"
                       "Example:\n"
                       "```!bet 100 @Knight```")
            return

        bettor_id = ctx.author.id

        bettor_player_id = self.db.get_player_id(bettor_id)
        if bettor_player_id is None:
            await ctx.send("You are not registered in the system.")
            return

        bettor_match_id = self.db.get_active_match(bettor_id)

        bet_side = member.id

        bet_side_match_id = self.db.get_active_match(bet_side)
        if bet_side_match_id is None:
            await ctx.send(f"{member.mention} is not in an active match.")
            return

        if bettor_id == bet_side:
            await ctx.send("You cannot bet on yourself.")
            return

        if bettor_match_id is not None:
            bettor_opponent_id = self.db.get_opponent_id(bettor_id, bettor_match_id)

            if bet_side == bettor_opponent_id:
                await ctx.send(f"You cannot bet on your current opponent ({member.mention}).")
                return

        self.db.cursor.execute("SELECT id FROM bets WHERE bettor_id = ? AND match_id = ?", (bettor_id, bet_side_match_id))
        existing_bet = self.db.cursor.fetchone()
        if existing_bet:
            await ctx.send("You have already placed a bet on this match.")
            return

        balance = self.db.get_player_balance(bettor_player_id)
        if balance < amount:
            await ctx.send("You do not have enough tokens to place this bet.")
            return

        if amount <= 0 or amount > balance:
            await ctx.send("Invalid betting amount.")
            return

        self.db.update_player_balance(bettor_id, balance - amount)
        self.db.place_bet(bettor_id, bet_side_match_id, bet_side, amount)

        await ctx.send(f"{ctx.author.mention} placed a bet of {amount} tokens on {member.mention}.")

    @commands.command()
    async def bet_history(self, ctx):
        user_id = ctx.author.id
        if user_id:
            self.db.cursor.execute("""
                SELECT match_id, bet_side, amount, placed_at, resolved, 
                       players.discord_id 
                FROM bets 
                INNER JOIN players ON bets.bet_side = players.discord_id
                WHERE bettor_id = ?
            """, (user_id,))
            bets = self.db.cursor.fetchall()
            if bets:
                response = [":scroll: **Your Bet History**"]
                for bet in bets:
                    match_id, bet_side, amount, placed_at, resolved, bet_side_discord_id = bet
                    status = "Resolved" if resolved else "Pending"
                    bet_side_member = ctx.guild.get_member(bet_side_discord_id)
                    if not bet_side_member:
                        bet_side_member = self.bot.get_user(bet_side_discord_id)
                    if not bet_side_member:
                        try:
                            bet_side_member = await self.bot.fetch_user(bet_side_discord_id)
                        except Exception:
                            bet_side_member = None
                    bet_side_name = bet_side_member.name if bet_side_member else "Unknown Player"
                    response.append(f"• Match {match_id}: Bet on {bet_side_name} for {amount} tokens ({status})")
                await ctx.send("\n".join(response))
            else:
                await ctx.send("You have no bet history.")
        else:
            await ctx.send("You are not registered in the system.")

async def setup(bot):
    await bot.add_cog(Betting(bot))

