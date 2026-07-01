import re
import requests
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

HEADERS_BASE = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "Referer": "https://vidfast.pro/",
    "X-Requested-With": "XMLHttpRequest"
}
API = "https://enc-dec.app/api"


def validate(data, path):
    if data.get("status") != 200:
        raise ValueError(f"API error at {path}: {data.get('error', 'unknown')}")
    return data["result"]


def resolve_vidfast(media_type, tmdb_id, season=None, episode=None):
    if media_type == "movie":
        base_url = f"https://vidfast.pro/movie/{tmdb_id}/"
    else:
        base_url = f"https://vidfast.pro/tv/{tmdb_id}/{season}/{episode}/"

    resp = requests.get(base_url, headers=HEADERS_BASE, timeout=15)
    resp.raise_for_status()
    page = resp.text

    match = re.search(r'\\"en\\":\\"(.*?)\\"', page)
    if not match:
        raise ValueError("Could not extract token text from page")
    text = match.group(1)

    enc_url = f"{API}/enc-vidfast?text={text}"
    r = requests.get(enc_url, timeout=15).json()
    parts = validate(r, enc_url)

    servers_url = parts["servers"]
    stream_base = parts["stream"]
    token = parts["token"]

    headers = {**HEADERS_BASE, "X-CSRF-Token": token}

    servers_enc = requests.post(servers_url, headers=headers, timeout=15).text
    r = requests.post(f"{API}/dec-vidfast", json={"text": servers_enc}, timeout=15).json()
    servers = validate(r, "dec-vidfast/servers")

    results = []
    for server in servers:
        try:
            data = server["data"]
            stream_url = f"{stream_base}/{data}"
            stream_enc = requests.post(stream_url, headers=headers, timeout=15).text
            r = requests.post(f"{API}/dec-vidfast", json={"text": stream_enc}, timeout=15).json()
            stream_dec = validate(r, "dec-vidfast/stream")
            results.append({
                "server": server.get("name", server.get("id", data)),
                "data": stream_dec,
                "referer": "https://vidfast.pro/"
            })
        except Exception as e:
            results.append({
                "server": server.get("name", server.get("id", "unknown")),
                "error": str(e)
            })

    return results


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/resolve", methods=["POST"])
def resolve():
    body = request.get_json()
    media_type = body.get("type", "movie")
    tmdb_id = body.get("tmdb_id", "").strip()
    season = body.get("season", "").strip()
    episode = body.get("episode", "").strip()

    if not tmdb_id:
        return jsonify({"error": "TMDB ID is required"}), 400
    if media_type == "tv" and (not season or not episode):
        return jsonify({"error": "Season and episode are required for TV"}), 400

    try:
        results = resolve_vidfast(media_type, tmdb_id, season, episode)
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=False)
