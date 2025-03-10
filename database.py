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
                discord_id INTEGER UNIQUE, 
                GameModeID INTEGER,
                is_matched BOOLEAN DEFAULT FALSE,
                is_unqueued BOOLEAN DEFAULT FALSE,
                timestamp_queued TEXT,
                timestamp_matched TEXT,
                timestamp_unqueued TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (GameModeID) REFERENCES gamemode(id)
            );

            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                player1 INTEGER, 
                player2 INTEGER, 
                GameModeID INTEGER, 
                thread_id INTEGER,  
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
            INSERT OR IGNORE INTO gamemode (id, name) VALUES (4, 'luckytest');
            
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
            
            INSERT INTO user_rewards (user_id, reward_name, role_id, awarded_at, expires_at)
            VALUES
                (1, 'Champion', 123456789, datetime('now'), NULL),
                (2, 'Elite Gambler', 987654321, datetime('now'), datetime('now', '+30 days')),
                (3, 'High Roller', 567891234, datetime('now'), datetime('now', '+60 days'));
        """)
        self.conn.commit()

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
            INSERT INTO queue (discord_id, GameModeID, timestamp_queued, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(discord_id) DO UPDATE SET
                GameModeID = excluded.GameModeID,
                is_matched = FALSE,
                is_unqueued = FALSE,
                timestamp_queued = excluded.timestamp_queued,
                timestamp_matched = NULL,
                timestamp_unqueued = NULL,
                updated_at = excluded.updated_at
        """, (discord_id, GameModeID, now, now, now))
        self.conn.commit()

        self.cursor.execute("SELECT discord_id FROM players WHERE discord_id = ?", (discord_id,))
        user = self.cursor.fetchone()
        if user:
            user_name = user[0]
            self.log_event("add_to_queue", discord_id, user_name)

    def mark_as_matched(self, discord_id):
        now = datetime.now().isoformat()
        self.cursor.execute("""
            UPDATE queue 
            SET is_matched = TRUE, timestamp_matched = ?, updated_at = ?
            WHERE discord_id = ?
        """, (now, now, discord_id))
        self.conn.commit()

        self.cursor.execute("SELECT discord_id FROM players WHERE discord_id = ?", (discord_id,))
        user = self.cursor.fetchone()
        if user:
            user_name = user[0]
            self.log_event("mark_as_matched", discord_id, user_name)

    def mark_as_unqueued(self, discord_id):
        now = datetime.now().isoformat()
        self.cursor.execute("""
            UPDATE queue 
            SET is_unqueued = TRUE, timestamp_unqueued = ?
            WHERE discord_id = ?
        """, (now, discord_id))
        self.conn.commit()

        self.cursor.execute("SELECT discord_id FROM players WHERE discord_id = ?", (discord_id,))
        user = self.cursor.fetchone()
        if user:
            user_name = user[0]
            self.log_event("mark_as_unqueued", discord_id, user_name)

    def create_match(self, player1, player2, GameModeID, thread_id):
        now = datetime.now().isoformat()
        self.cursor.execute("""
            INSERT INTO matches (player1, player2, GameModeID, thread_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (player1, player2, GameModeID, thread_id, now, now))
        self.conn.commit()

        self.cursor.execute("SELECT discord_id FROM players WHERE discord_id = ?", (player1,))
        user = self.cursor.fetchone()
        if user:
            user_name = user[0]
            self.log_event("create_match", player1, user_name)

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
                            elo_before_loser, elo_after_loser):
        now = datetime.now().isoformat()

        self.cursor.execute("SELECT id FROM players WHERE discord_id = ?", (winner_id,))
        winner_player_id = self.cursor.fetchone()[0]

        self.cursor.execute("SELECT id FROM players WHERE discord_id = ?", (loser_id,))
        loser_player_id = self.cursor.fetchone()[0]

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
        result = self.cursor.fetchone()
        return result[0] if result else None

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
            WHERE pr.GameModeID = ?
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

    def is_lobby_occupied(self, lobby):
        pass

    def get_available_lobby(self):
        pass

    def get_match_lobby(self, player1, player2, GameModeID):
        pass

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
        self.cursor.execute("SELECT COUNT(*) FROM match_history WHERE winner = ?", (user_id,))
        wins = self.cursor.fetchone()[0]

        if wins >= 100:
            return "Grand Knight", 1348037384398442597
        elif wins >= 90:
            return "Knight Commander", 1348037287853953124
        elif wins >= 80:
            return "Knight", 1348037134132711424
        elif wins >= 70:
            return "Baron", 1348027387731775573
        elif wins >= 60:
            return "Lord", 1348027307574431795
        elif wins >= 50:
            return "Duke", 1348027196605992963
        elif wins >= 40:
            return "Count", 1348026929743138896
        elif wins >= 30:
            return "Squire", 1348026851418706010
        elif wins >= 20:
            return "Knight Apprentice", 1348026658925445332
        elif wins >= 10:
            return "Peasant", 1348026610540085269
        elif wins >= 1:
            return "Lucky Beginner", 1347689950329704590

        return None, None

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
            SELECT p1.discord_id, p2.discord_id, g.name, m.lobby 
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
