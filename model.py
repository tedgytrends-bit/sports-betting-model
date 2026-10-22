"""Starter math for transparent score and market comparisons.

These helpers do not themselves create reliable predictions. A trained model and
point-in-time data pipeline must supply the projected scores.
"""
from dataclasses import dataclass

@dataclass
class GameProjection:
    away_team: str
    home_team: str
    away_points: float
    home_points: float
    market_home_spread: float | None = None  # e.g. -3.5 means home team favored by 3.5
    market_total: float | None = None

    @property
    def projected_home_margin(self) -> float:
        return self.home_points - self.away_points

    @property
    def projected_total(self) -> float:
        return self.home_points + self.away_points

    @property
    def model_home_spread(self) -> float:
        # Convention: a negative spread means the home team is favored.
        return -self.projected_home_margin

    @property
    def spread_difference(self) -> float | None:
        if self.market_home_spread is None:
            return None
        # Positive means the model is more favorable to the away side than market.
        return self.market_home_spread - self.model_home_spread

    @property
    def total_difference(self) -> float | None:
        if self.market_total is None:
            return None
        return self.projected_total - self.market_total


def ats_result(team_points: float, opponent_points: float, team_spread: float) -> str:
    """Grade one team's spread result; team_spread is the team's listed handicap."""
    adjusted = team_points + team_spread
    if adjusted > opponent_points:
        return "W"
    if adjusted < opponent_points:
        return "L"
    return "P"
