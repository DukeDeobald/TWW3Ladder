

import discord
from discord.ext import commands
import random
from database import Database
from logic import update_elo

from utils.maps import MODE_MAP, REVERSE_MODE_MAP, domination_constant_maps, season0_domination_maps, conquest_maps, land_maps

class Matches(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.mode_map = MODE_MAP
        self.reverse_mode_map = REVERSE_MODE_MAP

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
        for mode_arg in requested_modes:
            mode_name = mode_map.get(mode_arg.lower(), mode_arg)
            if mode_name not in self.mode_map:
                await ctx.send(f"Invalid mode: '{mode_name}'.")
                continue

            game_mode_id = self.mode_map[mode_name]
            self.db.add_player_mode(ctx.author.id, game_mode_id)

            if game_mode_id in self.db.get_queue_status(ctx.author.id):
                await ctx.send(f"{ctx.author.name}, you are already in the queue for {mode_name} mode.")
                continue

            match_details = self.db.get_match_details(ctx.author.id)
            if match_details and all(match_details):
                await ctx.send(f"{ctx.author.name}, you are already in a match. Please finish it before queuing again.")
                return

            self.db.add_to_queue(ctx.author.id, game_mode_id)
            player_count = self.db.get_queue_players_count(game_mode_id)
            await ctx.send(f"{ctx.author.mention} joined the queue for {mode_name} mode. Players in queue: {player_count}.")
            queued_modes.append(mode_name)

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
                        elif mode_name == "conquest" or mode_name == "luckydice":
                            if len(conquest_maps) >= 3:
                                selected_maps = random.sample(conquest_maps, 3)
                        elif mode_name == "land":
                            if len(land_maps) >= 3:
                                selected_maps = random.sample(land_maps, 3)

                        maps_message = "" 
                        if selected_maps:
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

                        if mode_name in ["land", "conquest"]:
                            await thread.thread.send("""
                            **⚔️ Pick/Ban System Rules**
    
                            __**1. Global Bans Phase**__
                            > • Player 1 bans 1 faction (globally banned)
                            > • Player 2 bans 1 faction (globally banned)
    
                            __**2. Game 1**__
                            > • Player 1 pre-picks 3 factions and bans 1 faction for Player 2  
                            > • Player 2 bans 1 faction from Player 1's pre-picks, then picks their faction  
                            > • Player 1 chooses one of their 2 remaining factions
    
                            __**3. Game 2**__
                            > • Player 2 pre-picks 3 factions and bans 1 faction for Player 1  
                            > • Player 1 bans 1 faction from Player 2's pre-picks, then picks their faction  
                            > • Player 2 chooses one of their 2 remaining factions
    
                            __**4. Game 3 (If tied 1-1)**__
                            > • Winner of Game 2 pre-picks 2 factions and bans 1 for the opponent  
                            > • Opponent picks their faction  
                            > • Winner selects one of their 2 pre-picked factions
    
                            🔔 **Players should coordinate their picks/bans in this thread.**
                            """)

                        elif mode_name == "domination":
                            await thread.thread.send("""
                            Actions described below use https://aoe2cm.net/preset/dEQGL
                            Each player has 1 unrestricted global ban. After that players will pick factions in order 1-2 2-1. The final pick will be determined through blind pick.
                            After picks are done, each player bans 4 out of 9 potential matchups (use 1-2-2-2-1 pattern, where player 1 starts). Once all bans are settled, the remaining matchup is the one that will be played.
                            For simplicity, you can use this ban matrix template:
                            -----  WE  EMP  NOR
                            VP     o   o    o
                            BM     o   o    o
                            BR     o   o    o
                            """)

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
                            "conquest": "**⚔️ Conquest Mode Rules:**\n-"
                                        "Unit caps MUST be ON.\n"
                                        "Tickets set to 650",
                            "domination": "**🏆 Domination Mode Rules:**\n- "
                                          "Unit caps MUST be ON.\n"
                                          "Default funds\n"
                                          "Ultra units scale\n"
                                          "Tickets set to 1500",
                            "luckydice": "**🎲 Lucky Dice Mode Rules:**\n- **ULTRA FUNDS** (17,000).\n- Each player can roll up to 5 times in total: meaning you can have maximum of 4 factions rolls, and it leaves you with 1 roll for a build. If a player rolls more than 5 times, they receive a technical loss in that battle. (Note: you can use unspent gold to give units chevrons. It is also possible to remove some units, but this money can still only be used for chevrons.).\n- The mode is Conquest, with 600 tickets.\n- Unit caps must be ON.\n"
                        }

                        if mode_name in mode_rules:
                            await thread.thread.send(mode_rules[mode_name])
                            await thread.thread.send(maps_message)

                        self.db.create_match(player1, player2, game_mode_id, thread.thread.id)

                    except (discord.HTTPException, discord.Forbidden) as e:
                        await ctx.send(f"Error creating match thread: {e}")
                    except Exception as e:
                        await ctx.send(f"An unexpected error occurred while creating the match: {e}")

    @commands.command(aliases=["e", "dq", "dequeue", "leave", "E", "DQ", "Dequeue", "Leave", "Dq"])
    async def exit(self, ctx, *, modes: str = None):
        player_id = ctx.author.id

        if modes is None:
            queue_statuses = self.db.get_queue_status(player_id)
            if queue_statuses:
                for queue_status in queue_statuses:
                    self.db.mark_as_unqueued(player_id, queue_status)
                    mode_name = self.reverse_mode_map.get(queue_status, "Unknown Mode")
                    await ctx.send(f"{ctx.author.name} left the queue for {mode_name} mode.")
                return
        else:
            mode_map = {"l": "land", "c": "conquest", "d": "domination", "ld": "luckydice"}
            requested_modes = [mode.strip() for mode in modes.split(',')]

            for mode_arg in requested_modes:
                mode_name = mode_map.get(mode_arg.lower(), mode_arg)
                if mode_name not in self.mode_map:
                    await ctx.send(f"Invalid mode: '{mode_name}'.")
                    continue

                game_mode_id = self.mode_map[mode_name]
                if game_mode_id in self.db.get_queue_status(player_id):
                    self.db.mark_as_unqueued(player_id, game_mode_id)
                    await ctx.send(f"{ctx.author.name} left the queue for {mode_name} mode.")
                else:
                    await ctx.send(f"{ctx.author.name}, you are not in the queue for {mode_name} mode.")
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
    async def result(self, ctx, outcome: str):
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

        await ctx.send(
            f"Match result recorded: <@{winner_id}> wins in {self.reverse_mode_map.get(GameModeID, 'Unknown Mode')} mode!\n"
            f"Rating change:\n<@{winner_id}>, {new_winner_rating} (+{new_winner_rating - winner_rating_before}) \n"
            f"<@{loser_id}>, {new_loser_rating} ({new_loser_rating - loser_rating_before})"
        )

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

