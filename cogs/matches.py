import discord
from discord.ext import commands, tasks
import random
from database import Database
from logic import update_elo
import re
from datetime import datetime, timedelta

from utils.maps import MODE_MAP, REVERSE_MODE_MAP, domination_constant_maps, season0_domination_maps, conquest_maps, land_maps, factions

class FactionSelectView(discord.ui.View):
    def __init__(self, db, match_id, player_id, faction_pool, maps, bot):
        super().__init__(timeout=300)
        self.db = db
        self.match_id = match_id
        self.player_id = player_id
        self.faction_pool = faction_pool
        self.maps = maps
        self.selected_factions = []
        self.bot = bot

        for faction in self.faction_pool:
            self.add_item(FactionButton(faction, self))

    def get_message_content(self):
        content = "Please select your 3 factions for this match.\n"
        for i, map_name in enumerate(self.maps):
            content += f"\nMap {i+1} ({map_name}): "
            if i < len(self.selected_factions):
                content += factions[self.selected_factions[i]]
        return content

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        await self.message.edit(content="Faction selection has timed out.", view=self)

class FactionButton(discord.ui.Button):
    def __init__(self, faction_name, view):
        super().__init__(style=discord.ButtonStyle.secondary, emoji=factions[faction_name])
        self.faction_name = faction_name
        self.view_ref = view

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.view_ref.player_id:
            await interaction.response.send_message("This is not for you.", ephemeral=True)
            return

        if self.faction_name in self.view_ref.selected_factions:
            self.view_ref.selected_factions.remove(self.faction_name)
            self.style = discord.ButtonStyle.secondary
        else:
            if len(self.view_ref.selected_factions) < 3:
                self.view_ref.selected_factions.append(self.faction_name)
                self.style = discord.ButtonStyle.success
            else:
                await interaction.response.send_message("You can only select 3 factions.", ephemeral=True)
                return

        if len(self.view_ref.selected_factions) == 3:
            for item in self.view_ref.children:
                if isinstance(item, FactionButton) and item.faction_name not in self.view_ref.selected_factions:
                    item.disabled = True
            self.view_ref.add_item(SubmitButton(self.view_ref, self.view_ref.bot))
        else:
            for item in self.view_ref.children:
                if isinstance(item, SubmitButton):
                    self.view_ref.remove_item(item)

        await interaction.response.edit_message(content=self.view_ref.get_message_content(), view=self.view_ref)

class SubmitButton(discord.ui.Button):
    def __init__(self, view, bot):
        super().__init__(label="Submit", style=discord.ButtonStyle.primary)
        self.view_ref = view
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.view_ref.player_id:
            await interaction.response.send_message("This is not for you.", ephemeral=True)
            return

        self.view_ref.db.update_luckydice_selection(self.view_ref.match_id, self.view_ref.player_id, self.view_ref.selected_factions)
        for item in self.view_ref.children:
            item.disabled = True
        await interaction.response.edit_message(content="Your selections have been submitted.", view=self.view_ref)

        selections = self.view_ref.db.get_luckydice_selections(self.view_ref.match_id)
        if selections and selections[7] and selections[8]:
            player1_factions = selections[5].split(',')
            player2_factions = selections[6].split(',')

            maps = self.view_ref.maps
            player1_id = selections[1]
            player2_id = selections[2]
            player1 = await self.bot.fetch_user(player1_id)
            player2 = await self.bot.fetch_user(player2_id)

            message_id = self.view_ref.db.get_match_message_id(self.view_ref.match_id)
            if message_id:
                try:
                    channel = self.view_ref.bot.get_channel(interaction.channel.id)
                    message = await channel.fetch_message(message_id)
                    if message.components:
                        view = discord.ui.View.from_message(message)
                        for item in view.children:
                            item.disabled = True
                        await message.edit(view=view)
                except (discord.NotFound, discord.Forbidden):
                    pass

            message_content = f"**Picks are finalized!**\n\n"
            message_content += f"{player1.display_name} ⚔️ {player2.display_name}\n"

            for i in range(len(maps)):
                p1_faction_name = player1_factions[i]
                p2_faction_name = player2_factions[i]
                map_name = maps[i]
                message_content += f'{factions[p1_faction_name]} {map_name} {factions[p2_faction_name]}\n'

            await interaction.channel.send(message_content)

class InitiateFactionSelectView(discord.ui.View):
    def __init__(self, db, match_id, maps, bot):
        super().__init__(timeout=300)
        self.db = db
        self.match_id = match_id
        self.maps = maps
        self.bot = bot

    @discord.ui.button(label="Select Your Factions", style=discord.ButtonStyle.primary)
    async def select_factions(self, interaction: discord.Interaction, button: discord.ui.Button):
        selections = self.db.get_luckydice_selections(self.match_id)
        if not selections:
            await interaction.response.send_message("This match does not exist.", ephemeral=True)
            return

        player1_id = selections[1]
        player2_id = selections[2]

        if interaction.user.id not in [player1_id, player2_id]:
            await interaction.response.send_message("This is not for you.", ephemeral=True)
            return

        player_faction_pool = selections[3].split(',') if interaction.user.id == player1_id else selections[4].split(',')
        view = FactionSelectView(self.db, self.match_id, interaction.user.id, player_faction_pool, self.maps, self.bot)
        await interaction.response.send_message(content=view.get_message_content(), view=view, ephemeral=True)


from discord.ext import tasks, commands

class Matches(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.mode_map = MODE_MAP
        self.reverse_mode_map = REVERSE_MODE_MAP
        self.check_queue_timeouts.start()

    def cog_unload(self):
        self.check_queue_timeouts.cancel()

    @tasks.loop(minutes=5)
    async def check_queue_timeouts(self):
        try:
            all_queued_players = self.db.get_all_queued_players()
            for player_info in all_queued_players:
                discord_id, game_mode_id, timestamp_queued, mode_name = player_info
                
                queued_time = datetime.fromisoformat(timestamp_queued)
                if datetime.now() - queued_time > timedelta(hours=2):
                    self.db.remove_from_queue(discord_id, game_mode_id)
                    
                    user = await self.bot.fetch_user(discord_id)
                    if user:
                        await user.send(f"You have been removed from the {mode_name} queue due to inactivity.")

        except Exception as e:
            print(f"Error in check_queue_timeouts: {e}")

    @check_queue_timeouts.before_loop
    async def before_check_queue_timeouts(self):
        await self.bot.wait_until_ready()

    @commands.command(aliases=["s", "S"])
    async def status(self, ctx):
        player_id = ctx.author.id
        queue_statuses = self.db.get_queue_status(player_id)

        if queue_statuses:
            mode_names = [self.reverse_mode_map.get(qs, "Unknown Mode") for qs in queue_statuses]
            await ctx.send(f"{ctx.author.name}, you are in the queue for the following modes: {', '.join(mode_names)}.")
            return

        match_details = self.db.get_match_details(player_id)
        if match_details and match_details[0] is not None and match_details[1] is not None:
            opponent, GameModeID = match_details
            mode_name = self.reverse_mode_map.get(GameModeID, "Unknown Mode")
            thread_id = self.db.get_match_thread(player_id, opponent, GameModeID)
            if thread_id:
                thread = self.bot.get_channel(thread_id)
                if thread:
                    await ctx.send(f'{ctx.author.name}, you are in a match ({mode_name}) against <@{opponent}> in {thread.jump_url}.')
                    return
            await ctx.send(f'{ctx.author.name}, you are in a match ({mode_name}) against <@{opponent}>.')
        else:
            await ctx.send(f'{ctx.author.name}, you are not in queue or in a match.')

    @commands.command(aliases=["q", "Q", "Queue"])
    async def queue(self, ctx, *, modes: str):
        if ctx.channel.name != "queue":
            await ctx.send("This command is only available in the #queue channel.")
            return

        mode_map = {"l": "land", "c": "conquest", "d": "domination", "ld": "luckydice"}
        requested_modes = [mode.strip() for mode in modes.split(',')]
        
        if not requested_modes:
            await ctx.send("Please specify at least one mode to queue for.")
            return

        self.db.add_player(ctx.author.id)

        queued_modes = []
        already_in_queue_modes = []
        invalid_modes = []

        for mode_arg in requested_modes:
            mode_name = mode_map.get(mode_arg.lower(), mode_arg)
            if mode_name not in self.mode_map:
                invalid_modes.append(mode_name)
                continue

            game_mode_id = self.mode_map[mode_name]
            self.db.add_player_mode(ctx.author.id, game_mode_id)

            if game_mode_id in self.db.get_queue_status(ctx.author.id):
                already_in_queue_modes.append(mode_name)
                continue

            match_details = self.db.get_match_details(ctx.author.id)
            if match_details and all(match_details):
                await ctx.send(f"{ctx.author.name}, you are already in a match. Please finish it before queuing again.")
                return

            self.db.add_to_queue(ctx.author.id, game_mode_id)
            
            player_count = self.db.get_queue_players_count(game_mode_id)
            
            if player_count >= 2:
                queue_players = self.db.get_queue_players(game_mode_id)
                if len(queue_players) >= 2:
                    players = [queue_players[0][0], queue_players[1][0]]
                    random.shuffle(players)
                    player1, player2 = players[0], players[1]

                    self.db.remove_from_all_queues(player1)
                    self.db.remove_from_all_queues(player2)
                    try:
                        forum_channel = self.bot.get_channel(self.bot.config.FORUM_CHANNEL_ID)
                        player1_name = (await self.bot.fetch_user(player1)).name
                        player2_name = (await self.bot.fetch_user(player2)).name
                        player1_elo = self.db.get_player_rating(player1, game_mode_id)
                        player2_elo = self.db.get_player_rating(player2, game_mode_id)

                        selected_maps = []
                        if mode_name == "domination":
                            if len(domination_constant_maps) >= 2 and len(season0_domination_maps) >= 1:
                                selected_maps.extend(random.sample(domination_constant_maps, 2))
                                selected_maps.append(random.choice(season0_domination_maps))
                                random.shuffle(selected_maps)
                        elif mode_name == "conquest":
                            if len(conquest_maps) >= 3:
                                selected_maps = random.sample(list(conquest_maps), 3)
                        elif mode_name == "luckydice":
                            if len(conquest_maps) >= 3:
                                selected_maps = random.sample(list(conquest_maps), 3)
                        elif mode_name == "land":
                            if len(land_maps) >= 3:
                                selected_maps = random.sample(land_maps, 3)

                        maps_message = ""
                        if selected_maps:
                            if mode_name in ["conquest", "luckydice"]:
                                maps_message = "\n\n**🗺️ Maps for this match:**\n" + "\n".join(f"> • {name} <#{thread_id}>" for name, thread_id in conquest_maps.items() if name in selected_maps)
                            else:
                                maps_message = "\n\n**🗺️ Maps for this match:**\n> • " + "\n> • ".join(selected_maps)

                        mode_tag_map = {
                            "land": 1387922476243226635,
                            "conquest": 1387922512385544285,
                            "domination": 1387922530647539842,
                            "luckydice": 1387922551979905054
                        }

                        mode_tag_id = mode_tag_map.get(mode_name)
                        available_tags = forum_channel.available_tags
                        mode_tag = next((tag for tag in available_tags if tag.id == mode_tag_id), None)

                        thread = await forum_channel.create_thread(
                            name=f"{player1_name} vs {player2_name}",
                            content=f'Match found: <@{player1}> ({player1_elo} ELO) vs <@{player2}> ({player2_elo} ELO) in {mode_name} mode!',
                            applied_tags=[mode_tag]
                        )

                        if mode_tag is None:
                            await ctx.send(f"Could not find the tag for {mode_name} mode.")
                            return

                        await thread.thread.send(f"""
                        **🔀 Player Roles (Randomly Assigned):**
                        > • **Player 1**: <@{player1}>
                        > • **Player 2**: <@{player2}>
                        """)

                        match_id = self.db.create_match(player1, player2, game_mode_id, thread.thread.id, selected_maps)

                        message_link = self.bot.config.RULES_MESSAGE_LINKS.get(mode_name)
                        if message_link and "YOUR_SERVER_ID" not in message_link:
                            match = re.match(r"https://(?:discord|discordapp).com/channels/\d+/(\d+)/(\d+)", message_link)
                            if match:
                                channel_id, message_id = map(int, match.groups())
                                try:
                                    channel = self.bot.get_channel(channel_id)
                                    message = await channel.fetch_message(message_id)
                                    await thread.thread.send(message.content)
                                except (discord.NotFound, discord.Forbidden):
                                    await thread.thread.send(f"Rules for {mode_name} could not be found or accessed.")
                            else:
                                await thread.thread.send(f"Invalid rules message link format for {mode_name}.")
                        else:
                            await thread.thread.send(f"No rules defined for {mode_name}. Please update the rules message link in `utils/config.py`.")

                        await thread.thread.send(maps_message)
                        
                        if mode_name == "luckydice":
                            faction_names = list(factions.keys())
                            random.shuffle(faction_names)

                            player1_factions_pool = faction_names[:5]
                            player2_factions_pool = faction_names[5:10]

                            self.db.create_luckydice_match(match_id, player1, player2, player1_factions_pool, player2_factions_pool)

                            view = InitiateFactionSelectView(self.db, match_id, selected_maps, self.bot)
                            message = await thread.thread.send(f"<@{player1}> and <@{player2}>, please select your factions.", view=view)
                            self.db.update_match_message_id(match_id, message.id)

                        return 

                    except (discord.HTTPException, discord.Forbidden) as e:
                        await ctx.send(f"Error creating match thread: {e}")
                    except Exception as e:
                        await ctx.send(f"An unexpected error occurred while creating the match: {e}")
                return
            else:
                queued_modes.append(mode_name)

        response_parts = []
        if queued_modes:
            response_parts.append(f"joined the queue for {', '.join(queued_modes)}")
        if already_in_queue_modes:
            response_parts.append(f"you are already in the queue for {', '.join(already_in_queue_modes)}")
        if invalid_modes:
            response_parts.append(f"invalid mode(s): {', '.join(invalid_modes)}")

        if response_parts:
            full_response = f"{ctx.author.name}, " + " and ".join(response_parts) + "."
            await ctx.send(full_response)

    @commands.command(aliases=["e", "dq", "dequeue", "leave", "E", "DQ", "Dequeue", "Leave", "Dq"])
    async def exit(self, ctx, *, modes: str = None):
        player_id = ctx.author.id

        if modes is None:
            queue_statuses = self.db.get_queue_status(player_id)
            if queue_statuses:
                left_modes = []
                for queue_status in queue_statuses:
                    self.db.mark_as_unqueued(player_id, queue_status)
                    mode_name = self.reverse_mode_map.get(queue_status, "Unknown Mode")
                    left_modes.append(mode_name)
                if left_modes:
                    await ctx.send(f"{ctx.author.name} left the queue for {', '.join(left_modes)}.")
                return
        else:
            mode_map = {"l": "land", "c": "conquest", "d": "domination", "ld": "luckydice"}
            requested_modes = [mode.strip() for mode in modes.split(',')]

            left_modes = []
            not_in_queue_modes = []
            invalid_modes = []

            for mode_arg in requested_modes:
                mode_name = mode_map.get(mode_arg.lower(), mode_arg)
                if mode_name not in self.mode_map:
                    invalid_modes.append(mode_name)
                    continue

                game_mode_id = self.mode_map[mode_name]
                if game_mode_id in self.db.get_queue_status(player_id):
                    self.db.mark_as_unqueued(player_id, game_mode_id)
                    left_modes.append(mode_name)
                else:
                    not_in_queue_modes.append(mode_name)
            
            response_parts = []
            if left_modes:
                response_parts.append(f"left the queue for {', '.join(left_modes)}")
            if not_in_queue_modes:
                response_parts.append(f"you were not in the queue for {', '.join(not_in_queue_modes)}")
            if invalid_modes:
                response_parts.append(f"invalid mode(s): {', '.join(invalid_modes)}")

            if response_parts:
                full_response = f"{ctx.author.name}, " + " and ".join(response_parts) + "."
                await ctx.send(full_response)
            return

        match_details = self.db.get_match_details(player_id)
        if match_details and all(match_details):
            opponent, GameModeID = match_details
            mode_name = self.reverse_mode_map.get(GameModeID, "Unknown Mode")

            match_id = self.db.get_active_match(player_id)
            if match_id:
                self.db.cursor.execute("SELECT bettor_id, amount FROM bets WHERE match_id = ? AND resolved = FALSE", (match_id,))
                unresolved_bets = self.db.cursor.fetchall()

                for bettor_id, amount in unresolved_bets:
                    self.db.update_player_balance(self.db.get_player_id(bettor_id), self.db.get_player_balance(self.db.get_player_id(bettor_id)) + amount)
                self.db.cursor.execute("UPDATE bets SET resolved = TRUE WHERE match_id = ?", (match_id,))
                self.db.conn.commit()

            self.db.remove_match(player_id, opponent)
            await ctx.send(f"{ctx.author.name} left the match for {mode_name} mode.")
            return

        await ctx.send(f"{ctx.author.name}, you are not in queue or in an active match.")

    @commands.command(aliases=["r", "R"])
    async def result(self, ctx, outcome: str, scores: str = None):
        if outcome.lower() not in ["win", "w", "loss", "l"]:
            await ctx.send("Invalid result. Use `!r win` or `!r loss`. For Lucky Dice, use `!r <w/l> <scores>` (e.g., `!r w 101`).")
            return

        match_details = self.db.get_match_details(ctx.author.id)
        if not match_details or match_details[0] is None:
            await ctx.send("You are not in an active match.")
            return

        opponent, GameModeID = match_details
        mode_name = self.reverse_mode_map.get(GameModeID, "Unknown Mode")

        match_id = self.db.get_active_match(ctx.author.id)
        if not match_id:
            await ctx.send("No active match found.")
            return

        if mode_name == "luckydice":
            if scores is None:
                await ctx.send("Please provide the scores for the Lucky Dice match (e.g., `!r w 101`).")
                return

            if len(scores) != 3 or not all(c in '01' for c in scores):
                await ctx.send("Invalid score format. Please use a 3-digit string of 1s and 0s (e.g., `101`).")
                return

            wins = scores.count('1')
            losses = scores.count('0')

            if (outcome.lower() in ["win", "w"] and wins <= losses) or (outcome.lower() in ["loss", "l"] and losses <= wins):
                await ctx.send("The scores you provided do not match the win/loss outcome.")
                return

            if outcome.lower() in ["win", "w"]:
                winner_id = ctx.author.id
                loser_id = opponent
            else:
                winner_id = opponent
                loser_id = ctx.author.id

            selections = self.db.get_luckydice_selections(match_id)
            if not selections or not selections[5] or not selections[6]:
                await ctx.send("Faction selections are not complete for this match. Please make sure both players have selected their factions.")
                return
                
            player1_factions = selections[5].split(',')
            player2_factions = selections[6].split(',')
            
            maps = self.db.get_match_maps(match_id)

            game_results = []
            
            winner_name = (await self.bot.fetch_user(winner_id)).display_name
            loser_name = (await self.bot.fetch_user(loser_id)).display_name

            for i, score in enumerate(scores):
                if score == '1':
                    game_winner_id = ctx.author.id
                    game_loser_id = opponent
                else:
                    game_winner_id = opponent
                    game_loser_id = ctx.author.id

                p1_faction = player1_factions[i]
                p2_faction = player2_factions[i]

                winner_faction = p1_faction if game_winner_id == selections[1] else p2_faction
                loser_faction = p1_faction if game_loser_id == selections[1] else p2_faction

                self.db.update_faction_stats(winner_faction, True)
                self.db.update_faction_stats(loser_faction, False)
                self.db.update_player_faction_stats(game_winner_id, winner_faction, True)
                self.db.update_player_faction_stats(game_loser_id, loser_faction, False)
                
                game_winner_name = (await self.bot.fetch_user(game_winner_id)).display_name
                game_loser_name = (await self.bot.fetch_user(game_loser_id)).display_name

                game_results.append(f"{maps[i]}: ||@{game_winner_name} ({factions[winner_faction]}) defeats @{game_loser_name} ({factions[loser_faction]})||")

            winner_rating_before = self.db.get_player_rating(winner_id, GameModeID)
            loser_rating_before = self.db.get_player_rating(loser_id, GameModeID)

            new_winner_rating, new_loser_rating = update_elo(winner_rating_before, loser_rating_before, K=16)

            self.db.record_luckydice_match(
                winner_id,
                loser_id,
                GameModeID,
                winner_rating_before,
                new_winner_rating,
                loser_rating_before,
                new_loser_rating
            )

            response = "**Lucky Dice Match Results:**\n\n"
            response += "\n".join(game_results)
            response += f"\n\nRating change: @{winner_name} **{new_winner_rating} **(+{new_winner_rating - winner_rating_before}) | @{loser_name} **{new_loser_rating} **({new_loser_rating - loser_rating_before})\n\n"
            response += "**Please, both players attach replays to this thread!**"

            self.db.resolve_bets(match_id, winner_id)
            self.db.remove_match(winner_id, loser_id)
            await self.bot.get_cog('Leaderboard').update_leaderboard(GameModeID)
            await self.assign_role_based_on_wins(ctx, winner_id)

            winner_db_id = self.db.get_player_id(winner_id)
            perks = self.db.get_player_perks(winner_db_id)
            taunt = None
            for perk_type, data in perks:
                if perk_type == 'taunt':
                    taunt = data
            
            if taunt:
                response += f"\n\n**{ctx.guild.get_member(winner_id).display_name} says:** {taunt}"

            self.bot.dispatch("luckydice_match_finished")
            await ctx.send(response)
            return

        if outcome.lower() in ["win", "w"]:
            winner_id = ctx.author.id
            loser_id = opponent
        else:
            winner_id = opponent
            loser_id = ctx.author.id
        if outcome.lower() not in ["win", "w", "loss", "l"]:
            await ctx.send("Invalid result. Use `/r win` or `/r loss`. ")
            return

        match_details = self.db.get_match_details(ctx.author.id)
        if not match_details or match_details[0] is None:
            await ctx.send("You are not in an active match.")
            return

        opponent, GameModeID = match_details

        match_id = self.db.get_active_match(ctx.author.id)
        if not match_id:
            await ctx.send("No active match found.")
            return

        if outcome.lower() in ["win", "w"]:
            winner_id = ctx.author.id
            loser_id = opponent
        else:
            winner_id = opponent
            loser_id = ctx.author.id

        winner_rating_before = self.db.get_player_rating(winner_id, GameModeID)
        loser_rating_before = self.db.get_player_rating(loser_id, GameModeID)

        new_winner_rating, new_loser_rating = update_elo(winner_rating_before, loser_rating_before)
        self.db.update_player_rating(winner_id, GameModeID, new_winner_rating)
        self.db.update_player_rating(loser_id, GameModeID, new_loser_rating)

        self.db.record_match_result(
            winner_id,
            loser_id,
            GameModeID,
            winner_rating_before,
            new_winner_rating,
            loser_rating_before,
            new_loser_rating
        )

        self.db.resolve_bets(match_id, winner_id)
        self.db.remove_match(winner_id, loser_id)

        await self.bot.get_cog('Leaderboard').update_leaderboard(GameModeID)

        await self.assign_role_based_on_wins(ctx, winner_id)

        winner_db_id = self.db.get_player_id(winner_id)
        perks = self.db.get_player_perks(winner_db_id)
        taunt = None
        for perk_type, data in perks:
            if perk_type == 'taunt':
                taunt = data

        response = f"Match result recorded: <@{winner_id}> wins in {self.reverse_mode_map.get(GameModeID, 'Unknown Mode')} mode!\n"
        response += f"Rating change:\n<@{winner_id}>, {new_winner_rating} (+{new_winner_rating - winner_rating_before}) \n"
        response += f"<@{loser_id}>, {new_loser_rating} ({new_loser_rating - loser_rating_before})"

        if taunt:
            response += f"\n\n**{ctx.guild.get_member(winner_id).display_name} says:** {taunt}"

        await ctx.send(response)

    @commands.command(aliases=["m", "M"])
    async def matches(self, ctx):
        try:
            self.db.cursor.execute("""
                SELECT 
                    m.id,
                    m.player1 as player1_id,
                    m.player2 as player2_id,
                    g.name as mode_name,
                    m.thread_id
                FROM matches m
                JOIN gamemode g ON m.GameModeID = g.id
                WHERE EXISTS (SELECT 1 FROM players p WHERE p.discord_id = m.player1)
                AND EXISTS (SELECT 1 FROM players p WHERE p.discord_id = m.player2)
            """)
            matches = self.db.cursor.fetchall()
            print(f"Corrected joined matches: {matches}")  # Debug

            if not matches:
                await ctx.send("No active matches at the moment.")
                return

            response = ["**Currently Active Matches:**"]
            for match_id, player1_id, player2_id, mode_name, thread_id in matches:
                try:
                    player1 = await self.bot.fetch_user(int(player1_id))
                    player2 = await self.bot.fetch_user(int(player2_id))

                    thread_info = ""
                    if thread_id:
                        try:
                            thread = await self.bot.fetch_channel(int(thread_id))
                            thread_info = f" | Thread: {thread.jump_url}"
                        except:
                            thread_info = f" | Thread ID: {thread_id}"

                    response.append(
                        f"`#{match_id}` {player1.name} vs {player2.name} | "
                        f"Mode: {mode_name}{thread_info}"
                    )

                except Exception as e:
                    print(f"Error processing match {match_id}: {e}")
                    response.append(
                        f"`#{match_id}` Player {player1_id} vs Player {player2_id} | "
                        f"Mode: {mode_name}"
                    )

            await ctx.send("\n".join(response))

        except Exception as e:
            print(f"Error in matches command: {e}")
            await ctx.send(f"Error fetching matches: {str(e)}")

    @commands.command(aliases=["rf"])
    async def rfaction(self, ctx, n: int = 24):
        faction_list = list(factions.values())
        if n > len(faction_list):
            await ctx.send(f"Cannot select {n} unique factions. There are only {len(faction_list)} factions available.")
            return
        if n == 0:
            await ctx.send("Can't be 0")
            return
        elif n < 0:
            await ctx.send("Can't be negative")
            return
        selected_factions = random.sample(faction_list, n)
        await ctx.send(" ".join(selected_factions) + ".")

    @commands.command()
    async def rmaps(self, ctx, mode: str, n: int = 5):
        mode = mode.lower()
        map_pools = {
            "d": domination_constant_maps + season0_domination_maps,
            "c": conquest_maps,
            "l": land_maps
        }

        if mode not in map_pools:
            await ctx.send("Invalid mode. Please use 'd' for domination, 'c' for conquest, or 'l' for land.")
            return

        map_pool = map_pools[mode]
        if isinstance(map_pool, dict):
            map_names = list(map_pool.keys())
        else:
            map_names = list(map_pool)

        if n > len(map_names):
            await ctx.send(
                f"Cannot select {n} unique maps for this mode. There are only {len(map_names)} maps available.")
            return

        selected_maps = random.sample(map_names, n)

        if isinstance(map_pool, dict):
            maps_message = "\n\n**🗺️ Maps:**\n" + "\n".join(
                f"> • {name} <#{map_pool[name]}>" for name in selected_maps
            )
        else:
            maps_message = "\n\n**🗺️ Maps:**\n" + "\n".join(
                f"> • {name}" for name in selected_maps
            )

        await ctx.send(maps_message)

    async def assign_reward_role(self, member, role_id):
        role = member.guild.get_role(role_id)
        if role:
            await member.add_roles(role)
            return True
        return False

    async def assign_role_based_on_wins(self, ctx, user_id):
        member = ctx.guild.get_member(user_id)
        if member is None:
            print("no member found")
            return

        reward_name, role_id, roles_to_remove_ids = self.db.check_win_reward(user_id)

        if roles_to_remove_ids:
            for role_to_remove_id in roles_to_remove_ids:
                role = member.guild.get_role(role_to_remove_id)
                if role and role in member.roles:
                    await member.remove_roles(role)
                    self.db.cursor.execute("DELETE FROM user_rewards WHERE user_id = ? AND role_id = ?",
                                            (self.db.get_player_id(user_id), role_to_remove_id))
                    self.db.conn.commit()

        if role_id:
            self.db.assign_reward(self.db.get_player_id(user_id), reward_name, role_id)
            success = await self.assign_reward_role(member, role_id)
            if success:
                await ctx.send(f"{member.mention} has been promoted to **{reward_name}**!")
            else:
                await ctx.send(f"Could not assign the role '{reward_name}' to {member.mention}.")

async def setup(bot):
    await bot.add_cog(Matches(bot))