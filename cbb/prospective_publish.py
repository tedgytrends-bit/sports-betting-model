"""Publish CBB shadow pregame snapshots to an isolated GitHub data branch.

Runs ONLY in the explicitly configured GitHub Actions workflow. Immutable
snapshots/frozen predictions are never replaced. latest.json may change.
"""
import argparse
import base64
import json
import os
import re
import time
from pathlib import Path

import requests


class GitHubStore:
    def __init__(self, repository, branch, token):
        if not repository or "/" not in repository or not branch or not token:
            raise ValueError("Expected GitHub repository, target branch, and token")
        self.repository, self.branch = repository, branch
        self.api = "https://api.github.com/repos/" + repository + "/contents/"
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })

    def read_json(self, path):
        """Read JSON from the isolated data branch or return None on 404."""
        r = self.session.get(self.api + path, params={"ref": self.branch}, timeout=45)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        payload = r.json()
        if payload.get("encoding") != "base64":
            raise ValueError("Expected base64 GitHub Contents JSON for " + path)
        return json.loads(base64.b64decode(payload["content"]))

    def existing_sha(self, path):
        r = self.session.get(self.api + path, params={"ref": self.branch}, timeout=40)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()["sha"]

    def put_json(self, path, body, immutable=True):
        data = (json.dumps(body, ensure_ascii=False, indent=2,
                           sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
        for attempt in range(4):
            sha = self.existing_sha(path)
            if sha and immutable:
                return "existing"
            payload = {
                "message": ("CBB: freeze pregame " if immutable else "CBB: update latest ") + path,
                "content": base64.b64encode(data).decode("ascii"),
                "branch": self.branch,
            }
            if sha:
                payload["sha"] = sha
            r = self.session.put(self.api + path, json=payload, timeout=50)
            if r.ok:
                return "created" if not sha else "updated"
            if r.status_code in (409, 422) and attempt < 3:
                # Concurrent data-branch activity: re-read current SHA, but
                # never overwrite immutable entries if another run won.
                time.sleep(1 + attempt)
                continue
            r.raise_for_status()
        raise RuntimeError(f"Failed publishing {path} after retries")


def validate(board):
    if board.get("capture_type") != "research_shadow" or board.get("capture_version") != 1:
        raise ValueError("Unexpected capture format")
    season = int(board["season"])
    if not 2020 <= season <= 2050:
        raise ValueError("Season out of expected bounds")
    time_string = str(board["capture_utc"])
    if not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z", time_string):
        raise ValueError("Capture timestamp must be a UTC ISO string")
    for g in board["games"]:
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", str(g["id"])):
            raise ValueError("Unsafe game ID")
        if str(g["tip_utc"]) <= time_string:
            raise ValueError("Cannot publish past games as prospective")
    return season


def publish(board, store, run_id):
    season = validate(board)
    stamp = board["capture_utc"].replace("-", "").replace(":", "").replace(".", "")
    stamp = stamp.replace("Z", "")
    suffix = re.sub(r"[^a-zA-Z0-9_-]", "", str(run_id))
    root = f"cbb/prospective/{season}"
    name = f"{stamp}_{suffix}.json"
    snapshot_path = f"{root}/snapshots/{name}"
    saved = store.put_json(snapshot_path, board, immutable=True)
    frozen_new = frozen_existing = 0
    for record in board["games"]:
        if not record["freeze_candidate"]:
            continue
        frozen = {
            "capture_version": 1,
            "capture_type": board["capture_type"],
            "capture_utc": board["capture_utc"],
            "model_commit": board["model_commit"],
            "source": board["source"],
            "source_sha256": board["source_sha256"],
            "game": record,
            "frozen_rule": "First snapshot within 24 hours before tip with at least one market line",
            "snapshot_path": snapshot_path,
        }
        result = store.put_json(f"{root}/frozen/{record['id']}.json", frozen, immutable=True)
        frozen_new += result == "created"
        frozen_existing += result == "existing"
    latest = {
        **board,
        "snapshot_path": snapshot_path,
        "latest_rule": "Most recent timestamped projection; do not grade as pre-tip frozen",
    }
    updated = store.put_json(f"{root}/latest.json", latest, immutable=False)
    print("CBB_PUBLISHED", json.dumps({
        "snapshot": snapshot_path, "snapshot_result": saved,
        "frozen_created": frozen_new, "frozen_already_exists": frozen_existing,
        "latest_result": updated, "upcoming": len(board["games"]),
        "branch": store.branch,
    }))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--capture", default="cbb/outputs/prospective/latest_capture.json")
    args = ap.parse_args()
    board = json.loads(Path(args.capture).read_text(encoding="utf-8"))
    store = GitHubStore(
        os.getenv("GITHUB_REPOSITORY"),
        os.getenv("CBB_PUBLISH_BRANCH", "cbb-prospective"),
        os.getenv("GITHUB_TOKEN"),
    )
    publish(board, store, os.getenv("GITHUB_RUN_ID", "manual"))


if __name__ == "__main__":
    main()
