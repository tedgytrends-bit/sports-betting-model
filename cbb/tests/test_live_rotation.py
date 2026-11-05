"""Daily current-season box-score caching and cutoff checks."""
from datetime import datetime, timezone, timedelta
import json

import pytest
from cbb.live_rotation import (
    aware, elapsed_windows, refresh_live_player_boxes, load_live_player_boxes,
)


def test_elapsed_windows_stop_at_asof():
    start=aware("2026-10-01T00:00:00Z")
    end=aware("2026-11-05T22:00:00Z")
    windows=list(elapsed_windows(start,end))
    assert windows[0][0]=="2026-10-01T00:00:00Z"
    assert windows[-1][1]=="2026-11-05T22:00:00Z"
    assert all(a[1]==b[0] for a,b in zip(windows,windows[1:]))
    assert len(windows)==6


def test_first_capture_and_incremental_refetch(monkeypatch,tmp_path):
    calls=[]
    sample=dict(
        gameId=1,teamId=100,season=2027,startDate="2026-11-03T19:00:00Z",
        players=[dict(athleteId=4,minutes=30,starter=True)]
    )
    sample2={**sample,"gameId":2,"startDate":"2026-11-06T18:00:00Z"}
    future={**sample,"gameId":3,"startDate":"2026-11-10T18:00:00Z"}
    def fake_week(session,season,left,right,token):
        calls.append((left,right))
        return [sample,sample2,future]
    monkeypatch.setenv("CBBD_API_KEY","sample-from-test-fixture")
    monkeypatch.setattr("cbb.live_rotation.get_week",fake_week)
    t1=aware("2026-11-05T22:00:00Z")
    out1,meta1=refresh_live_player_boxes(2027,str(tmp_path),t1)
    assert len(calls)==6
    assert [x["gameId"] for x in out1]==[1]
    assert meta1["unique_games"]==1
    calls.clear()
    t2=aware("2026-11-06T22:00:00Z")
    out2,meta2=refresh_live_player_boxes(2027,str(tmp_path),t2)
    assert len(calls)==2
    assert [x["gameId"] for x in out2]==[1,2]
    assert meta2["unique_games"]==2
    assert len(load_live_player_boxes(2027,str(tmp_path)))==2
    assert calls[0][0]=="2026-10-29T22:00:00Z"


def test_missing_cache_and_naive_time_fail(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_live_player_boxes(2027,str(tmp_path))
    with pytest.raises(ValueError,match="Naive"):
        aware("2026-11-05T21:00:00")
    with pytest.raises(ValueError,match="timezone-aware"):
        refresh_live_player_boxes(2027,str(tmp_path),datetime(2026,11,5))


def test_basketball_future_season_rejected(tmp_path):
    with pytest.raises(ValueError,match="not yet begun"):
        refresh_live_player_boxes(2029,str(tmp_path),
                                  aware("2026-11-05T22:00:00Z"))
