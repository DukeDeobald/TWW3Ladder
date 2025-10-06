import discord
from discord.ext import commands
from database import Database
import datetime

class Shop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()

    @commands.command(name="shop", description="Spend your tokens on perks.")
    async def shop(self, ctx):
        view = ShopView(self.db, ctx.author)
        await ctx.send("Welcome to the shop! Select a perk to purchase.", view=view)

    @commands.command(name="give", aliases=["transfer"], description="Give tokens to another player.")
    async def give(self, ctx, recipient: discord.Member, amount: int):
        sender = ctx.author

        if recipient.bot:
            await ctx.send("You cannot give tokens to a bot.")
            return

        if recipient.id == sender.id:
            await ctx.send("You cannot give tokens to yourself.")
            return

        if amount <= 0:
            await ctx.send("Please enter a positive amount of tokens to give.")
            return

        sender_id = self.db.get_player_id(sender.id)
        if not sender_id:
            await ctx.send("You are not registered as a player yet. Play a match first!")
            return

        sender_balance = self.db.get_player_balance(sender_id)
        if sender_balance < amount:
            await ctx.send(f"You do not have enough tokens to give. You have {sender_balance}, but you tried to give {amount}.")
            return

        recipient_id = self.db.get_player_id(recipient.id)
        if not recipient_id:
            self.db.add_player(recipient.id)
            recipient_id = self.db.get_player_id(recipient.id)

        self.db.update_player_balance(sender_id, sender_balance - amount)
        recipient_balance = self.db.get_player_balance(recipient_id)
        self.db.update_player_balance(recipient_id, recipient_balance + amount)

        await ctx.send(f"{sender.mention} has successfully given {amount} tokens to {recipient.mention}!")

    @give.error
    async def give_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("**Usage:** `!give <@user> <amount>`")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("**Invalid argument.** Please make sure you mention a valid user and enter a whole number for the amount.")

class ShopView(discord.ui.View):
    def __init__(self, db, user):
        super().__init__(timeout=180)
        self.db = db
        self.user = user
        self.add_item(PerkSelect(db, user))

class PerkSelect(discord.ui.Select):
    def __init__(self, db, user):
        self.db = db
        self.user = user
        options = [
            discord.SelectOption(label="Leaderboard Highlight", description="Highlight your name on the leaderboard for 7 days. Price: 50 tokens.", value="highlight"),
            discord.SelectOption(label="Custom Taunt", description="Set a custom message that displays when you win a match. Price: 100 tokens.", value="taunt")
        ]
        super().__init__(placeholder="Choose a perk...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("You cannot use this menu.", ephemeral=True)
            return

        selection = self.values[0]
        if selection == "highlight":
            await self.purchase_highlight(interaction)
        elif selection == "taunt":
            await interaction.response.send_modal(TauntModal(self.db, self.user))

    async def purchase_highlight(self, interaction: discord.Interaction):
        player_id = self.db.get_player_id(self.user.id)
        if not player_id:
            await interaction.response.send_message("You are not registered as a player yet. Play a match first!", ephemeral=True)
            return

        balance = self.db.get_player_balance(player_id)
        price = 50

        if balance >= price:
            self.db.update_player_balance(player_id, balance - price)
            expires_at = datetime.datetime.now() + datetime.timedelta(days=7)
            self.db.cursor.execute("DELETE FROM player_perks WHERE player_id = ? AND perk_type = 'highlight'", (player_id,))
            self.db.cursor.execute("INSERT INTO player_perks (player_id, perk_type, expires_at) VALUES (?, ?, ?)", (player_id, "highlight", expires_at.isoformat()))
            self.db.conn.commit()
            await interaction.response.send_message("You have purchased a Leaderboard Highlight! It will expire in 7 days.", ephemeral=True)
        else:
            await interaction.response.send_message(f"You do not have enough tokens to purchase this perk. You need {price}, but you have {balance}.", ephemeral=True)

class TauntModal(discord.ui.Modal, title="Set Your Custom Taunt"):
    def __init__(self, db, user):
        super().__init__()
        self.db = db
        self.user = user
        self.taunt_input = discord.ui.TextInput(label="Enter your taunt (max 100 characters)", max_length=100)
        self.add_item(self.taunt_input)

    async def on_submit(self, interaction: discord.Interaction):
        player_id = self.db.get_player_id(self.user.id)
        if not player_id:
            await interaction.response.send_message("You are not registered as a player yet. Play a match first!", ephemeral=True)
            return

        balance = self.db.get_player_balance(player_id)
        price = 100

        if balance >= price:
            self.db.update_player_balance(player_id, balance - price)
            self.db.cursor.execute("DELETE FROM player_perks WHERE player_id = ? AND perk_type = 'taunt'", (player_id,))
            self.db.cursor.execute("INSERT INTO player_perks (player_id, perk_type, data) VALUES (?, ?, ?)", (player_id, "taunt", self.taunt_input.value))
            self.db.conn.commit()
            await interaction.response.send_message("Your custom taunt has been set!", ephemeral=True)
        else:
            await interaction.response.send_message(f"You do not have enough tokens to purchase this perk. You need {price}, but you have {balance}.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Shop(bot))
