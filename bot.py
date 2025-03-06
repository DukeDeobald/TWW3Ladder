import discord
from discord.ext import commands, tasks
from logic import LadderSystem
from database import Database
import logic
import matplotlib.pyplot as plt
import io
import seaborn as sns
import pandas as pd
from matplotlib.ticker import MaxNLocator
import matplotlib.dates as mdates

with open("forum.txt", "r") as file:
    FORUM_CHANNEL_ID = int(file.read().strip())

with open("ladder token.txt", "r") as file:
    TOKEN = file.read().strip()

with open("server.txt", "r") as file:
    SERVER_ID = int(file.read().strip())

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

db = Database()
ladder = LadderSystem(db)

MODE_MAP = {
    "land": 1,
    "l": 1,
    "conquest": 2,
    "c": 2,
    "domination": 3,
    "d": 3,
    "lucky-test": 4,
    "lt": 4
}
REVERSE_MODE_MAP = {1: "land", 2: "conquest", 3: "domination", 4: "lucky-test"}


@tasks.loop(hours=24)
async def remove_expired_rewards_task():
    await remove_expired_roles()


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')


@bot.command(aliases=["s"])
async def status(ctx):
    player_id = ctx.author.id

    queue_status = db.get_queue_status(player_id)
    if queue_status:
        mode_name = REVERSE_MODE_MAP.get(queue_status, "Unknown Mode")
        await ctx.send(f'{ctx.author.name}, you are in the queue for {mode_name} mode.')
        return

    match_details = db.get_match_details(player_id)
    if match_details and match_details[0] is not None and match_details[1] is not None:
        opponent, GameModeID = match_details
        mode_name = REVERSE_MODE_MAP.get(GameModeID, "Unknown Mode")
        thread_id = db.get_match_thread(player_id, opponent, GameModeID)
        if thread_id:
            thread = bot.get_channel(thread_id)
            if thread:
                await ctx.send(f'{ctx.author.name}, you are in a match ({mode_name}) against <@{opponent}> in {thread.jump_url}.')
                return
        await ctx.send(f'{ctx.author.name}, you are in a match ({mode_name}) against <@{opponent}>.')
    else:
        await ctx.send(f'{ctx.author.name}, you are not in queue or in a match.')


@bot.command(aliases=["q"])
async def queue(ctx, mode: str):
    """Adds the player to the queue for the selected mode."""
    mode_map = {"l": "land", "c": "conquest", "d": "domination", "lt": "lucky-test"}
    mode = mode_map.get(mode.lower(), mode)

    if ctx.channel.name != "queue":
        await ctx.send("This command is only available in the #queue channel.")
        return

    if mode not in ["land", "conquest", "domination", "lucky-test"]:
        await ctx.send("Mode must be 'land', 'conquest', 'domination' or 'lucky-test'.")
        return

    GameModeID = MODE_MAP.get(mode)
    if not GameModeID:
        await ctx.send("Invalid mode.")
        return

    db.add_player(ctx.author.id)
    db.add_player_mode(ctx.author.id, GameModeID)

    queue_status = db.get_queue_status(ctx.author.id)
    if queue_status:
        mode_name = REVERSE_MODE_MAP.get(queue_status, "Unknown Mode")
        await ctx.send(f'{ctx.author.name}, you are already in the queue for {mode_name} mode.')
        return

    match_details = db.get_match_details(ctx.author.id)
    if match_details and all(match_details):
        await ctx.send(
            f"{ctx.author.name}, you are already in a match. Please finish your current match before queuing again.")
        return

    db.add_to_queue(ctx.author.id, GameModeID)
    player_count = db.get_queue_players_count(GameModeID)

    await ctx.send(f'{ctx.author.mention} joined the queue for {mode} mode. Players in queue: {player_count}.')

    if player_count >= 2:
        queue_players = db.get_queue_players(GameModeID)
        if len(queue_players) >= 2:
            player1, player2 = queue_players[0][0], queue_players[1][0]

            db.mark_as_matched(player1)
            db.mark_as_matched(player2)

            try:
                forum_channel = bot.get_channel(FORUM_CHANNEL_ID)

                player1_name = (await bot.fetch_user(player1)).display_name
                player2_name = (await bot.fetch_user(player2)).display_name

                thread = await forum_channel.create_thread(
                    name=f"Match: {player1_name} vs {player2_name} - {mode.capitalize()}",
                    content=f"Match found: <@{player1}> vs <@{player2}> in {mode} mode!"
                )

                db.create_match(player1, player2, GameModeID, thread.id)

                player1_elo = db.get_player_rating(player1, GameModeID)
                player2_elo = db.get_player_rating(player2, GameModeID)

                await thread.send(
                    f'Match found: <@{player1}> ({player1_elo} ELO) vs <@{player2}> ({player2_elo} ELO) in {mode} mode!'
                )
            except Exception as e:
                await ctx.send(f"Error creating match: {str(e)}")


@bot.command(aliases=["e", "dq", "dequeue", "leave"])
async def exit(ctx):
    player_id = ctx.author.id

    queue_status = db.get_queue_status(player_id)
    if queue_status:
        db.mark_as_unqueued(player_id)
        mode_name = REVERSE_MODE_MAP.get(queue_status, "Unknown Mode")
        await ctx.send(f"{ctx.author.name} left the queue for {mode_name} mode.")
        return

    match_details = db.get_match_details(player_id)

    if match_details and all(match_details):
        opponent, GameModeID = match_details
        mode_name = REVERSE_MODE_MAP.get(GameModeID, "Unknown Mode")

        match_id = db.get_active_match(player_id)
        if match_id:
            db.cursor.execute("SELECT bettor_id, amount FROM bets WHERE match_id = ? AND resolved = FALSE", (match_id,))
            unresolved_bets = db.cursor.fetchall()

            for bettor_id, amount in unresolved_bets:
                db.update_player_balance(db.get_player_id(bettor_id), db.get_player_balance(db.get_player_id(bettor_id)) + amount)
            db.cursor.execute("UPDATE bets SET resolved = TRUE WHERE match_id = ?", (match_id,))
            db.conn.commit()

        db.remove_match(player_id, opponent)
        await ctx.send(f"{ctx.author.name} left the match for {mode_name} mode.")
        return

    await ctx.send(f"{ctx.author.name}, you are not in queue or in an active match.")


@bot.command(aliases=["r"])
async def result(ctx, outcome: str):
    if outcome.lower() not in ["win", "w", "loss", "l"]:
        await ctx.send("Invalid result. Use `/r win` or `/r loss`.")
        return

    match_details = db.get_match_details(ctx.author.id)
    if not match_details or match_details[0] is None:
        await ctx.send("You are not in an active match.")
        return

    opponent, GameModeID = match_details

    match_id = db.get_active_match(ctx.author.id)
    if not match_id:
        await ctx.send("No active match found.")
        return

    if outcome.lower() in ["win", "w"]:
        winner_id = ctx.author.id
        loser_id = opponent
    else:
        winner_id = opponent
        loser_id = ctx.author.id

    winner_rating_before = db.get_player_rating(winner_id, GameModeID)
    loser_rating_before = db.get_player_rating(loser_id, GameModeID)

    new_winner_rating, new_loser_rating = logic.update_elo(winner_rating_before, loser_rating_before)

    db.update_player_rating(winner_id, GameModeID, new_winner_rating)
    db.update_player_rating(loser_id, GameModeID, new_loser_rating)

    db.record_match_result(
        winner_id,
        loser_id,
        GameModeID,
        winner_rating_before,
        new_winner_rating,
        loser_rating_before,
        new_loser_rating
    )

    db.resolve_bets(match_id, winner_id)


    db.remove_match(winner_id, loser_id)

    reward, role_id = db.check_win_reward(winner_id)
    if reward:
        db.assign_reward(winner_id, reward, role_id)
        member = ctx.guild.get_member(winner_id)
        if member:
            role = ctx.guild.get_role(role_id)
            if role:
                await member.add_roles(role)
                await ctx.send(f"{ctx.author.mention} has earned the {reward} reward and the corresponding role!")

    await ctx.send(
        f"Match result recorded: <@{winner_id}> wins in {REVERSE_MODE_MAP.get(GameModeID, 'Unknown Mode')} mode!\n"
        f"Rating change: <@{winner_id}> +{new_winner_rating - winner_rating_before}, {new_winner_rating} \n"
        f"<@{loser_id}> {new_loser_rating - loser_rating_before}, {new_loser_rating}"
    )


@bot.command(aliases=["lb", "leaderboard"])
async def leaders(ctx, mode: str = " "):
    mode_map = {"l": "land", "c": "conquest", "d": "domination", "lt": "lucky-test"}
    mode = mode_map.get(mode.lower(), mode.lower())

    if mode not in ["land", "conquest", "domination", "lucky-test"]:
        return await ctx.send(f"Invalid mode. Valid modes: {', '.join(mode_map.values())}")

    GameModeID = MODE_MAP.get(mode)
    if not GameModeID:
        return await ctx.send("Invalid mode.")

    try:
        leaderboard = ladder.get_leaderboard(GameModeID)
        if not leaderboard:
            return await ctx.send(f"The leaderboard for {mode} mode is empty.")

        response = [f"🏆 **Top players ({mode})**"]
        for idx, (player_id, elo, matches, wins) in enumerate(leaderboard[:10], 1):
            try:
                user = await bot.fetch_user(player_id)
                display_name = user.display_name
            except discord.NotFound:
                display_name = f"Player {player_id}"

            response.append(
                f"{idx}. {display_name} - {int(elo)} ELO | "
                f"{matches} matches | {wins} wins"
            )

        await ctx.send("\n".join(response))
    except Exception as e:
        await ctx.send(f"Error fetching leaderboard: {str(e)}")


@bot.command(aliases=["h"])
async def history(ctx, limit: int = 11):
    try:
        matches = ladder.get_match_history(ctx.author.id, limit)
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
                user = await bot.fetch_user(player_id)
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
            mode_name = REVERSE_MODE_MAP.get(GameModeID, "Unknown Mode")
            elo_change = elo_after_winner - elo_before_winner if winner_discord_id == ctx.author.id else elo_after_loser - elo_before_loser
            entry = (
                f"- {mode_name}: {player1_name} vs {player2_name} | "
                f"{result} ({elo_change} ELO)"
            )
            response.append(entry)

        await ctx.send("\n".join(response[:limit]))
    except Exception as e:
        await ctx.send(f"Error fetching history: {str(e)}")


@bot.command(aliases=["elo"])
async def elo_graph_cmd(ctx, mode: str = None):
    try:
        if mode is None:
            await ctx.send("Please specify a mode ('land', 'conquest', 'domination' or 'lucky-test').")
            return

        mode = mode.lower()
        mode_map = {
            "land": 1, "l": 1,
            "conquest": 2, "c": 2,
            "domination": 3, "d": 3,
            "lucky-test": 4, "lt": 4
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

        elo_data = db.get_player_elo_history(ctx.author.id, GameModeID)
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


@bot.command(aliases=["myelo"])
async def my_elo(ctx):
    try:
        player_id = ctx.author.id

        elo_data = []
        for mode_name, GameModeID in MODE_MAP.items():
            if len(mode_name) > 1:  # Only use full mode names (e.g., "land", "conquest", "domination")
                elo = db.get_player_rating(player_id, GameModeID)
                elo_data.append((mode_name.capitalize(), elo))

        response = [f"🏆 **{ctx.author.name}'s ELO Ratings**"]
        for mode_name, elo in elo_data:
            response.append(f"• {mode_name}: {elo} ELO")

        await ctx.send("\n".join(response))
    except Exception as e:
        await ctx.send(f"Error fetching ELO ratings: {str(e)}")


@bot.command()
async def balance(ctx):
    user_id = db.get_player_id(ctx.author.id)
    if user_id:
        balance = db.get_player_balance(user_id)
        await ctx.send(f"{ctx.author.mention}, you have {balance} tokens.")
    else:
        await ctx.send("You are not registered in the system.")


@bot.command()
async def bet(ctx, amount: int, member: discord.Member):
    bettor_id = ctx.author.id

    bet_side = member.id
    match_id = db.get_active_match(bet_side)

    if bettor_id is None:
        await ctx.send("You are not registered in the system.")
        return

    if bet_side is None:
        await ctx.send(f"{member.mention} is not registered in the system.")
        return

    if bettor_id == bet_side:
        await ctx.send("You cannot bet on your own match.")
        return

    if match_id is None:
        await ctx.send(f"{member.mention} is not in an active match.")
        return

    db.cursor.execute("SELECT id FROM bets WHERE bettor_id = ? AND match_id = ?", (bettor_id, match_id))
    existing_bet = db.cursor.fetchone()
    if existing_bet:
        await ctx.send("You have already placed a bet on this match.")
        return

    bettor_player_id = db.get_player_id(bettor_id)
    balance = db.get_player_balance(bettor_player_id)
    if balance < amount:
        await ctx.send("You do not have enough tokens to place this bet.")
        return

    if amount <= 0 or amount > balance:
        await ctx.send("Invalid betting amount")
        return

    db.update_player_balance(bettor_id, balance - amount)
    db.place_bet(bettor_id, match_id, bet_side, amount)
    await ctx.send(f"{ctx.author.mention} placed a bet of {amount} tokens on {member.mention}.")


@bot.command()
async def bet_history(ctx):
    user_id = ctx.author.id
    if user_id:
        db.cursor.execute("""
            SELECT match_id, bet_side, amount, placed_at, resolved, 
                   players.discord_id 
            FROM bets 
            INNER JOIN players ON bets.bet_side = players.discord_id
            WHERE bettor_id = ?
        """, (user_id,))
        bets = db.cursor.fetchall()
        if bets:
            response = [":scroll: **Your Bet History**"]
            for bet in bets:
                match_id, bet_side, amount, placed_at, resolved, bet_side_discord_id = bet
                status = "Resolved" if resolved else "Pending"
                bet_side_member = ctx.guild.get_member(bet_side_discord_id)
                if not bet_side_member:
                    bet_side_member = bot.get_user(bet_side_discord_id)
                if not bet_side_member:
                    try:
                        bet_side_member = await bot.fetch_user(bet_side_discord_id)
                    except Exception:
                        bet_side_member = None
                bet_side_name = bet_side_member.name if bet_side_member else "Unknown Player"
                response.append(f"• Match {match_id}: Bet on {bet_side_name} for {amount} tokens ({status})")
            await ctx.send("\n".join(response))
        else:
            await ctx.send("You have no bet history.")
    else:
        await ctx.send("You are not registered in the system.")


async def assign_reward_role(member, role_id):
    role = member.guild.get_role(role_id)
    if role:
        await member.add_roles(role)
        return True
    return False


async def remove_expired_roles():
    expired_rewards = db.remove_expired_rewards()
    for user_id, role_id in expired_rewards:
        member = bot.get_guild(SERVER_ID).get_member(user_id)
        if member:
            role = member.guild.get_role(role_id)
            if role:
                await member.remove_roles(role)
                print(f"Removed role {role.name} from user {member.display_name}.")


@bot.command(aliases=["m"])
async def matches(ctx):
    matches = db.get_current_matches()
    if not matches:
        await ctx.send("No active matches at the moment.")
        return

    response = "**Currently Active Matches:**\n"
    for player1, player2, mode, thread_id in matches:
        thread = bot.get_channel(thread_id)
        if thread:
            response += f"🎮 {player1} vs {player2} | Mode: {mode} | Thread: {thread.jump_url}\n"
        else:
            response += f"🎮 {player1} vs {player2} | Mode: {mode} | Thread ID: {thread_id}\n"

    await ctx.send(response)

bot.run(TOKEN)
