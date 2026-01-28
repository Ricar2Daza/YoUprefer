from typing import Tuple

class RankingService:
    K_FACTOR = 32

    @staticmethod
    def calculate_elo(winner_rating: int, loser_rating: int) -> Tuple[int, int]:
        """
        Calculates the new ELO ratings for both winner and loser.
        """
        # Expected scores
        expected_winner = 1 / (1 + 10 ** ((loser_rating - winner_rating) / 400))
        expected_loser = 1 / (1 + 10 ** ((winner_rating - loser_rating) / 400))

        # New ratings
        new_winner_rating = round(winner_rating + RankingService.K_FACTOR * (1 - expected_winner))
        new_loser_rating = round(loser_rating + RankingService.K_FACTOR * (0 - expected_loser))

        return new_winner_rating, new_loser_rating

ranking_service = RankingService()
