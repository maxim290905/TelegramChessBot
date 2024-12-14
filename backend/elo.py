# backend/elo.py

def calculate_elo(winner_elo, loser_elo, k=32, draw=False):
    expected_score_winner = 1 / (1 + 10 ** ((loser_elo - winner_elo) / 400))
    expected_score_loser = 1 / (1 + 10 ** ((winner_elo - loser_elo) / 400))

    if draw:
        winner_new_elo = winner_elo + k * (0.5 - expected_score_winner)
        loser_new_elo = loser_elo + k * (0.5 - expected_score_loser)
    else:
        winner_new_elo = winner_elo + k * (1 - expected_score_winner)
        loser_new_elo = loser_elo + k * (0 - expected_score_loser)

    return round(winner_new_elo, 1), round(loser_new_elo, 1)