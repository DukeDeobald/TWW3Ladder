import sqlite3
from datetime import datetime


class Database:
    def __init__(self, db_path="ladder.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self._create_tables()

    def _create_tables(self):
        self.cursor.executescript("""
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY, 
                discord_id INTEGER UNIQUE,
                tokens INTEGER DEFAULT 100,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS gamemode (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS player_ratings (
                player_id INTEGER, 
                GameModeID INTEGER, 
                elo INT DEFAULT 1000,   
                matches INTEGER DEFAULT 0, 
                wins INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (player_id, GameModeID),
                FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,
                FOREIGN KEY (GameModeID) REFERENCES gamemode(id)
            );

            CREATE TABLE IF NOT EXISTS queue (
                discord_id INTEGER,
                GameModeID INTEGER,
                is_matched BOOLEAN DEFAULT FALSE,
                is_unqueued BOOLEAN DEFAULT FALSE,
                timestamp_queued TEXT,
                timestamp_matched TEXT,
                timestamp_unqueued TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (discord_id, GameModeID),
                FOREIGN KEY (GameModeID) REFERENCES gamemode(id)
            );

            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                player1 INTEGER, 
                player2 INTEGER, 
                GameModeID INTEGER, 
                thread_id INTEGER,  
                message_id INTEGER,
                maps TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (GameModeID) REFERENCES gamemode(id)
            );

            CREATE TABLE IF NOT EXISTS match_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player1 INTEGER,
                player2 INTEGER,
                winner INTEGER,
                GameModeID INTEGER,
                elo_before_winner INTEGER,
                elo_after_winner INTEGER,
                elo_before_loser INTEGER,
                elo_after_loser INTEGER,
                datetime TEXT,
                FOREIGN KEY (GameModeID) REFERENCES gamemode(id)
            );

            INSERT OR IGNORE INTO gamemode (id, name) VALUES (1, 'land');
            INSERT OR IGNORE INTO gamemode (id, name) VALUES (2, 'conquest');
            INSERT OR IGNORE INTO gamemode (id, name) VALUES (3, 'domination');
            INSERT OR IGNORE INTO gamemode (id, name) VALUES (4, 'luckydice');

            CREATE TABLE IF NOT EXISTS bets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id INTEGER,
                bettor_id INTEGER,
                bet_side INTEGER, 
                amount INTEGER,
                placed_at TEXT,
                resolved BOOLEAN DEFAULT FALSE,
                FOREIGN KEY (match_id) REFERENCES matches(id),
                FOREIGN KEY (bettor_id) REFERENCES players(id)
            );

            CREATE TABLE IF NOT EXISTS user_rewards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                reward_name TEXT,
                role_id INTEGER,
                awarded_at TEXT,
                expires_at TEXT NULL,
                FOREIGN KEY (user_id) REFERENCES players(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT DEFAULT (datetime('now')),
                command TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                user_name TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS shop_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                price INTEGER NOT NULL
            );

            INSERT OR IGNORE INTO shop_items (name, description, price) VALUES 
                ('Leaderboard Highlight', 'Highlight your name on the leaderboard for 7 days.', 50),
                ('Custom Taunt', 'Set a custom message that displays when you win a match.', 100);

            CREATE TABLE IF NOT EXISTS player_perks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER,
                perk_type TEXT NOT NULL,
                data TEXT,
                expires_at TEXT,
                FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS luckydice_selections (
                match_id INTEGER PRIMARY KEY,
                player1_id INTEGER NOT NULL,
                player2_id INTEGER NOT NULL,
                player1_faction_pool TEXT,
                player2_faction_pool TEXT,
                player1_selected_factions TEXT,
                player2_selected_factions TEXT,
                player1_ready BOOLEAN DEFAULT FALSE,
                player2_ready BOOLEAN DEFAULT FALSE,
                FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS faction_stats (
                faction_name TEXT PRIMARY KEY,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS player_faction_stats (
                player_id INTEGER,
                faction_name TEXT,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                PRIMARY KEY (player_id, faction_name),
                FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
            );
        """)
            

    def update_faction_stats(self, faction_name, won):
        if won:
            self.cursor.execute("INSERT INTO faction_stats (faction_name, wins) VALUES (?, 1) ON CONFLICT(faction_name) DO UPDATE SET wins = wins + 1", (faction_name,))
        else:
            self.cursor.execute("INSERT INTO faction_stats (faction_name, losses) VALUES (?, 1) ON CONFLICT(faction_name) DO UPDATE SET losses = losses + 1", (faction_name,))
        self.conn.commit()

    def update_player_faction_stats(self, player_id, faction_name, won):
        db_player_id = self.get_player_id(player_id)
        if won:
            self.cursor.execute("INSERT INTO player_faction_stats (player_id, faction_name, wins) VALUES (?, ?, 1) ON CONFLICT(player_id, faction_name) DO UPDATE SET wins = wins + 1", (db_player_id, faction_name))
        else:
            self.cursor.execute("INSERT INTO player_faction_stats (player_id, faction_name, losses) VALUES (?, ?, 1) ON CONFLICT(player_id, faction_name) DO UPDATE SET losses = losses + 1", (db_player_id, faction_name))
        self.conn.commit()

    def get_faction_stats(self):
        self.cursor.execute("SELECT faction_name, wins, losses FROM faction_stats")
        return self.cursor.fetchall()

    def get_player_faction_stats(self, player_id):
        db_player_id = self.get_player_id(player_id)
        self.cursor.execute("SELECT faction_name, wins, losses FROM player_faction_stats WHERE player_id = ?", (db_player_id,))
        return self.cursor.fetchall()

    def log_event(self, command, user_id, user_name):
        now = datetime.now().isoformat()
        self.cursor.execute("""
            INSERT INTO logs (timestamp, command, user_id, user_name)
            VALUES (?, ?, ?, ?)
        """, (now, command, user_id, user_name))
        self.conn.commit()

    def add_player(self, discord_id):
        now = datetime.now().isoformat()
        self.cursor.execute("""
            INSERT INTO players (discord_id, created_at, updated_at) 
            VALUES (?, ?, ?)
            ON CONFLICT(discord_id) DO UPDATE SET updated_at = ?
        """, (discord_id, now, now, now))
        self.conn.commit()

    def add_player_mode(self, discord_id, GameModeID):
        self.cursor.execute("SELECT id FROM players WHERE discord_id = ?", (discord_id,))
        player = self.cursor.fetchone()

        if player:
            player_id = player[0]
            self.cursor.execute("""
                INSERT OR IGNORE INTO player_ratings (player_id, GameModeID, elo, matches, wins)
                VALUES (?, ?, 1000, 0, 0)
            """, (player_id, GameModeID))
            self.conn.commit()

    def get_elo(self, discord_id, GameModeID):
        self.cursor.execute("""
            SELECT elo FROM player_ratings 
            WHERE player_id = (SELECT id FROM players WHERE discord_id = ?) AND GameModeID = ?
        """, (discord_id, GameModeID))
        result = self.cursor.fetchone()
        return result[0] if result else 1000

    def update_elo(self, discord_id, GameModeID, new_elo):
        self.cursor.execute("""
            UPDATE player_ratings 
            SET elo = ?
            WHERE player_id = (SELECT id FROM players WHERE discord_id = ?) AND GameModeID = ?
        """, (new_elo, discord_id, GameModeID))
        self.conn.commit()

    def get_queue_players(self, GameModeID):
        self.cursor.execute("""
            SELECT discord_id FROM queue 
            WHERE GameModeID = ? AND is_matched = FALSE AND is_unqueued = FALSE
        """, (GameModeID,))
        return self.cursor.fetchall()

    def get_queue_players_count(self, GameModeID):
        self.cursor.execute("""
            SELECT COUNT(*) FROM queue 
            WHERE GameModeID = ? AND is_matched = FALSE AND is_unqueued = FALSE
        """, (GameModeID,))
        return self.cursor.fetchone()[0]

    def add_to_queue(self, discord_id, GameModeID):
        now = datetime.now().isoformat()
        self.cursor.execute("""
            INSERT INTO queue (discord_id, GameModeID, timestamp_queued, created_at, updated_at, is_unqueued)
            VALUES (?, ?, ?, ?, ?, FALSE)
            ON CONFLICT(discord_id, GameModeID) DO UPDATE SET
                is_unqueued = FALSE,
                timestamp_queued = excluded.timestamp_queued,
                updated_at = excluded.updated_at
        """, (discord_id, GameModeID, now, now, now))
        self.conn.commit()

        self.cursor.execute("SELECT discord_id FROM players WHERE discord_id = ?", (discord_id,))
        user = self.cursor.fetchone()
        if user:
            user_name = user[0]
            self.log_event("add_to_queue", discord_id, user_name)

    def remove_from_all_queues(self, discord_id):
        self.cursor.execute("DELETE FROM queue WHERE discord_id = ?", (discord_id,))
        self.conn.commit()

    def remove_from_queue(self, discord_id, GameModeID):
        self.cursor.execute("DELETE FROM queue WHERE discord_id = ? AND GameModeID = ?", (discord_id, GameModeID))
        self.conn.commit()

    def mark_as_unqueued(self, discord_id, GameModeID):
        now = datetime.now().isoformat()
        self.cursor.execute("""
            UPDATE queue 
            SET is_unqueued = TRUE, timestamp_unqueued = ?
            WHERE discord_id = ? AND GameModeID = ?
        """, (now, discord_id, GameModeID))
        self.conn.commit()

        self.cursor.execute("SELECT discord_id FROM players WHERE discord_id = ?", (discord_id,))
        user = self.cursor.fetchone()
        if user:
            user_name = user[0]
            self.log_event("mark_as_unqueued", discord_id, user_name)

    def create_match(self, player1, player2, GameModeID, thread_id, maps=None):
        now = datetime.now().isoformat()
        maps_str = ",".join(maps) if maps else None
        self.cursor.execute("""
            INSERT INTO matches (player1, player2, GameModeID, thread_id, maps, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (player1, player2, GameModeID, thread_id, maps_str, now, now))
        self.conn.commit()
        match_id = self.cursor.lastrowid

        self.cursor.execute("SELECT discord_id FROM players WHERE discord_id = ?", (player1,))
        user = self.cursor.fetchone()
        if user:
            user_name = user[0]
            self.log_event("create_match", player1, user_name)
        return match_id

    def update_match_message_id(self, match_id, message_id):
        self.cursor.execute("""
            UPDATE matches 
            SET message_id = ?
            WHERE id = ?
        """, (message_id, match_id))
        self.conn.commit()

    def get_match_message_id(self, match_id):
        self.cursor.execute("""
            SELECT message_id 
            FROM matches 
            WHERE id = ?
        """, (match_id,))
        result = self.cursor.fetchone()
        return result[0] if result else None

    def remove_match(self, player1_id, player2_id):
        self.cursor.execute("""
            DELETE FROM matches 
            WHERE (player1 = ? AND player2 = ?) 
               OR (player1 = ? AND player2 = ?)
        """, (player1_id, player2_id, player2_id, player1_id))
        self.conn.commit()

        self.cursor.execute("SELECT discord_id FROM players WHERE discord_id = ?", (player1_id,))
        user = self.cursor.fetchone()
        if user:
            user_name = user[0]
            self.log_event("remove_match", player1_id, user_name)

    def record_match_result(self, winner_id, loser_id, GameModeID, elo_before_winner, elo_after_winner,
                            elo_before_loser, elo_after_loser, match_id=None):
        now = datetime.now().isoformat()

        self.cursor.execute("SELECT id FROM players WHERE discord_id = ?", (winner_id,))
        winner_player_id = self.cursor.fetchone()[0]

        self.cursor.execute("SELECT id FROM players WHERE discord_id = ?", (loser_id,))
        loser_player_id = self.cursor.fetchone()[0]

        if match_id:
            self.cursor.execute("""
                UPDATE match_history
                SET winner = ?, elo_before_winner = ?, elo_after_winner = ?,
                    elo_before_loser = ?, elo_after_loser = ?
                WHERE id = ?
            """, (winner_player_id, elo_before_winner, elo_after_winner, elo_before_loser, elo_after_loser, match_id))
        else:
            self.cursor.execute("""
                INSERT INTO match_history (player1, player2, winner, GameModeID, 
                                           elo_before_winner, elo_after_winner, 
                                           elo_before_loser, elo_after_loser, datetime)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (winner_player_id, loser_player_id, winner_player_id, GameModeID, elo_before_winner, elo_after_winner,
                  elo_before_loser, elo_after_loser, now))

        self.cursor.execute("""
            UPDATE player_ratings 
            SET elo = ?, matches = matches + 1, wins = wins + 1
            WHERE player_id = ? AND GameModeID = ?
        """, (elo_after_winner, winner_player_id, GameModeID))

        self.cursor.execute("""
            UPDATE player_ratings 
            SET elo = ?, matches = matches + 1
            WHERE player_id = ? AND GameModeID = ?
        """, (elo_after_loser, loser_player_id, GameModeID))

        self.conn.commit()

    def get_queue_status(self, player_id):
        self.cursor.execute("""
            SELECT GameModeID FROM queue 
            WHERE discord_id = ? AND is_matched = FALSE AND is_unqueued = FALSE
        """, (player_id,))
        results = self.cursor.fetchall()
        return [result[0] for result in results] if results else []

    def get_match_details(self, player_id):
        self.cursor.execute("""
            SELECT player1, player2, GameModeID 
            FROM matches 
            WHERE player1 = ? OR player2 = ?
        """, (player_id, player_id))
        result = self.cursor.fetchone()

        if result:
            player1, player2, GameModeID = result
            opponent = player2 if player1 == player_id else player1
            return opponent, GameModeID
        return None, None

    def get_player_rating(self, discord_id, GameModeID):
        self.cursor.execute("""
            SELECT elo FROM player_ratings 
            WHERE player_id = (SELECT id FROM players WHERE discord_id = ?) AND GameModeID = ?
        """, (discord_id, GameModeID))
        result = self.cursor.fetchone()
        return result[0] if result else "N/A"

    def update_player_rating(self, player_id, GameModeID, rating):
        self.cursor.execute("""
            UPDATE player_ratings 
            SET elo = ?, matches = matches + 1
            WHERE player_id = ? AND GameModeID = ?
        """, (rating, player_id, GameModeID))
        self.conn.commit()

    def get_leaderboard(self, GameModeID, limit=10):
        self.cursor.execute("""
            SELECT p.discord_id, pr.elo, pr.matches, pr.wins 
            FROM player_ratings pr
            JOIN players p ON pr.player_id = p.id
            WHERE pr.GameModeID = ? AND pr.matches > 0
            ORDER BY pr.elo DESC
            LIMIT ?
        """, (GameModeID, limit))
        results = self.cursor.fetchall()
        return results

    def get_match_history(self, discord_id, limit=11):
        self.cursor.execute("""
            SELECT 
                (SELECT discord_id FROM players WHERE id = player1) AS player1_discord_id,
                (SELECT discord_id FROM players WHERE id = player2) AS player2_discord_id,
                (SELECT discord_id FROM players WHERE id = winner) AS winner_discord_id,
                GameModeID, 
                elo_before_winner, 
                elo_after_winner,
                elo_before_loser,
                elo_after_loser
            FROM match_history
            WHERE player1 = (SELECT id FROM players WHERE discord_id = ?) 
               OR player2 = (SELECT id FROM players WHERE discord_id = ?)
            ORDER BY id DESC
            LIMIT ?
        """, (discord_id, discord_id, limit))
        return self.cursor.fetchall()

    def get_queue_statistics(self):
        self.cursor.execute("""
            SELECT strftime('%Y-%m-%d %H:%M:%S', timestamp_queued) AS timestamp, 
                   COUNT(*) AS queue_count
            FROM queue 
            WHERE is_unqueued = FALSE 
            GROUP BY timestamp
            ORDER BY timestamp ASC
        """)
        results = self.cursor.fetchall()

        print("Raw Queue Data from SQLite:", results)

        return results

    def get_player_elo_history(self, discord_id, GameModeID):
        if not GameModeID:
            return []

        self.cursor.execute("""
            SELECT replace(substr(datetime, 1, 19), 'T', ' ') AS timestamp, 
                   CASE 
                       WHEN winner = (SELECT id FROM players WHERE discord_id = ?) THEN elo_after_winner
                       ELSE elo_after_loser
                   END AS elo
            FROM match_history
            WHERE (player1 = (SELECT id FROM players WHERE discord_id = ?) 
               OR player2 = (SELECT id FROM players WHERE discord_id = ?))
              AND GameModeID = ?
            ORDER BY timestamp ASC
        """, (discord_id, discord_id, discord_id, GameModeID))

        results = self.cursor.fetchall()

        return results

    def get_player_id(self, discord_id):
        self.cursor.execute("SELECT id FROM players WHERE discord_id = ?", (discord_id,))
        result = self.cursor.fetchone()
        return result[0] if result else None

    def get_discord_id(self, player_id):
        self.cursor.execute("SELECT discord_id FROM players WHERE id = ?", (player_id,))
        result = self.cursor.fetchone()
        return result[0] if result else None

    def get_player_balance(self, user_id):
        print(user_id)
        self.cursor.execute("SELECT tokens FROM players WHERE id = ?", (user_id,))
        result = self.cursor.fetchone()

        if result is None:
            raise ValueError(f"No player found with ID {user_id}.")

        return result[0]

    def update_player_balance(self, user_id, new_balance):
        now = datetime.now().isoformat()
        self.cursor.execute("""
            UPDATE players 
            SET tokens = ?, updated_at = ?
            WHERE id = ?
        """, (new_balance, now, user_id))
        self.conn.commit()

    def place_bet(self, bettor_id, match_id, bet_side, amount):
        now = datetime.now().isoformat()
        player_id = self.get_player_id(bettor_id)

        balance = self.get_player_balance(player_id)
        if balance < amount:
            raise ValueError("Insufficient balance to place the bet.")

        new_balance = balance - amount
        self.update_player_balance(player_id, new_balance)

        self.cursor.execute("""
            INSERT INTO bets (match_id, bettor_id, bet_side, amount, placed_at, resolved)
            VALUES (?, ?, ?, ?, ?, FALSE)
        """, (match_id, bettor_id, bet_side, amount, now))
        self.conn.commit()

    def resolve_bets(self, match_id, winner_id):
        self.cursor.execute("SELECT bettor_id, bet_side, amount FROM bets WHERE match_id = ? AND resolved = FALSE",
                            (match_id,))
        bets = self.cursor.fetchall()

        for bettor_id, bet_side, amount in bets:
            if bet_side == winner_id:
                winnings = amount * 2
                try:
                    new_balance = self.get_player_balance(self.get_player_id(bettor_id)) + winnings
                    self.update_player_balance(self.get_player_id(bettor_id), new_balance)
                except ValueError as e:
                    print(f"Error resolving bet for bettor {bettor_id}: {str(e)}")

        self.cursor.execute("UPDATE bets SET resolved = TRUE WHERE match_id = ?", (match_id,))
        self.conn.commit()

    def check_win_reward(self, discord_id):
        user_id = self.get_player_id(discord_id)
        if not user_id:
            return None, None, None

        self.cursor.execute("SELECT COUNT(*) FROM match_history WHERE winner = ?", (user_id,))
        wins = self.cursor.fetchone()[0]

        roles = [
            (100, "Grand Knight", 1348037384398442597),
            (90, "Knight Commander", 1348037287853953124),
            (80, "Knight", 1348037134132711424),
            (70, "Baron", 1348027387731775573),
            (60, "Lord", 1348027307574431795),
            (50, "Duke", 1348027196605992963),
            (40, "Count", 1348026929743138896),
            (30, "Squire", 1348026851418706010),
            (20, "Knight Apprentice", 1348026658925445332),
            (10, "Peasant", 1348026610540085269),
            (1, "Lucky Beginner", 1347689950329704590)
        ]

        self.cursor.execute("SELECT role_id FROM user_rewards WHERE user_id = ?", (user_id,))
        awarded_roles_ids = {row[0] for row in self.cursor.fetchall()}

        highest_role_to_award = None
        roles_to_remove = set()

        for i, (win_req, role_name, role_id) in enumerate(roles):
            if wins >= win_req:
                if role_id not in awarded_roles_ids:
                    highest_role_to_award = (role_name, role_id)
                    for j in range(i + 1, len(roles)):
                        lower_role_id = roles[j][2]
                        if lower_role_id in awarded_roles_ids:
                            roles_to_remove.add(lower_role_id)
                    break

        if highest_role_to_award:
            return highest_role_to_award[0], highest_role_to_award[1], list(roles_to_remove)

        return None, None, None

    def assign_reward(self, user_id, reward_name, role_id, expires_at=None):
        now = datetime.now().isoformat()
        self.cursor.execute("""
            INSERT INTO user_rewards (user_id, reward_name, role_id, awarded_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, reward_name, role_id, now, expires_at))
        self.conn.commit()
        return role_id

    def get_active_match(self, player_id):
        self.cursor.execute("SELECT id FROM matches WHERE player1 = ? OR player2 = ?", (player_id, player_id))
        result = self.cursor.fetchone()

        return result[0] if result else None

    def remove_expired_rewards(self):
        now = datetime.now().isoformat()
        self.cursor.execute("""
            SELECT user_id, role_id 
            FROM user_rewards 
            WHERE expires_at IS NOT NULL AND expires_at < ?
        """, (now,))
        expired_rewards = self.cursor.fetchall()

        self.cursor.execute("""
            DELETE FROM user_rewards 
            WHERE expires_at IS NOT NULL AND expires_at < ?
        """, (now,))
        self.conn.commit()

        return expired_rewards

    def get_current_matches(self):
        self.cursor.execute("""
            SELECT 
                p1.discord_id, 
                p2.discord_id, 
                g.name, 
                m.thread_id  
            FROM matches m
            JOIN players p1 ON m.player1 = p1.id
            JOIN players p2 ON m.player2 = p2.id
            JOIN gamemode g ON m.GameModeID = g.id
        """)
        return self.cursor.fetchall()

    def get_match_thread(self, player1, player2, GameModeID):
        self.cursor.execute("""
            SELECT thread_id FROM matches 
            WHERE player1 = ? AND player2 = ? AND GameModeID = ?
        """, (player1, player2, GameModeID))
        result = self.cursor.fetchone()
        return result[0] if result else None

    def get_winrate(self, discord_id, GameModeID):
        player_id = self.get_player_id(discord_id)
        self.cursor.execute(
            "SELECT wins, matches FROM player_ratings WHERE player_id = ? AND GameModeID = ?",
            (player_id, GameModeID),
        )
        result = self.cursor.fetchone()

        if result:
            wins, matches = result
            wins = wins if wins is not None else 0
            matches = matches if matches is not None else 0

            return round((wins / matches) * 100, 1) if matches > 0 else 0
        return 0

    def get_player_rank(self, discord_id, GameModeID):
        player_id = self.get_player_id(discord_id)
        self.cursor.execute(
            "SELECT elo FROM player_ratings WHERE player_id = ? AND GameModeID = ?",
            (player_id, GameModeID),
        )
        result = self.cursor.fetchone()
        if not result:
            return None, None

        player_elo = result[0]

        self.cursor.execute(
            "SELECT COUNT(*) FROM player_ratings WHERE GameModeID = ? AND elo > ?",
            (GameModeID, player_elo),
        )
        higher_rank_count = self.cursor.fetchone()[0]

        self.cursor.execute(
            "SELECT COUNT(*) FROM player_ratings WHERE GameModeID = ?",
            (GameModeID,),
        )
        total_players = self.cursor.fetchone()[0]

        player_rank = higher_rank_count + 1
        return player_rank, total_players

    def get_opponent_id(self, bettor_id: int, match_id: int):
        self.cursor.execute("SELECT player1, player2 FROM matches WHERE id = ?", (match_id,))
        match = self.cursor.fetchone()

        if match is None:
            return None
        player1_id, player2_id = match

        if bettor_id == player1_id:
            return player2_id
        elif bettor_id == player2_id:
            return player1_id
        else:
            return None

    def get_player_perks(self, player_id):
        now = datetime.now().isoformat()
        self.cursor.execute("DELETE FROM player_perks WHERE expires_at IS NOT NULL AND expires_at < ?", (now,))
        self.conn.commit()

        self.cursor.execute("SELECT perk_type, data FROM player_perks WHERE player_id = ?", (player_id,))
        return self.cursor.fetchall()

    def create_luckydice_match(self, match_id, player1_id, player2_id, player1_pool, player2_pool):
        self.cursor.execute("""
            INSERT INTO luckydice_selections (match_id, player1_id, player2_id, player1_faction_pool, player2_faction_pool)
            VALUES (?, ?, ?, ?, ?)
        """, (match_id, player1_id, player2_id, ",".join(player1_pool), ",".join(player2_pool)))
        self.conn.commit()

    def get_luckydice_selections(self, match_id):
        self.cursor.execute("SELECT * FROM luckydice_selections WHERE match_id = ?", (match_id,))
        return self.cursor.fetchone()

    def update_luckydice_selection(self, match_id, player_id, selected_factions):
        selections = self.get_luckydice_selections(match_id)
        if selections:
            if selections[1] == player_id:
                self.cursor.execute("UPDATE luckydice_selections SET player1_selected_factions = ?, player1_ready = TRUE WHERE match_id = ?", (",".join(selected_factions), match_id))
            else:
                self.cursor.execute("UPDATE luckydice_selections SET player2_selected_factions = ?, player2_ready = TRUE WHERE match_id = ?", (",".join(selected_factions), match_id))
            self.conn.commit()

    def get_token_leaderboard(self, limit=15):
        self.cursor.execute("""
            SELECT p.discord_id, p.tokens
            FROM players p
            ORDER BY p.tokens DESC
            LIMIT ?
        """, (limit,))
        return self.cursor.fetchall()

    def get_all_queued_players(self):
        self.cursor.execute("""
            SELECT q.discord_id, q.GameModeID, q.timestamp_queued, g.name 
            FROM queue q
            JOIN gamemode g ON q.GameModeID = g.id
            WHERE q.is_matched = FALSE AND q.is_unqueued = FALSE
        """)
        return self.cursor.fetchall()

    def get_match_maps(self, match_id):
        self.cursor.execute("SELECT maps FROM matches WHERE id = ?", (match_id,))
        result = self.cursor.fetchone()
        return result[0].split(',') if result and result[0] else []

    def update_player_wins(self, player_id, GameModeID, number_of_wins):
        db_player_id = self.get_player_id(player_id)
        if db_player_id:
            self.cursor.execute("""
                UPDATE player_ratings 
                SET wins = wins + ?
                WHERE player_id = ? AND GameModeID = ?
            """, (number_of_wins, db_player_id, GameModeID))
            self.conn.commit()

    def record_luckydice_match(self, winner_id, loser_id, GameModeID, elo_before_winner, elo_after_winner,
                            elo_before_loser, elo_after_loser):
        now = datetime.now().isoformat()

        winner_player_id = self.get_player_id(winner_id)
        loser_player_id = self.get_player_id(loser_id)

        self.cursor.execute("""
            INSERT INTO match_history (player1, player2, winner, GameModeID, 
                                       elo_before_winner, elo_after_winner, 
                                       elo_before_loser, elo_after_loser, datetime)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (winner_player_id, loser_player_id, winner_player_id, GameModeID, elo_before_winner, elo_after_winner,
              elo_before_loser, elo_after_loser, now))

        self.cursor.execute("""
            UPDATE player_ratings 
            SET elo = ?, matches = matches + 1, wins = wins + 1
            WHERE player_id = ? AND GameModeID = ?
        """, (elo_after_winner, winner_player_id, GameModeID))

        self.cursor.execute("""
            UPDATE player_ratings 
            SET elo = ?, matches = matches + 1
            WHERE player_id = ? AND GameModeID = ?
        """, (elo_after_loser, loser_player_id, GameModeID))

        self.conn.commit()