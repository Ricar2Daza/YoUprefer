from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EloResult:
    winner_rating: int
    loser_rating: int


def calculate_elo(*, winner_rating: int, loser_rating: int, k_factor: int = 32) -> EloResult:
    expected_winner = 1 / (1 + 10 ** ((loser_rating - winner_rating) / 400))
    expected_loser = 1 / (1 + 10 ** ((winner_rating - loser_rating) / 400))

    new_winner_rating = round(winner_rating + k_factor * (1 - expected_winner))
    new_loser_rating = round(loser_rating + k_factor * (0 - expected_loser))
    return EloResult(winner_rating=new_winner_rating, loser_rating=new_loser_rating)
