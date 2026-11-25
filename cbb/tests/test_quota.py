"""Quota-reduction controls, no live network used in tests."""
from datetime import datetime, timezone
import json

import pytest

from cbb.ingest import windows, fetch_season
from cbb.player_ingest import player_inputs


def test_horizon_restricts_current_season_months():
    assert len(list(windows(2027))) == 8
    assert len(list(windows(2027, datetime(2026,11,14,tzinfo=timezone.utc)))) == 2
    assert len(list(windows(2027, datetime(2026,12,14,tzinfo=timezone.utc)))) == 3
    assert len(list(windows(2027, datetime(2027,3,1,tzinfo=timezone.utc)))) == 6


def test_roster_refresh_preserves_previous_season_input_cache(tmp_path,monkeypatch):
    folder=tmp_path/"2027"
    folder.mkdir()
    for name in ("rosters","prior_players","portal","recruits"):
        (folder/(name+".json")).write_text(json.dumps([{"source":name}]),encoding="utf-8")
    called=[]
    def fake_fetch(session, endpoint, params, token):
        called.append(endpoint)
        return [{"source":"new"}]
    monkeypatch.setattr("cbb.player_ingest.get_collection",fake_fetch)
    monkeypatch.setenv("CBBD_API_KEY","synthetic-unit-test-token")
    result=player_inputs(2027,root=str(tmp_path),refresh_roster_only=True)
    assert called==["/teams/roster"]
    assert result["rosters"]==[{"source":"new"}]
    assert result["prior_players"]==[{"source":"prior_players"}]
    assert result["portal"]==[{"source":"portal"}]
    assert result["recruits"]==[{"source":"recruits"}]


def test_rejects_negative_data_horizon():
    with pytest.raises(ValueError,match="non-negative"):
        fetch_season(2027,through_days=-1)
