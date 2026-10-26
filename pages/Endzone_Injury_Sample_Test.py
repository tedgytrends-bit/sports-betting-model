import json
import os

import pandas as pd
import requests
import streamlit as st

st.title("EndzoneAPI Historical Injury Sample Test")
st.caption("Small diagnostic only • Does not change the model or backtest")

st.markdown(
    "This makes two targeted requests to EndzoneAPI to check whether its historical injury responses "
    "contain report timestamps or dates that could support leakage-safe backtesting. It does not download "
    "a full season or modify any model inputs."
)
st.warning(
    "The test uses the API key already stored in Streamlit Secrets as ENDZONE_API_KEY. "
    "The key is never displayed. Expected cost is 4 credits total (2 credits per request), if both calls succeed."
)

with st.expander("What this test checks"):
    st.markdown(
        "- 2025, Week 9 — a completed historical week.\n"
        "- 2026, Week 7 — a completed recent week.\n"
        "- Response field names, timestamp/date-like fields, sample values, and credit headers.\n"
        "- A date field alone does not prove the data was captured before kickoff; we need a trustworthy report/update timestamp."
    )

def get_api_key():
    try:
        key = st.secrets.get("ENDZONE_API_KEY", "")
    except Exception:
        key = ""
    return str(key).strip() if key else os.getenv("ENDZONE_API_KEY", "").strip()

def unwrap_payload(payload):
    if isinstance(payload, dict) and isinstance(payload.get("data"), (dict, list)):
        return payload["data"]
    return payload

if st.button("Run 2-request injury sample test", type="primary"):
    api_key = get_api_key()
    if not api_key:
        st.error("ENDZONE_API_KEY was not found in Streamlit Secrets or environment variables. Add it in the app's Secrets settings; do not paste it into chat.")
        st.stop()

    endpoint = "https://mcp.endzoneapi.com/v1/get_injuries"
    tests = [
        {"season": 2025, "week": 9},
        {"season": 2026, "week": 7},
    ]
    results = []
    progress = st.progress(0)

    for idx, params in enumerate(tests):
        try:
            response = requests.post(
                endpoint,
                headers={"x-api-key": api_key, "Content-Type": "application/json"},
                json=params,
                timeout=(5, 30),
            )
            used = response.headers.get("X-Credits-Used", "not returned")
            remaining = response.headers.get("X-Credits-Remaining", "not returned")
            try:
                payload = response.json()
            except Exception:
                payload = {"raw_text": response.text[:2000]}

            unwrapped = unwrap_payload(payload)
            rows = []
            if isinstance(unwrapped, dict):
                candidate = unwrapped.get("injuries")
                if isinstance(candidate, list):
                    rows = candidate
                elif isinstance(unwrapped.get("data"), list):
                    rows = unwrapped["data"]
            elif isinstance(unwrapped, list):
                rows = unwrapped

            all_keys = set()
            for row in rows[:100]:
                if isinstance(row, dict):
                    all_keys.update(row.keys())
            date_keys = sorted(
                key for key in all_keys
                if any(term in str(key).lower() for term in ("date", "time", "timestamp", "modified", "updated", "published", "created"))
            )
            sample = rows[:5]
            results.append({
                "season": params["season"],
                "week": params["week"],
                "http_status": response.status_code,
                "credits_used": used,
                "credits_remaining": remaining,
                "payload": payload,
                "row_count": len(rows),
                "row_keys": sorted(all_keys),
                "date_keys": date_keys,
                "sample": sample,
            })
        except Exception as exc:
            results.append({
                "season": params["season"],
                "week": params["week"],
                "error": f"{type(exc).__name__}: {exc}",
            })
        progress.progress((idx + 1) / len(tests))

    summary_rows = []
    for item in results:
        summary_rows.append({
            "Season": item["season"],
            "Week": item["week"],
            "HTTP status": item.get("http_status", "error"),
            "Rows returned": item.get("row_count", 0),
            "Date/time fields": ", ".join(item.get("date_keys", [])) or "(none detected)",
            "Credits used": item.get("credits_used", "not returned"),
            "Credits remaining": item.get("credits_remaining", "not returned"),
            "Error": item.get("error", ""),
        })
    st.subheader("Test summary")
    st.dataframe(pd.DataFrame(summary_rows), hide_index=True, use_container_width=True)

    for item in results:
        title = f'{item["season"]} Week {item["week"]}'
        with st.expander(f"{title} — response details", expanded=True):
            if "error" in item:
                st.error(item["error"])
                continue
            st.write(f'HTTP status: {item["http_status"]} • Rows extracted: {item["row_count"]}')
            st.write("Detected date/time fields:", item.get("date_keys") or "None")
            st.write("All returned injury-row fields:", item.get("row_keys") or "No injury rows detected")
            st.markdown("**Sample injury rows (up to 5)**")
            if item.get("sample"):
                st.json(item["sample"])
            else:
                st.json(item["payload"])

    st.info(
        "Decision rule: if the response contains a genuine report/update timestamp, next verify it predates kickoff "
        "for the historical game week. If it only contains current/final statuses or no timing metadata, we should "
        "not use it as a historical pregame feature."
    )
