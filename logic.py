from database import Database


class LadderSystem:
    def __init__(self, db: Database):
        self.db = db

    def get_leaderboard(self, mode):
        return self.db.get_leaderboard(mode)

    def get_match_history(self, player_id, limit):
        return self.db.get_match_history(player_id, limit)


def expected_score(rating_a, rating_b):
    return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))


def update_elo(rating_winner, rating_loser, K=32):
    expected_winner = expected_score(rating_winner, rating_loser)
    expected_loser = expected_score(rating_loser, rating_winner)

    new_rating_winner = rating_winner + K * (1 - expected_winner)
    new_rating_loser = rating_loser + K * (0 - expected_loser)

    return int(new_rating_winner), int(new_rating_loser)


