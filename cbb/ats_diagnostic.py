"""Read-only, point-in-time ATS audit of a pinned prospective data checkout."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from itertools import combinations
import json
from math import sqrt
from pathlib import Path
import random
from statistics import mean
import subprocess
from zoneinfo import ZoneInfo


MODELS = ("player_opp_v3", "player_rot_v4", "player_all_v4")
CENTRAL = ZoneInfo("America/Chicago")
SPREAD = ("0–5", ">5–10", ">10–20", ">20")
EDGE = ("0–2.5", ">2.5–5", ">5–8", ">8")
MOVE = ("0–0.5", ">0.5–1", ">1–2", ">2")


def utc_date(value):
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError(f"Timestamp must include a UTC offset: {value}")
    return stamp


def read(path):
    return json.loads(path.read_text())


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def bins(value, bounds, labels):
    return next((label for bound, label in zip(bounds, labels) if value <= bound), labels[-1])


def first_grades(repo, root):
    availability = {}
    folder = (root / "graded").relative_to(repo)
    for line in git(repo, "log", "--first-parent", "--reverse", "--format=%H %cI", "--", str(folder)).splitlines():
        sha, stamp = line.split()
        for path in git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", sha, "--", str(folder)).splitlines():
            for ident, grade in json.loads(git(repo, "show", f"{sha}:{path}"))["results"].items():
                availability.setdefault(ident, (utc_date(stamp), grade))
    return availability


def availability_group(game):
    coverage = game.get("rotation_coverage") or {}
    sides = [coverage.get(side) or {} for side in ("home", "away")]
    if any(side.get("prior_key_minutes_missing") is None for side in sides):
        return "unknown"
    if any(not side.get("last_box_present") for side in sides):
        return "missing recent box"
    if any(side["prior_key_minutes_missing"] > 0 for side in sides):
        return "prior key minutes missing"
    return "recent boxes and prior key minutes available"


def load_games(repo, root):
    earliest = first_grades(repo, root)
    games, counts, seen = [], Counter(), set()
    snapshots = defaultdict(list)
    for path in sorted((root / "snapshots").glob("*.json")):
        snap = read(path)
        capture = utc_date(snap["capture_utc"])
        for game in snap["games"]:
            line = game.get("market") or {}
            if line.get("home_spread") is None or not line.get("as_of_utc"):
                continue
            observed = utc_date(line["as_of_utc"])
            tip = utc_date(game["tip_utc"])
            identity = tuple(str(game[key]) for key in ("home_team_id", "away_team_id"))
            if observed <= capture and capture + timedelta(minutes=1) < tip:
                snapshots[str(game["id"])].append(
                    (capture, observed, line["provider"], line["home_spread"], identity)
                )

    for path in sorted((root / "graded").glob("*.json")):
        journal = read(path)
        counts["untracked"] += len(journal["untracked"])
        counts["invalid"] += len(journal["invalid"])
        for ident, grade in journal["results"].items():
            if ident in seen:
                raise ValueError(f"Duplicate grade for {ident}")
            seen.add(ident)
            counts["tracked"] += 1
            freeze = read(root / "frozen" / f"{ident}.json")
            game = freeze["game"]
            capture = utc_date(freeze["capture_utc"])
            tip = min(utc_date(grade["tip_utc"]), utc_date(game["tip_utc"]))
            if (str(game["id"]) != ident or str(grade["id"]) != ident
                    or any(grade[side] != game[side] for side in ("home", "away"))
                    or utc_date(grade["captured_utc"]) != capture
                    or capture + timedelta(minutes=1) >= tip):
                raise ValueError(f"Invalid freeze/grade match for {ident}")
            for model in MODELS:
                counts[f"missing_{model}"] += model not in game
            market = game.get("market") or {}
            spread = market.get("home_spread")
            counts["missing_spread"] += spread is None
            if any(model not in game for model in MODELS) or spread is None:
                continue
            observed = utc_date(market["as_of_utc"])
            if observed > capture or grade["home_spread"] != spread or grade["market_provider"] != market["provider"]:
                raise ValueError(f"Invalid market observation for {ident}")
            margin = grade["home_points"] - grade["away_points"]
            preds = {model: game[model]["projected_margin_home"] for model in MODELS}
            edges = {model: game[model]["ats_edge"] for model in MODELS}
            picks = {model: game[model]["ats_lean"] for model in MODELS}
            for model in MODELS:
                if (edges[model] is None or abs(edges[model] - (preds[model] + spread)) > 0.0011
                        or (edges[model] and picks[model] != ("home" if edges[model] > 0 else "away"))):
                    raise ValueError(f"Invalid frozen ATS fields for {ident}/{model}")
            available, first_grade = earliest[ident]
            if first_grade != grade or available <= tip:
                raise ValueError(f"Unverified first final score for {ident}")
            identity = tuple(str(game[key]) for key in ("home_team_id", "away_team_id"))
            later = [entry for entry in snapshots[ident]
                     if capture < entry[0] < tip - timedelta(minutes=1)
                     and observed < entry[1] and entry[2] == market["provider"] and entry[4] == identity]
            day = utc_date(grade["tip_utc"]).astimezone(CENTRAL).date().isoformat()
            games.append(dict(id=ident, day=day, capture=capture, observed=observed,
                              tip=tip, available=available, spread=spread, actual=margin,
                              preds=preds, edges=edges, picks=picks, neutral=game.get("neutral_site"),
                              coverage=availability_group(game), provider=market["provider"],
                              model_commit=freeze["model_commit"], later=max(later, default=None)))
    if not games:
        raise ValueError("No common eligible games")
    return games, dict(counts)


def score(game, pick, spread=None):
    if pick not in ("home", "away"):
        return None
    delta = game["actual"] + (game["spread"] if spread is None else spread)
    selected = delta if pick == "home" else -delta
    return "W" if selected > 0 else "L" if selected < 0 else "P"


def pick(game, model):
    return game["picks"][model] if game["edges"][model] else None


def units(outcome):
    return {"W": 100 / 110, "L": -1, "P": 0, None: 0}[outcome]


def wilson(wins, decided):
    if not decided:
        return None
    p = wins / decided
    scale = 1 + 1.96**2 / decided
    center = (p + 1.96**2 / (2 * decided)) / scale
    half_width = 1.96 * sqrt(p * (1 - p) / decided + 1.96**2 / (4 * decided**2)) / scale
    return [100 * (center - half_width), 100 * (center + half_width)]


def metrics(rows):
    # One row per eligible game, with a null outcome for a tied projection.
    results = Counter(outcome for _, outcome, _ in rows)
    w, l, p = (results[key] for key in "WLP")
    n = w + l + p
    errors = [pred - game["actual"] for game, _, pred in rows]
    return dict(games=len(rows), selections=n, wins=w, losses=l, pushes=p,
                win_rate_pct=100 * w / (w + l) if w + l else None,
                win_rate_wilson_pct=wilson(w, w + l),
                roi_minus_110_pct=100 * (w * 100 / 110 - l) / n if n else None,
                margin_mae=mean(map(abs, errors)) if errors else None,
                signed_home_residual=mean(errors) if errors else None)


def frozen_rows(games, model):
    return [(g, score(g, pick(g, model)), g["preds"][model]) for g in games]


def slices(rows, group, labels=None):
    groups = defaultdict(list)
    for row in rows:
        groups[group(row[0])].append(row)
    return {label: metrics(groups[label]) for label in (labels or sorted(groups))}


def side(game, model):
    selection = pick(game, model)
    if not selection or not game["spread"]:
        return "pick'em or no selection"
    favorite = "home" if game["spread"] < 0 else "away"
    return "favorite" if selection == favorite else "underdog"


def paired_delta(candidate, reference, alpha=0.05):
    by_day = defaultdict(list)
    for (g, ats, pred), (other, old_ats, old_pred) in zip(candidate, reference, strict=True):
        if g["id"] != other["id"]:
            raise ValueError("Unmatched paired comparison")
        mae = abs(pred - g["actual"]) - abs(old_pred - g["actual"])
        by_day[g["day"]].append((mae, 100 * (units(ats) - units(old_ats))))
    days = [(len(rows), *(sum(col) for col in zip(*rows))) for rows in by_day.values()]
    if not days:
        return None
    n, mae, net = map(sum, zip(*days))
    rng = random.Random(54)
    simulations = []
    for _ in range(5000 if len(days) > 1 else 0):
        size, err, ret = map(sum, zip(*rng.choices(days, k=len(days))))
        simulations.append((err / size, ret / size))
    intervals = []
    for series in zip(*simulations):
        values = sorted(series)
        intervals.append([values[int(alpha / 2 * len(values))],
                          values[int((1 - alpha / 2) * len(values))]])
    return dict(games=n, day_blocks=len(days), margin_mae_delta=mae / n,
                return_per_eligible_game_delta_pct=net / n, interval_level=1 - alpha,
                mae_interval=intervals[0] if intervals else None,
                return_interval_pct=intervals[1] if intervals else None)


def compare(games, left, right):
    disagreements = [g for g in games if pick(g, left) and pick(g, right)
                     and pick(g, left) != pick(g, right)]
    coverage = sorted({g["coverage"] for g in games})
    adjust = lambda g: bins(abs(g["preds"][right] - g["preds"][left]), (0.5, 1, 2), MOVE)
    groups = {"by_coverage": {k: [g for g in games if g["coverage"] == k] for k in coverage},
              "by_projection_movement": {k: [g for g in games if adjust(g) == k] for k in MOVE}}
    return dict(opposite_picks=len(disagreements),
                only_one_picked=sum(bool(pick(g, left)) != bool(pick(g, right)) for g in games),
                on_opposite_picks={m: metrics(frozen_rows(disagreements, m)) for m in (left, right)},
                overall=paired_delta(frozen_rows(games, right), frozen_rows(games, left)),
                **{key: {label: paired_delta(frozen_rows(group, right), frozen_rows(group, left))
                         for label, group in subsets.items()} for key, subsets in groups.items()})


def walk_forward(games):
    # Fixed benchmark weights, no search. Train a home-margin intercept per model.
    # Set it before the earliest freeze in each Central-date test block.
    days = sorted({g["day"] for g in games})
    folds, frozen, corrected, market = [], defaultdict(list), defaultdict(list), []
    for day in days:
        test = [g for g in games if g["day"] == day]
        cutoff = min(g["capture"] for g in test)
        train = [g for g in games if g["day"] < day and g["available"] < cutoff]
        if len({g["day"] for g in train}) < 2 or len(train) < 75:
            continue
        biases = {}
        for model in MODELS:
            # Shrink the frozen edge 25% toward market. Fit the intercept to
            # earlier finalized rows only. Fixed shrinkage avoids a weight sweep.
            bias = mean(g["actual"] - (0.75 * g["preds"][model] - 0.25 * g["spread"]) for g in train)
            biases[model] = bias
            frozen[model].extend(frozen_rows(test, model))
            for g in test:
                pred = 0.75 * g["preds"][model] - 0.25 * g["spread"] + bias
                edge = pred + g["spread"]
                selection = "home" if edge > 0 else "away" if edge < 0 else None
                corrected[model].append((g, score(g, selection), pred))
        market.extend((g, None, -g["spread"]) for g in test)
        folds.append(dict(day=day, cutoff_utc=cutoff.isoformat(), train_games=len(train),
                          test_games=len(test), fitted_intercepts=biases))
    return dict(folds=folds, market=metrics(market),
                models={m: dict(frozen=metrics(frozen[m]), corrected=metrics(corrected[m]),
                                corrected_minus_frozen=paired_delta(corrected[m], frozen[m], 0.05 / 6),
                                corrected_minus_market_mae=paired_delta(corrected[m], market, 0.05 / 6))
                        for m in MODELS})


def report(repo, root):
    games, counts = load_games(repo, root)
    analyses = {}
    for m in MODELS:
        rows = frozen_rows(games, m)
        spread_bin = lambda g: bins(abs(g["spread"]), (5, 10, 20), SPREAD)
        edge = slices(rows, lambda g: bins(abs(g["edges"][m]), (2.5, 5, 8), EDGE), EDGE)
        rates = [bucket["win_rate_pct"] for bucket in edge.values() if bucket["win_rate_pct"] is not None]
        later = [g for g in games if g["later"] and pick(g, m)]
        advantages = [(g["spread"] - g["later"][3]) * (1 if pick(g, m) == "home" else -1) for g in later]
        analyses[m] = dict(overall=metrics(rows), edge=edge,
                           edge_win_rate_monotone=all(a <= b for a, b in zip(rates, rates[1:])),
                           edge_at_least_3_5=metrics([row for row in rows if abs(row[0]["edges"][m]) >= 3.5]),
                           spread=slices(rows, spread_bin, SPREAD),
                           spread_by_side={s: slices([row for row in rows if side(row[0], m) == s],
                                                     spread_bin, SPREAD)
                                           for s in ("favorite", "underdog", "pick'em or no selection")},
                           selection_location=slices(rows, lambda g: f"{'neutral' if g['neutral'] else 'non-neutral'} / {pick(g, m)}"),
                           later_pretip=dict(games=len(later), frozen=metrics(frozen_rows(later, m)),
                                             later=metrics([(g, score(g, pick(g, m), g["later"][3]), g["preds"][m]) for g in later]),
                                             mean_original_line_advantage=mean(advantages) if advantages else None))
    # Combined minus Opponent is the rotation contribution conditional on
    # opponent features. Rotation-only minus Opponent swaps feature families.
    pairs = {f"{right} minus {left}": compare(games, left, right)
             for left, right in combinations(MODELS, 2)}
    counts.update(matched=len(games), later_same_provider_pretip=sum(bool(g["later"]) for g in games),
                  confirmed_closing=0)
    sources = []
    for g in games:
        item = {key: g[key] for key in ("id", "day", "provider", "model_commit")}
        item.update({key: g[key].isoformat() for key in ("capture", "observed", "tip", "available")})
        if g["later"]:
            item["later_capture"], item["later_observed"] = (value.isoformat() for value in g["later"][:2])
            item["later_home_spread"] = g["later"][3]
        sources.append(item)
    return dict(source_commit=git(repo, "rev-parse", "HEAD"),
                journal_as_of_utc=read(root / "performance_report.json")["as_of_utc"],
                counts=counts, sources=sources, models=analyses, pairs=pairs,
                walk_forward=walk_forward(games))


def fmt(value):
    return "—" if value is None else f"{value:.2f}"


def table(items):
    lines = [
        "| Group | Games | W–L–P | Win % (95% CI) | ROI % | Margin MAE | Signed residual |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, row in items:
        record = "–".join(str(row[k]) for k in ("wins", "losses", "pushes"))
        interval = row["win_rate_wilson_pct"]
        win = fmt(row["win_rate_pct"])
        if interval:
            win += f" ({fmt(interval[0])} to {fmt(interval[1])})"
        values = [name, str(row["games"]), record, win, fmt(row["roi_minus_110_pct"]),
                  fmt(row["margin_mae"]), fmt(row["signed_home_residual"])]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def render(data):
    counts = data["counts"]
    sources = data["sources"]
    lines = [
        "# CBB ATS diagnostics",
        f"Data commit `{data['source_commit']}` · grade report {data['journal_as_of_utc']}",
        f"{counts['matched']} common games from {counts['tracked']} tracked finals. "
        f"{counts['untracked']} untracked, {counts['invalid']} invalid, "
        f"{counts['missing_spread']} tracked without spread.",
        "Missing frozen predictions by model: " + ", ".join(f"{m} {counts[f'missing_{m}']}" for m in MODELS) + ".",
        f"Matched freeze timestamps span {min(g['capture'] for g in sources)} to "
        f"{max(g['capture'] for g in sources)}. Per-game observation and grade-availability timestamps are in JSON.",
        "ROI assumes hypothetical flat stakes at −110 and includes pushes in the stake denominator. "
        "Win rate excludes pushes and tied projections. Signed residual is projected minus final home margin.",
        f"{counts['later_same_provider_pretip']} games have a verified later same-provider pretip quote. "
        "The archive provides no confirmed closing designation.",
    ]
    for model, info in data["models"].items():
        lines.extend([f"## {model}",
                      table([("All", info["overall"]), ("Edge ≥3.5", info["edge_at_least_3_5"])]),
                      f"Edge win rates are {'monotone' if info['edge_win_rate_monotone'] else 'nonmonotone'}.",
                      table(info["edge"].items()),
                      table(info["spread"].items()),
                      table((f"{side_name} / {bucket}", metrics)
                            for side_name, groups in info["spread_by_side"].items()
                            for bucket, metrics in groups.items()),
                      table(info["selection_location"].items()),
                      table((k, info["later_pretip"][k]) for k in ("frozen", "later"))])
    for name, pair in data["pairs"].items():
        lines.extend([f"## {name}", f"{pair['opposite_picks']} opposite picks and "
                      f"{pair['only_one_picked']} games where only one model picked.",
                      table(pair["on_opposite_picks"].items())])
        for group, delta in [("Overall", pair["overall"]), *pair["by_coverage"].items(),
                             *pair["by_projection_movement"].items()]:
            if delta:
                lines.append(f"- {group} ({delta['games']} games). MAE delta "
                             f"{fmt(delta['margin_mae_delta'])} points, return delta "
                             f"{fmt(delta['return_per_eligible_game_delta_pct'])} pp per eligible game.")
        lines.append("The Combined minus Opponent comparison adds rotation features conditional on opponent features. "
                     "Rotation-only minus Opponent swaps feature families.")
    walk = data["walk_forward"]
    lines.extend(["## Chronological evaluation",
                  "The fixed candidate shrinks model edges 25% toward the frozen spread and fits a home-margin "
                  "intercept using 75 or more earlier games from at least two dates. The first published grade "
                  "must precede the earliest freeze in the test date block. "
                  "The market spread is a margin benchmark with no directional pick.",
                  f"{len(walk['folds'])} held-out dates.",
                  table([("Market", walk["market"]), *((f"{m} / {k}", result[k])
                        for m, result in walk["models"].items() for k in ("frozen", "corrected"))]),
                  "The JSON includes paired Central-date block bootstrap intervals (5,000 replicates). "
                  "The six model-vs-frozen MAE and return comparisons use a Bonferroni adjustment. "
                  "Market comparisons and subgroup searches are descriptive. "
                  "The limited number of dates makes interval estimates unstable."])
    return "\n\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-repo", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    root = args.data_repo / "cbb/prospective/2027"
    data = report(args.data_repo, root)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "ats_diagnostic.json").write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    markdown = render(data)
    (args.output_dir / "ats_diagnostic.md").write_text(markdown)
    print(markdown)


if __name__ == "__main__":
    main()
