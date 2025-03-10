import discord
from discord.ext import commands, tasks
from logic import LadderSystem
from database import Database
import logic
import matplotlib.pyplot as plt
import io
import seaborn as sns
import pandas as pd


with open("forum.txt", "r") as file:
    FORUM_CHANNEL_ID = int(file.read().strip())

with open("ladder token.txt", "r") as file:
    TOKEN = file.read().strip()

with open("server.txt", "r") as file:
    SERVER_ID = int(file.read().strip())

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
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
    "luckytest": 4,
    "lt": 4
}
REVERSE_MODE_MAP = {1: "land", 2: "conquest", 3: "domination", 4: "luckytest"}


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
async def queue(ctx, mode: str = "  "):
    mode_map = {"l": "land", "c": "conquest", "d": "domination", "lt": "luckytest"}
    mode = mode_map.get(mode.lower(), mode)

    if ctx.channel.name != "queue":
        await ctx.send("This command is only available in the #queue channel.")
        return

    if mode not in ["land", "conquest", "domination", "luckytest"]:
        await ctx.send("Mode must be 'land', 'conquest', 'domination' or 'luckytest'.")
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

                player1_name = (await bot.fetch_user(player1)).name
                player2_name = (await bot.fetch_user(player2)).name

                player1_elo = db.get_player_rating(player1, GameModeID)
                player2_elo = db.get_player_rating(player2, GameModeID)

                mode_tag_map = {
                    "land": 1347697308841545769,
                    "conquest": 1347697335240491038,
                    "domination": 1347697321395224706,
                    "luckytest": 1347697354249338993
                }

                mode_tag_id = mode_tag_map.get(mode)

                available_tags = forum_channel.available_tags
                mode_tag = next((tag for tag in available_tags if tag.id == mode_tag_id), None)

                if mode_tag is None:
                    await ctx.send(f"Could not find the tag for {mode} mode.")
                    return

                mode_rules = {
                    "land": "**🏰 Land Mode Rules:**\n- ATTACK:\n"
                      "- Moving into position to initiate an attack\n"
                      "- Engaging in melee combat\n"
                      "- Ranged fire\n\n"
                      "NOT AN ATTACK:\n"
                      "- Chasing down shattered units\n"
                      "- Attacking with only single units (exception: artillery or the last remaining units on the battlefield)\n"
                      "- Using abilities\n\n"
                      "ADDITIONAL NOTES:\n"
                      "- If you only have flying units left, you can no longer perform cycle charges.\n"
                      "- Shots where you cannot manually select a target are never considered an attack."
                      "- Unit caps should be ON. Only use in-game rules.",
                    "conquest": "**⚔️ Conquest Mode Rules:**\n- .",
                    "domination": "**🏆 Domination Mode Rules:**\n- .",
                    "luckytest": "**🎲 Lucky Test Mode Rules:**\n- **ULTRA FUNDS** (17,000).\n- Each player can roll up to 5 times in total: meaning you can have maximum of 4 factions rolls, and it leaves you with 1 roll for a build. If a player rolls more than 5 times, they receive a technical loss in that battle. (Note: you can use unspent gold to give units chevrons. It is also possible to remove some units, but this money can still only be used for chevrons.).\n- The mode is Conquest, with 600 tickets.\n- Unit caps must be ON.\n- The game is Bo5"
                }

                thread = await forum_channel.create_thread(
                    name=f"{player1_name} vs {player2_name}",
                    content=f'Match found: <@{player1}> ({player1_elo} ELO) vs <@{player2}> ({player2_elo} ELO) in {mode} mode!',
                    applied_tags=[mode_tag]
                )

                db.create_match(player1, player2, GameModeID, thread.thread.id)

                await thread.thread.send(mode_rules.get(mode, "No specific rules available for this mode."))

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
        await ctx.send("Invalid result. Use `/r win` or `/r loss`. ")
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

    await update_leaderboard(GameModeID)

    reward, role_id = db.check_win_reward(winner_id)
    if reward:
        db.assign_reward(winner_id, reward, role_id)
        member = ctx.guild.get_member(winner_id)
        if member:
            role = ctx.guild.get_role(role_id)
            if role:
                await member.add_roles(role)

    await assign_role_based_on_wins(ctx, winner_id)

    await ctx.send(
        f"Match result recorded: <@{winner_id}> wins in {REVERSE_MODE_MAP.get(GameModeID, 'Unknown Mode')} mode!\n"
        f"Rating change:\n<@{winner_id}>, {new_winner_rating} (+{new_winner_rating - winner_rating_before}) \n"
        f"<@{loser_id}>, {new_loser_rating} ({new_loser_rating - loser_rating_before})"
    )


@bot.command(aliases=["lb", "leaderboard", "top"])
async def leaders(ctx, mode: str = " "):
    mode_map = {"l": "land", "c": "conquest", "d": "domination", "lt": "luckytest"}
    mode = mode_map.get(mode.lower(), mode.lower())

    if mode not in ["land", "conquest", "domination", "luckytest"]:
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

            if matches > 0:
                win_rate = round((wins / matches) * 100, 1)
            else:
                win_rate = 0

            response.append(
                f"{idx}. {display_name} - **{int(elo)}** ELO | 🏅 WR: **{win_rate}%** ({wins} / {matches})"
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
            await ctx.send("Please specify a mode ('land', 'conquest', 'domination' or 'luckytest').")
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
            if len(mode_name) > 2:  # Only use full mode names (e.g., "land", "conquest", "domination")
                elo = db.get_player_rating(player_id, GameModeID)

                if elo == "N/A":
                    elo_data.append((mode_name.capitalize(), elo, "N/A", "N/A", "N/A"))
                else:
                    win_rate = db.get_winrate(player_id, GameModeID)
                    player_rank, total_players = db.get_player_rank(player_id, GameModeID)
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


@bot.command()
async def balance(ctx):
    user_id = db.get_player_id(ctx.author.id)
    if user_id:
        balance = db.get_player_balance(user_id)
        await ctx.send(f"{ctx.author.mention}, you have {balance} tokens.")
    else:
        await ctx.send("You are not registered in the system.")


@bot.command()
async def bet(ctx, amount: int = None, member: discord.Member = None):
    if amount is None or member is None:
        await ctx.send("Incorrect usage! Please use the correct format:\n"
                       "```!bet <amount> @player```"
                       "Example:\n"
                       "```!bet 100 @Knight```")
        return

    bettor_id = ctx.author.id

    bettor_player_id = db.get_player_id(bettor_id)
    if bettor_player_id is None:
        await ctx.send("You are not registered in the system.")
        return

    bettor_match_id = db.get_active_match(bettor_id)

    bet_side = member.id

    bet_side_match_id = db.get_active_match(bet_side)
    if bet_side_match_id is None:
        await ctx.send(f"{member.mention} is not in an active match.")
        return

    if bettor_id == bet_side:
        await ctx.send("You cannot bet on yourself.")
        return

    if bettor_match_id is not None:
        bettor_opponent_id = db.get_opponent_id(bettor_id, bettor_match_id)

        if bet_side == bettor_opponent_id:
            await ctx.send(f"You cannot bet on your current opponent ({member.mention}).")
            return

    db.cursor.execute("SELECT id FROM bets WHERE bettor_id = ? AND match_id = ?", (bettor_id, bet_side_match_id))
    existing_bet = db.cursor.fetchone()
    if existing_bet:
        await ctx.send("You have already placed a bet on this match.")
        return

    balance = db.get_player_balance(bettor_player_id)
    if balance < amount:
        await ctx.send("You do not have enough tokens to place this bet.")
        return

    if amount <= 0 or amount > balance:
        await ctx.send("Invalid betting amount.")
        return

    db.update_player_balance(bettor_id, balance - amount)
    db.place_bet(bettor_id, bet_side_match_id, bet_side, amount)

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


async def assign_role_based_on_wins(ctx, user_id):
    member = ctx.guild.get_member(user_id)
    if member is None:
        print("no member found")
        return

    reward_name, role_id = db.check_win_reward(user_id)
    if role_id:
        success = await assign_reward_role(member, role_id)
        if success:
            await ctx.send(f"{member.mention} has been awarded the role '{reward_name}' for {reward_name}!")
        else:
            await ctx.send(f"Could not assign the role '{reward_name}' to {member.mention}.")


async def update_leaderboard(GameModeID):
    channel_map = {
        1: 1347711976502984744,
        2: 1347712009181073429,
        3: 1347712036024483861,
        4: 1347712063753158796
    }

    channel_id = channel_map.get(GameModeID)
    if not channel_id:
        return

    channel = bot.get_channel(channel_id)
    if not channel:
        return

    try:
        leaderboard = db.get_leaderboard(GameModeID)

        if not leaderboard:
            await channel.send(f"The leaderboard for {GameModeID} mode is empty.")
            return

        response = [f"🏆 **Top players**"]

        for idx, (player_id, elo, matches, wins) in enumerate(leaderboard[:], 1):
            try:
                user = await bot.fetch_user(player_id)
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

bot.run(TOKEN)
