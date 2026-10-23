import json
import urllib.error
import urllib.request

import streamlit as st

BASE_URL = "https://mcp.endzoneapi.com/v1"
TIMEOUT_SECONDS = 20

st.set_page_config(
    page_title="EndzoneAPI Data Audit",
    page_icon="🔌",
    layout="wide",
)

st.title("EndzoneAPI Data Audit")
st.caption(
    "Read-only diagnostics only. These tests do not change model predictions or stored data."
)

st.info(
    "Run each test separately. Estimated costs: schedule 2 credits, historical games 5, "
    "one game's or one season's sportsbook odds 10, historical injuries 2. Failed server requests are "
    "normally refunded by EndzoneAPI. Your API key is never displayed."
)

try:
    API_KEY = st.secrets.get("ENDZONE_API_KEY", "")
except Exception:
    API_KEY = ""

if not API_KEY:
    st.error(
        "ENDZONE_API_KEY was not found in Streamlit Secrets. Add it under app Settings → Secrets."
    )
    st.stop()


def post_api(endpoint, payload):
    """Make one authenticated JSON request and return status and decoded response."""
    request = urllib.request.Request(
        f"{BASE_URL}/{endpoint}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": API_KEY,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read(2_000_000).decode("utf-8", errors="replace")
            status = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read(2000).decode("utf-8", errors="replace")
        status = exc.code
    except urllib.error.URLError as exc:
        st.error(f"Could not reach EndzoneAPI: {exc.reason}")
        return None, None
    try:
        return status, json.loads(raw)
    except json.JSONDecodeError:
        return status, {"non_json_response": raw[:1000]}


def show_result(endpoint, status, data):
    if status is None:
        return
    st.write(f"HTTP status: **{status}**")
    if status == 200:
        st.success(f"{endpoint} returned HTTP 200.")
    else:
        st.error(f"{endpoint} returned HTTP {status}.")
    if isinstance(data, dict):
        st.write("Top-level response fields:", ", ".join(str(k) for k in list(data)[:30]))
        if "error" in data:
            st.warning(str(data["error"]))
    st.json(data)


def unwrap_response(data):
    """EndzoneAPI responses may wrap the endpoint payload inside a top-level data field."""
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        return data["data"]
    return data


def show_game_summary(games):
    if not isinstance(games, list):
        st.warning("No list was found at the expected 'games' response field.")
        return
    st.metric("Games returned", len(games))
    if not games:
        return
    import pandas as pd

    safe_columns = [
        "game_id", "season", "week", "gameday", "kickoff",
        "away_team", "home_team", "away_score", "home_score",
        "total", "total_line", "spread_line", "away_moneyline",
        "home_moneyline", "status",
    ]
    rows = [
        {key: game.get(key) for key in safe_columns if key in game}
        for game in games[:10]
        if isinstance(game, dict)
    ]
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    present = set().union(*(row.keys() for row in rows)) if rows else set()
    st.write("Field availability in sample:", ", ".join(sorted(present)))


with st.expander("Test 1 — upcoming schedule (2 credits)", expanded=True):
    st.write("Checks authentication and confirms the actual schedule response structure.")
    if st.button("Run schedule test", key="schedule_test", type="primary"):
        status, data = post_api("get_schedule", {"days": 7})
        show_result("get_schedule", status, data)
        payload = unwrap_response(data)
        if status == 200 and isinstance(payload, dict):
            games = payload.get("upcoming_games", payload.get("games", []))
            show_game_summary(games)

with st.expander("Test 2 — historical games and closing lines (5 credits)"):
    st.write(
        "Checks whether completed 2025 games and consensus closing totals are returned. "
        "This is useful for a historical baseline, but it does not provide bookmaker-specific "
        "opening prices."
    )
    if st.button("Run 2025 historical games test", key="games_test"):
        status, data = post_api(
            "get_games",
            {"season": 2025, "game_type": "REG", "limit": 300},
        )
        show_result("get_games", status, data)
        payload = unwrap_response(data)
        if status == 200 and isinstance(payload, dict):
            show_game_summary(payload.get("games", []))
            games = payload.get("games", [])
            if isinstance(games, list) and games:
                total_lines = sum(
                    isinstance(g, dict) and g.get("total_line") is not None for g in games
                )
                scores = sum(
                    isinstance(g, dict)
                    and g.get("away_score") is not None
                    and g.get("home_score") is not None
                    for g in games
                )
                st.write(f"Rows with a total line: **{total_lines}/{len(games)}**")
                st.write(f"Rows with both final scores: **{scores}/{len(games)}**")

with st.expander("Test 3 — sportsbook-specific historical odds (10 credits)"):
    st.write(
        "Checks one historical game for bookmaker-specific opening/closing totals, prices, "
        "and capture timestamps. This is the most important test for reliable backtesting."
    )
    game_id = st.text_input(
        "Game ID",
        value="2025_01_KC_LAC",
        help="Defaults to a documented 2025 regular-season game. You can leave it unchanged.",
    )
    if st.button("Run historical odds test", key="odds_test"):
        if not game_id.strip():
            st.error("Enter a game ID.")
        else:
            status, data = post_api("get_odds", {"game_id": game_id.strip()})
            show_result("get_odds", status, data)
            payload = unwrap_response(data)
            if status == 200 and isinstance(payload, dict):
                books = payload.get("books", [])
                st.metric("Bookmakers returned", len(books) if isinstance(books, list) else 0)
                if isinstance(books, list):
                    summaries = []
                    for book in books:
                        if not isinstance(book, dict):
                            continue
                        row = {"bookmaker": book.get("bookmaker")}
                        for snap_name in ("opening", "closing", "latest"):
                            snap = book.get(snap_name)
                            if isinstance(snap, dict):
                                row[f"{snap_name}_total"] = snap.get("total")
                                row[f"{snap_name}_over_odds"] = snap.get("total_over_odds")
                                row[f"{snap_name}_under_odds"] = snap.get("total_under_odds")
                                row[f"{snap_name}_captured_at"] = snap.get("captured_at")
                        summaries.append(row)
                    if summaries:
                        import pandas as pd
                        st.dataframe(pd.DataFrame(summaries), use_container_width=True, hide_index=True)
                if isinstance(payload.get("consensus_closing"), dict):
                    st.write("Consensus closing line:")
                    st.json(payload["consensus_closing"])

with st.expander("Test 4 — historical injury report (2 credits)"):
    st.write(
        "Checks whether archived practice participation and game-status reports are available. "
        "This sample is for Kansas City, Week 9 of 2025."
    )
    if st.button("Run historical injury test", key="injury_test"):
        status, data = post_api(
            "get_injuries",
            {"team": "KC", "season": 2025, "week": 9},
        )
        show_result("get_injuries", status, data)
        payload = unwrap_response(data)
        if status == 200 and isinstance(payload, dict):
            injuries = payload.get("injuries", [])
            st.metric("Injury records returned", len(injuries) if isinstance(injuries, list) else 0)
            if isinstance(injuries, list) and injuries:
                import pandas as pd
                fields = [
                    "team", "name", "position", "report_status",
                    "practice_status", "report_primary_injury", "game_type",
                ]
                st.dataframe(
                    pd.DataFrame([
                        {key: player.get(key) for key in fields if key in player}
                        for player in injuries[:30]
                        if isinstance(player, dict)
                    ]),
                    use_container_width=True,
                    hide_index=True,
                )


with st.expander("Test 5 — full-season sportsbook odds coverage (10 credits)"):
    st.write(
        "Fetches one season of per-book odds in a single request, then summarizes game coverage, "
        "bookmaker coverage, and whether recorded closing timestamps precede kickoff. "
        "This is the next recommended test before model integration."
    )
    odds_season = st.selectbox(
        "Season to audit",
        options=[2025, 2024, 2023, 2022, 2021, 2020],
        index=0,
        key="odds_season",
    )
    if st.button("Audit full-season odds", key="season_odds_test"):
        status, data = post_api(
            "get_odds",
            {
                "season": odds_season,
                "snapshot_type": "closing",
                "limit": 500,
            },
        )
        show_result("get_odds (season)", status, data)
        payload = unwrap_response(data)
        if status == 200 and isinstance(payload, dict):
            games = payload.get("games", [])
            if isinstance(games, list) and games:
                import pandas as pd

                game_rows = []
                book_rows = []
                for game in games:
                    if not isinstance(game, dict):
                        continue
                    kickoff = pd.to_datetime(game.get("kickoff"), utc=True, errors="coerce")
                    game_rows.append({
                        "game_id": game.get("game_id"),
                        "kickoff": game.get("kickoff"),
                        "bookmakers": len(game.get("books", []))
                            if isinstance(game.get("books"), list) else 0,
                    })
                    for book in game.get("books", []) if isinstance(game.get("books"), list) else []:
                        if not isinstance(book, dict):
                            continue
                        snap = book.get("closing")
                        if not isinstance(snap, dict):
                            snap = book.get("latest")
                        if not isinstance(snap, dict):
                            continue
                        captured = pd.to_datetime(
                            snap.get("captured_at"), utc=True, errors="coerce"
                        )
                        book_rows.append({
                            "game_id": game.get("game_id"),
                            "bookmaker": book.get("bookmaker"),
                            "total": snap.get("total"),
                            "over_odds": snap.get("total_over_odds"),
                            "under_odds": snap.get("total_under_odds"),
                            "both_prices_available": (
                                snap.get("total_over_odds") is not None
                                and snap.get("total_under_odds") is not None
                            ),
                            "captured_at": snap.get("captured_at"),
                            "kickoff": game.get("kickoff"),
                            "timestamp_before_kickoff": (
                                bool(captured < kickoff)
                                if pd.notna(captured) and pd.notna(kickoff)
                                else None
                            ),
                        })
                books_df = pd.DataFrame(book_rows)
                games_df = pd.DataFrame(game_rows)
                st.metric("Games returned", len(games_df))
                if not books_df.empty:
                    st.metric("Bookmaker-game price rows", len(books_df))
                    st.write("Bookmaker coverage:")
                    st.dataframe(
                        books_df.groupby("bookmaker", dropna=False).agg(
                            games_with_prices=("game_id", "nunique"),
                            rows=("game_id", "size"),
                            rows_with_total=("total", lambda x: x.notna().sum()),
                            rows_with_both_prices=(
                                "both_prices_available",
                                "sum",
                            ),
                            timestamps_before_kickoff=(
                                "timestamp_before_kickoff",
                                lambda x: (x == True).sum(),
                            ),
                        ).reset_index().sort_values("games_with_prices", ascending=False),
                        use_container_width=True,
                        hide_index=True,
                    )
                    known_timestamps = books_df["timestamp_before_kickoff"].dropna()
                    if len(known_timestamps):
                        pct = 100 * known_timestamps.mean()
                        st.write(
                            f"Rows with a parseable timestamp before kickoff: "
                            f"**{int(known_timestamps.sum())}/{len(known_timestamps)} "
                            f"({pct:.1f}%)**."
                        )
                    st.write("Sample bookmaker prices:")
                    st.dataframe(books_df.head(20), use_container_width=True, hide_index=True)
                    st.download_button(
                        "Download season odds audit CSV",
                        data=books_df.to_csv(index=False).encode("utf-8"),
                        file_name=f"endzoneapi_odds_audit_{odds_season}.csv",
                        mime="text/csv",
                    )
                else:
                    st.warning(
                        "The response contained games but no recognizable per-book closing "
                        "snapshots. Inspect the response fields above before proceeding."
                    )
            else:
                st.warning(
                    "No list of games was found in the season response. Inspect the response "
                    "fields above; the endpoint may use a different wrapper/schema."
                )

st.divider()
st.caption(
    "No response is treated as proof of a betting edge. Historical odds must be checked for "
    "source, timestamp, sportsbook, and whether the price was available before kickoff. "
    "Only run tests you need; each successful call consumes the credits listed above."
)
