"""Fixed-fit NFL Injury ablation and season-forward ATS calibration."""

from argparse import ArgumentParser
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from injury_model import (
    SNAPSHOT_DIR, _feature_names, _kickoff_utc, _snapshot_capture_time,
    _snapshot_is_structurally_valid, add_injury_features, load_injury_reports,
)
from model import (
    PBP_COLUMNS, build_efficiency_model_dataset, load_pbp, load_schedule_data,
    normalize_schedule, project_upcoming_efficiency,
)
from qb_epa_model import attach_qb_margin_adjustment, build_qb_epa_board, qb_game_stats
from research.validate_qb_starter_confirmations import validate_starter_confirmations


SEASONS = tuple(range(2021, 2027))
ROOT = Path(__file__).resolve().parents[1]
FULL = "nonqb_on_qb_on"
ARMS = ("nonqb_off_qb_off", "nonqb_on_qb_off", "nonqb_off_qb_on", FULL)
CALIBRATIONS = ("market_only_fit", "market_and_model_fit", "market_favorite_bias_fit")
WEEK_LIMIT = 10


def historical_injury_inputs(base, schedule, reports):
    dataset = add_injury_features(base, schedule, reports, exclude_qb=True)
    dataset = dataset.set_index("game_id")
    dataset["injury_input_source"] = "timestamped_feed_or_unknown"
    snapshots = {}
    for path in sorted(SNAPSHOT_DIR.glob("injuries_2026_week_*.csv")):
        _, year, _, week, _ = path.stem.split("_")
        snapshot = pd.read_csv(path, low_memory=False)
        captured = _snapshot_capture_time(path)
        if pd.notna(captured) and _snapshot_is_structurally_valid(snapshot):
            snapshots.setdefault((int(year), int(week)), []).append((captured, snapshot))
    targets = schedule.loc[schedule.game_id.isin(dataset.index) & schedule.season.eq(2026)].copy()
    for idx, game in targets.iterrows():
        cutoff = _kickoff_utc(game)
        candidates = snapshots.get((game.season, game.week), ())
        # The live selector checks the newest file only. In a replay that
        # file can be post-kickoff even if an earlier capture was available.
        for captured, snapshot in reversed(candidates):
            if captured < cutoff:
                one = base.loc[base.game_id.eq(game.game_id)]
                replay = add_injury_features(
                    one, targets.loc[[idx]], snapshot.assign(date_modified=captured), exclude_qb=True
                ).set_index("game_id")
                dataset.loc[replay.index, replay.columns] = replay
                dataset.loc[game.game_id, "injury_input_source"] = captured.isoformat()
                break
    return dataset.reset_index()


def ridge_arms(dataset, min_train_games=500):
    """Score the observed and zero-count versions in the very same Ridge fit."""
    dataset = dataset.dropna(subset=["gameday", "home_score", "away_score"]).copy()
    dataset = dataset.sort_values(["gameday", "game_id"])
    counts = [f"{side}_{name}" for side in ("home", "away") for name in _feature_names()]
    if not set(counts).issubset(dataset.columns):
        raise ValueError("Non-QB injury features are missing")
    forecasts = []
    for _, target in dataset.groupby(dataset["gameday"].dt.to_period("W"), sort=True):
        train = dataset.loc[dataset.gameday.lt(target.gameday.min())]
        if len(train) < min_train_games:
            continue
        on = target.assign(home_score=np.nan, away_score=np.nan)
        off = on.copy()
        # Zero means no reported counts. Preserve unknown counts and report
        # availability so this toggle measures counts independently of coverage.
        off[counts] = off[counts].where(off[counts].isna(), 0.0)
        batch = pd.concat([train, on, off], ignore_index=True)
        scored = project_upcoming_efficiency(batch, min_train_games=min_train_games)
        on_scores, off_scores = scored.iloc[:len(on)], scored.iloc[len(on):]
        for arm in (on_scores, off_scores):
            if not np.array_equal(arm.game_id, target.game_id):
                raise AssertionError("Prediction arms differ in game membership or order")
        fold = target[["game_id", "gameday", "season", "week", "home_team", "away_team"]].copy()
        fold["actual_margin"] = target.home_score - target.away_score
        fold["home_report"] = target.home_injury_report_available
        fold["away_report"] = target.away_injury_report_available
        if "injury_input_source" in target:
            fold["injury_input_source"] = target.injury_input_source
        fold["training_games"] = len(train)
        fold["train_through"] = train.gameday.max()
        for name, scores in zip(ARMS[:2], (off_scores, on_scores)):
            fold[name] = (scores.projected_home - scores.projected_away).to_numpy()
        forecasts.append(fold)
    result = pd.concat(forecasts, ignore_index=True)
    if result.game_id.duplicated().any():
        raise ValueError("Duplicate scored game")
    return result


def calibration_inputs(games, variant):
    market = games.spread_line.to_numpy()
    if variant == "market_only_fit":
        return market[:, None]
    edge = games[FULL].to_numpy() - market
    if variant == "market_and_model_fit":
        return np.column_stack([market, edge])
    # Let the model disagreement have a different slope when the home
    # team is the favorite. Sign(market) allows a distinct favorite offset.
    return np.column_stack([market, edge, np.sign(market), edge * np.sign(market)])


def calibrate_forward(games):
    games = games.copy()
    coefficients = []
    for season in (2024, 2025, 2026):
        train = games.loc[games.season.lt(season)]
        test = games.loc[games.season.eq(season)]
        if train.empty or test.empty:
            raise ValueError(f"Missing calibration data for {season}")
        for variant in CALIBRATIONS:
            fit = LinearRegression().fit(
                calibration_inputs(train, variant), train.actual_margin - train.spread_line
            )
            games.loc[test.index, variant] = test.spread_line + fit.predict(
                calibration_inputs(test, variant)
            )
            coefficients.append(dict(
                season=season, variant=variant, training_games=len(train),
                intercept=fit.intercept_, coefficients=fit.coef_.tolist(),
            ))
    return games, pd.DataFrame(coefficients)


def evaluate(games, arms, reference):
    rows = []
    for arm in arms:
        if games.empty:
            break
        pick = np.sign((games[arm] - games.spread_line).round(10))
        ref_pick = np.sign((games[reference] - games.spread_line).round(10))
        actual = np.sign(games.actual_margin - games.spread_line)
        result = pick * actual
        wins, losses = int(result.eq(1).sum()), int(result.eq(-1).sum())
        actions = int(pick.ne(0).sum())
        pushes = actions - wins - losses
        dog = (pick * np.sign(games.spread_line)).lt(0)
        favorite = (pick * np.sign(games.spread_line)).gt(0)
        errors = games[arm] - games.actual_margin
        delta = errors.abs() - (games[reference] - games.actual_margin).abs()
        # Resample whole calendar-week blocks within each reported cohort.
        blocks = delta.groupby(games.gameday.dt.to_period("W")).agg(["sum", "size"])
        lower = upper = np.nan
        if len(blocks) >= 8:
            draw = np.random.default_rng(811).integers(0, len(blocks), (4000, len(blocks)))
            samples = blocks["sum"].to_numpy()[draw].sum(axis=1) / blocks["size"].to_numpy()[draw].sum(axis=1)
            lower, upper = np.quantile(samples, [0.025, 0.975])
        rows.append(dict(
            arm=arm, games=len(games), wins=wins, losses=losses, pushes=pushes,
            no_pick=len(games) - actions, roi_pct=100 * (wins / 1.1 - losses) / actions if actions else np.nan,
            dog_picks=int(dog.sum()), favorite_picks=int(favorite.sum()),
            dog_wins=int(result.loc[dog].eq(1).sum()), dog_losses=int(result.loc[dog].eq(-1).sum()),
            favorite_wins=int(result.loc[favorite].eq(1).sum()),
            favorite_losses=int(result.loc[favorite].eq(-1).sum()),
            changed_picks=int(pick.ne(ref_pick).sum()), margin_mae=errors.abs().mean(),
            home_margin_bias=errors.mean(), mean_abs_margin=games[arm].abs().mean(),
            mean_favorite_edge=((games[arm] - games.spread_line) * np.sign(games.spread_line)).mean(),
            delta_mae_vs_reference=delta.mean(), delta_mae_ci_low=lower, delta_mae_ci_high=upper,
        ))
    return pd.DataFrame(rows)


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, help="Directory with schedule.csv, pbp_YEAR.csv.gz and injury_YEAR.csv")
    args = parser.parse_args()
    print("Loading public schedule, play-by-play and injury reports", flush=True)
    if args.inputs:
        source = args.inputs
        schedule = normalize_schedule(pd.read_csv(source / "schedule.csv"))
        pbp = pd.concat([
            pd.read_csv(source / f"pbp_{year}.csv.gz", usecols=lambda c: c in PBP_COLUMNS, low_memory=False)
            for year in SEASONS
        ], ignore_index=True)
        reports = pd.concat([
            pd.read_csv(source / f"injury_{year}.csv", low_memory=False) for year in SEASONS
        ], ignore_index=True)
        hashes = []
        for name in ["schedule.csv", *(f"pbp_{year}.csv.gz" for year in SEASONS),
                     *(f"injury_{year}.csv" for year in SEASONS)]:
            with (source / name).open("rb") as handle:
                hashes.append(f"{hashlib.file_digest(handle, 'sha256').hexdigest()}  {name}")
    else:
        schedule, pbp, reports = load_schedule_data(), load_pbp(SEASONS), load_injury_reports(SEASONS)
    schedule = schedule.loc[
        schedule.season.isin(SEASONS) & (schedule.season.lt(2026) | schedule.week.le(WEEK_LIMIT))
    ].dropna(subset=["home_score", "away_score"]).copy()
    missing_pbp = set(schedule.game_id) - set(pbp.game_id)
    if missing_pbp:
        raise ValueError(f"Completed scheduled games missing play-by-play: {sorted(missing_pbp)}")

    print("Building historical Ridge inputs and scoring paired non-QB variants", flush=True)
    base = build_efficiency_model_dataset(schedule, pbp)
    dataset = historical_injury_inputs(base, schedule, reports)
    scored = ridge_arms(dataset)

    print("Applying the capped QB overlay using prior games and vetted attestations", flush=True)
    attestations = pd.read_csv(ROOT / "data/qb_starters/2026_week10_confirmed.csv")
    verified, _ = validate_starter_confirmations(
        schedule, attestations, checked_as_of_utc="2026-11-17T23:59:59Z"
    )
    expected = pd.read_csv(ROOT / "data/qb_starters/2026_week10_expected.csv")
    # A date-only coach statement must be from a prior calendar day.
    dated = expected.merge(schedule[["game_id", "gameday"]], validate="many_to_one")
    expected = dated.loc[pd.to_datetime(dated.source_report_date).lt(dated.gameday)]
    board = build_qb_epa_board(
        qb_game_stats(pbp, schedule), schedule, scored, overrides=verified, expected=expected
    )
    # Use the production overlay function so cap and sign match the live formula.
    overlay = attach_qb_margin_adjustment(scored[["game_id"]].assign(
        projected_home=0.0, projected_away=0.0
    ), board)
    scored = scored.merge(overlay[["game_id", "qb_margin_adjustment"]], validate="one_to_one")
    for without, with_qb in zip(ARMS[:2], ARMS[2:]):
        scored[with_qb] = scored[without] + scored.qb_margin_adjustment
    scored = scored.merge(schedule[["game_id", "spread_line"]], validate="one_to_one")
    for side in ("home", "away"):
        detail = board.loc[board.side.eq(side)].set_index("game_id")
        for column in ("starter_source", "confidence"):
            scored[f"{side}_{column}"] = scored.game_id.map(detail[column])
    common = scored.dropna(subset=[*ARMS, "spread_line"]).copy()
    common, coefficients = calibrate_forward(common)
    groups = [("all_2024_2026", common.loc[common.season.ge(2024)]),
              *((str(y), group) for y, group in common.loc[common.season.ge(2024)].groupby("season"))]
    summary = [
        evaluate(group, (*ARMS, "spread_line", *CALIBRATIONS), FULL).assign(cohort=name)
        for name, group in groups
    ]
    has_confirmed = common[["home_starter_source", "away_starter_source"]].eq("verified_pregame").any(axis=1)
    low_history = common[["home_confidence", "away_confidence"]].eq("insufficient_data").any(axis=1)
    for name, mask in {
        "any_confirmed_qb": has_confirmed,
        "both_qbs_unconfirmed": ~has_confirmed,
        "any_qb_under_40_weighted_dropbacks": low_history,
        "both_qbs_40_plus_weighted_dropbacks": ~low_history,
        "both_injury_reports": common.home_report.eq(1) & common.away_report.eq(1),
        "abs_qb_shift_ge_1": common.qb_margin_adjustment.abs().ge(1),
    }.items():
        group = common.loc[mask & common.season.ge(2024)]
        if not group.empty:
            summary.append(evaluate(group, ARMS, FULL).assign(cohort=name))
    for low, high in ((0, 3), (3, 7), (7, np.inf)):
        spread_group = common.loc[common.season.ge(2024) & common.spread_line.abs().ge(low)
                                  & common.spread_line.abs().lt(high)]
        summary.append(evaluate(spread_group, (*ARMS, "spread_line", *CALIBRATIONS), FULL).assign(
            cohort=f"abs_market_spread_{low}_to_{high}"
        ))
    # Additional paired main effects isolate each toggle with the other off.
    for name, group in groups:
        summary.append(evaluate(group, (ARMS[1], ARMS[2]), ARMS[0]).assign(
            cohort=f"{name}_vs_both_off"
        ))
    args.output.mkdir(parents=True, exist_ok=True)
    scored.merge(
        common[["game_id", *CALIBRATIONS]], on="game_id", how="left", validate="one_to_one"
    ).to_csv(args.output / "games.csv", index=False, float_format="%.10g")
    board.to_csv(args.output / "qb_evidence.csv", index=False, float_format="%.10g")
    coefficients.to_csv(args.output / "calibration_coefficients.csv", index=False)
    pd.concat(summary, ignore_index=True).to_csv(
        args.output / "metrics.csv", index=False, float_format="%.10g"
    )
    if args.inputs:
        (args.output / "inputs.sha256").write_text("\n".join(hashes) + "\n")
    print(f"Completed {len(common)} comparable of {len(scored)} scored games.", flush=True)


if __name__ == "__main__":
    main()
