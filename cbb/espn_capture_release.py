"""Validate the five-model board and stage a single atomic branch update."""
import json
from datetime import datetime, timezone
from pathlib import Path

from cbb.prospective import utc_date
from cbb.prospective_publish import publish
from cbb.espn_daily_board import MODELS


class CheckoutStore:
    branch = "cbb-prospective"

    def put_text(self, path, content, immutable=False):
        file = Path("archive") / path
        if immutable and file.exists():
            return "existing"
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content, encoding="utf-8")
        return "created"

    def put_json(self, path, content, immutable=False):
        return self.put_text(path, json.dumps(content, indent=2, allow_nan=False)+"\n", immutable)


def validate_capture(board, now):
    games = board["games"]
    if not games or not board["source"].startswith("ESPN") or not board["source_sha256"]:
        raise ValueError("Empty board or missing ESPN input provenance")
    if any(utc_date(g["tip_utc"])<=now for g in games):
        raise ValueError("Game started before publication")
    if len({g["id"] for g in games}) != len(games):
        raise ValueError("Duplicate event ID")
    for g in games:
        for model in MODELS:
            m = g[model]
            if m["training_games"] < 1000 or not all(0 < m[k] < 240 for k in
                    ("projected_away_points","projected_home_points","projected_total")):
                raise ValueError(f"Invalid {model} prediction for {g['id']}")
    lined = [g for g in games if g["freeze_candidate"]]
    if lined:
        teams = [g["coverage"][side+"_prior_matched"] for g in lined for side in ("home","away")]
        if sum(v>0 for v in teams) < len(teams)*0.7:
            raise ValueError("Player-prior identity coverage too low for publication")
        covered = [g["rotation_coverage"][side]["past_game_boxes"] for g in lined for side in ("home","away")]
        if sum(v>0 for v in covered)<len(covered)*0.7:
            raise ValueError("Rotation identity coverage too low for publication")


def main():
    board = json.loads(Path("cbb/outputs/prospective/latest_capture.json").read_text())
    now = datetime.now(timezone.utc)
    validate_capture(board,now)
    latest = Path("archive/cbb/prospective/2027/latest.json")
    if latest.exists() and utc_date(json.loads(latest.read_text())["capture_utc"])>=utc_date(board["capture_utc"]):
        raise ValueError("A newer board already exists")
    import os
    publish(board, CheckoutStore(), os.environ["GITHUB_RUN_ID"])


if __name__=="__main__":
    main()
