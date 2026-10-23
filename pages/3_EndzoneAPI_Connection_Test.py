import json
import urllib.error
import urllib.request

import streamlit as st

st.set_page_config(
    page_title="EndzoneAPI Connection Test",
    page_icon="🔌",
    layout="centered",
)

st.title("EndzoneAPI Connection Test")
st.caption("Temporary, read-only diagnostic. It does not change model predictions or stored data.")

st.info(
    "This test makes one small get_schedule request (2 credits according to EndzoneAPI's docs). "
    "It only displays the HTTP result and a small response summary; it never displays your API key."
)

if st.button("Test EndzoneAPI connection", type="primary"):
    try:
        api_key = st.secrets.get("ENDZONE_API_KEY", "")
    except Exception:
        api_key = ""

    if not api_key:
        st.error(
            "ENDZONE_API_KEY was not found in Streamlit Secrets. "
            "Check the secret name and save it in the app's Secrets settings."
        )
        st.stop()

    url = "https://mcp.endzoneapi.com/v1/get_schedule"
    payload = json.dumps({"days": 7}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            status_code = response.status
            raw_body = response.read(1_000_000).decode("utf-8", errors="replace")

        st.write(f"HTTP status: **{status_code}**")
        try:
            data = json.loads(raw_body)
        except json.JSONDecodeError:
            st.error("The API returned a response that was not valid JSON.")
            st.code(raw_body[:1000])
            st.stop()

        if status_code == 200:
            st.success("The API key authenticated and the endpoint returned HTTP 200.")
            if isinstance(data, dict):
                st.write("Top-level response fields:", ", ".join(list(data.keys())[:30]))
                games = data.get("games")
                if isinstance(games, list):
                    st.metric("Games returned", len(games))
                    if games:
                        sample = games[0]
                        if isinstance(sample, dict):
                            safe_fields = [
                                "game_id", "season", "week", "gameday",
                                "away_team", "home_team", "status",
                            ]
                            st.write(
                                "Sample game:",
                                {key: sample.get(key) for key in safe_fields if key in sample},
                            )
                elif "error" in data:
                    st.warning(f"API response included an error field: {data.get('error')}")
            else:
                st.write("Response type:", type(data).__name__)
        else:
            st.error(f"EndzoneAPI returned HTTP {status_code}.")
            st.write("Response summary:")
            if isinstance(data, dict):
                # Keep diagnostics compact and avoid printing arbitrary headers or secrets.
                st.json({key: value for key, value in data.items() if key.lower() not in {"api_key", "key", "token"}})
            else:
                st.code(raw_body[:1000])

    except urllib.error.HTTPError as exc:
        st.error(f"EndzoneAPI returned HTTP {exc.code}.")
        try:
            body = exc.read(1000).decode("utf-8", errors="replace")
            st.code(body)
        except Exception:
            st.write("No readable error details were returned.")
    except urllib.error.URLError as exc:
        st.error("Could not reach EndzoneAPI from the Streamlit app.")
        st.write(str(exc.reason))
    except Exception as exc:
        st.error(f"Unexpected diagnostic failure: {type(exc).__name__}")
        st.write(str(exc))
