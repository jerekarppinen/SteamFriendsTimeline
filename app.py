import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from time import time
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import requests


FRIEND_LIST_URL = "https://api.steampowered.com/ISteamUser/GetFriendList/v1/"
PLAYER_SUMMARIES_URL = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"
GROUP_LIST_URL = "https://api.steampowered.com/ISteamUser/GetUserGroupList/v1/"
VANITY_URL = "https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/"
CACHE_TTL_SECONDS = 6 * 60 * 60
timeline_cache = {}


def load_env(path=".env"):
    values = {}

    with open(path, encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()

            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")

    return values


ENV = load_env()
API_KEY = ENV.get("STEAM_API_KEY")

if not API_KEY:
    raise ValueError("Lisää STEAM_API_KEY .env-tiedostoon.")


def request_json(url, params):
    response = requests.get(url, params=params, timeout=20)
    response.raise_for_status()
    return response.json()


def parse_profile_part(profile_url):
    parsed = urlparse(profile_url.strip())

    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Syötä koko Steam-profiilin URL, esimerkiksi https://steamcommunity.com/id/nimi/")

    if parsed.netloc.lower() != "steamcommunity.com":
        raise ValueError("URL ei ole steamcommunity.com-profiili.")

    parts = [part for part in parsed.path.split("/") if part]

    if len(parts) < 2 or parts[0] not in {"profiles", "id"}:
        raise ValueError("URL ei näytä Steam-profiililta.")

    return parts[0], parts[1]


def get_steam_id(profile_url):
    profile_type, profile_part = parse_profile_part(profile_url)

    if profile_type == "profiles":
        if not profile_part.isdigit():
            raise ValueError("Steam-profiilin numeerinen ID ei ole validi.")

        return profile_part

    data = request_json(VANITY_URL, {
        "key": API_KEY,
        "vanityurl": profile_part
    })["response"]

    if data.get("success") != 1:
        raise ValueError("Steam vanity -osoitteesta ei löytynyt profiilia.")

    return data["steamid"]


def get_player_names(steam_ids):
    players = []

    for start in range(0, len(steam_ids), 100):
        batch = steam_ids[start:start + 100]
        data = request_json(PLAYER_SUMMARIES_URL, {
            "key": API_KEY,
            "steamids": ",".join(batch)
        })
        players.extend(data["response"]["players"])

    return {
        player["steamid"]: player.get("personaname", player["steamid"])
        for player in players
    }


def get_group_data(steam_id, friend_ids):
    data = request_json(GROUP_LIST_URL, {
        "key": API_KEY,
        "steamid": steam_id
    })
    groups = data.get("response", {}).get("groups", [])

    group_options = []
    friend_groups = {friend_id: [] for friend_id in friend_ids}
    friend_id_set = set(friend_ids)

    for group in groups:
        group_id = group["gid"]
        response = requests.get(
            f"https://steamcommunity.com/gid/{group_id}/memberslistxml/",
            params={"xml": 1},
            timeout=20
        )

        if response.status_code != 200:
            continue

        try:
            root = ET.fromstring(response.text)
        except ET.ParseError:
            continue

        group_name = root.findtext("groupDetails/groupName") or group_id
        member_ids = {
            member.text
            for member in root.findall("members/steamID64")
            if member.text
        }
        matching_friend_ids = sorted(friend_id_set.intersection(member_ids))

        if not matching_friend_ids:
            continue

        group_options.append({
            "id": group_id,
            "name": group_name,
            "count": len(matching_friend_ids),
        })

        for friend_id in matching_friend_ids:
            friend_groups[friend_id].append(group_id)

    return (
        sorted(group_options, key=lambda item: item["name"].casefold()),
        friend_groups,
    )


def build_timeline(profile_url):
    steam_id = get_steam_id(profile_url)
    cached = timeline_cache.get(steam_id)

    if cached and time() - cached["created_at"] < CACHE_TTL_SECONDS:
        return cached["data"]

    data = request_json(FRIEND_LIST_URL, {
        "key": API_KEY,
        "steamid": steam_id,
        "relationship": "friend"
    })

    friends = [
        friend
        for friend in data["friendslist"]["friends"]
        if friend.get("friend_since", 0) > 0
    ]
    friends.sort(key=lambda friend: friend["friend_since"])

    steam_ids = [friend["steamid"] for friend in friends]
    names = get_player_names(steam_ids)
    group_options, friend_groups = get_group_data(steam_id, steam_ids)

    dates = []
    date_texts = []

    for friend in friends:
        date = datetime.fromtimestamp(friend["friend_since"], timezone.utc)
        dates.append(date.strftime("%Y-%m-%dT%H:%M:%S"))
        date_texts.append(f"{date:%H:%M} {date.day}.{date.month}.{date.year}")

    result = {
        "dates": dates,
        "positions": list(range(1, len(friends) + 1)),
        "names": [names.get(steam_id, steam_id) for steam_id in steam_ids],
        "dateTexts": date_texts,
        "steamIds": steam_ids,
        "groups": group_options,
        "friendGroups": [friend_groups[steam_id] for steam_id in steam_ids],
    }

    timeline_cache[steam_id] = {
        "created_at": time(),
        "data": result,
    }

    return result


INDEX_HTML = """<!doctype html>
<html lang="fi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Steam-kaverit aikajanalla</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    body {
      margin: 0;
      font-family: Arial, sans-serif;
      background: #f7f7f7;
      color: #222;
    }

    .topbar {
      position: fixed;
      top: 14px;
      left: 18px;
      right: 18px;
      z-index: 10;
      display: grid;
      grid-template-columns: minmax(240px, 520px) auto;
      align-items: center;
      gap: 12px;
      padding: 10px 12px;
      border: 1px solid #d8d8d8;
      border-radius: 6px;
      background: rgba(255, 255, 255, 0.96);
      box-shadow: 0 4px 18px rgba(0, 0, 0, 0.08);
    }

    .field {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    label {
      font-size: 14px;
      font-weight: 600;
      white-space: nowrap;
    }

    input,
    select {
      font-size: 14px;
      padding: 8px 9px;
      border: 1px solid #c8c8c8;
      border-radius: 5px;
      background: #fff;
    }

    input {
      width: 100%;
    }

    select {
      min-width: 260px;
    }

    input.valid-flash {
      animation: validFlash 700ms ease-out;
    }

    @keyframes validFlash {
      0% {
        border-color: #1f9d55;
        box-shadow: 0 0 0 3px rgba(31, 157, 85, 0.24);
        background: #f0fff6;
      }

      100% {
        border-color: #c8c8c8;
        box-shadow: none;
        background: #fff;
      }
    }

    #chart {
      width: 100vw;
      height: calc(100vh - 74px);
      margin-top: 74px;
    }

    @media (max-width: 860px) {
      .topbar {
        grid-template-columns: 1fr;
      }

      .field {
        align-items: stretch;
        flex-direction: column;
      }

      select {
        min-width: 0;
        width: 100%;
      }
    }
  </style>
</head>
<body>
  <div class="topbar">
    <div class="field">
      <label for="profile-url">Steam-profiili</label>
      <input id="profile-url" type="url" placeholder="Syötä Steam-profiilin URL">
    </div>
    <div class="field">
      <label for="group-filter">Ryhmä</label>
      <select id="group-filter" disabled>
        <option>Ei dataa</option>
      </select>
    </div>
  </div>

  <div id="chart"></div>

  <script>
    const input = document.getElementById("profile-url");
    const groupFilter = document.getElementById("group-filter");
    const profileStorageKey = "steamfriends.profileUrl";
    const groupStorageKey = "steamfriends.groupId";
    let currentData = null;
    let debounceTimer = null;
    let lastRequestedUrl = "";

    const emptyLayout = {
      title: "Steam-kaverit aikajanalla",
      xaxis: { title: "Kaveruuden alkamispäivä" },
      yaxis: { title: "Kaverien kertymä" },
      margin: { l: 70, r: 30, t: 96, b: 90 },
      hovermode: "closest",
      annotations: [{
        text: "Syötä Steam-profiilin URL.",
        xref: "paper",
        yref: "paper",
        x: 0.5,
        y: 0.5,
        showarrow: false,
        font: { size: 18, color: "#666" }
      }]
    };

    const config = {
      responsive: true,
      displaylogo: false,
      scrollZoom: true
    };

    Plotly.newPlot("chart", [], emptyLayout, config);

    function showChartMessage(message, isError = false) {
      Plotly.react("chart", [], {
        ...emptyLayout,
        annotations: [{
          text: message,
          xref: "paper",
          yref: "paper",
          x: 0.5,
          y: 0.5,
          showarrow: false,
          font: {
            size: 20,
            color: isError ? "#b42318" : "#555"
          }
        }]
      }, config);
    }

    function isProfileUrl(value) {
      try {
        const url = new URL(value);
        const parts = url.pathname.split("/").filter(Boolean);

        return (
          url.hostname === "steamcommunity.com" &&
          ["profiles", "id"].includes(parts[0]) &&
          Boolean(parts[1])
        );
      } catch {
        return false;
      }
    }

    function flashValid() {
      input.classList.remove("valid-flash");
      void input.offsetWidth;
      input.classList.add("valid-flash");
    }

    function fillGroups(data) {
      groupFilter.innerHTML = "";
      const savedGroupId = localStorage.getItem(groupStorageKey) || "";

      const allOption = document.createElement("option");
      allOption.value = "";
      allOption.textContent = `Kaikki kaverit (${data.steamIds.length})`;
      groupFilter.appendChild(allOption);

      for (const group of data.groups) {
        const option = document.createElement("option");
        option.value = group.id;
        option.textContent = `${group.name} (${group.count})`;
        groupFilter.appendChild(option);
      }

      if ([...groupFilter.options].some((option) => option.value === savedGroupId)) {
        groupFilter.value = savedGroupId;
      }

      groupFilter.disabled = false;
    }

    function filteredRows(groupId) {
      const rows = [];

      for (let index = 0; index < currentData.steamIds.length; index += 1) {
        if (!groupId || currentData.friendGroups[index].includes(groupId)) {
          rows.push({
            date: currentData.dates[index],
            position: rows.length + 1,
            name: currentData.names[index],
            dateText: currentData.dateTexts[index],
            steamId: currentData.steamIds[index]
          });
        }
      }

      return rows;
    }

    function makeTrace(rows) {
      return {
        type: "scatter",
        mode: "markers+text",
        x: rows.map((row) => row.date),
        y: rows.map((row) => row.position),
        text: rows.map((row) => row.name),
        textposition: "middle right",
        textfont: {
          size: 11,
          color: "#222"
        },
        customdata: rows.map((row) => [row.dateText, row.steamId]),
        marker: {
          color: "#1b75d0",
          size: 9,
          opacity: 0.82
        },
        hovertemplate:
          "<b>%{text}</b><br>" +
          "Kaveruus alkoi: %{customdata[0]}<br>" +
          "SteamID: %{customdata[1]}" +
          "<extra></extra>"
      };
    }

    function renderChart() {
      const rows = filteredRows(groupFilter.value);
      const selectedText = groupFilter.options[groupFilter.selectedIndex].textContent;

      Plotly.react("chart", [makeTrace(rows)], {
        title: groupFilter.value
          ? `Steam-kaverit aikajanalla - ${selectedText}`
          : "Steam-kaverit aikajanalla",
        xaxis: { title: "Kaveruuden alkamispäivä" },
        yaxis: { title: "Kaverien kertymä" },
        margin: { l: 70, r: 30, t: 96, b: 90 },
        hovermode: "closest"
      }, config);
    }

    async function fetchTimeline(profileUrl) {
      lastRequestedUrl = profileUrl;
      groupFilter.disabled = true;
      showChartMessage("Haetaan dataa...");

      try {
        const response = await fetch("/api/timeline", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ profileUrl })
        });
        const payload = await response.json();

        if (!response.ok) {
          throw new Error(payload.error || "Steam-dataa ei voitu hakea.");
        }

        if (profileUrl !== lastRequestedUrl) {
          return;
        }

        currentData = payload;
        localStorage.setItem(profileStorageKey, profileUrl);
        flashValid();
        fillGroups(payload);
        renderChart();
      } catch (error) {
        groupFilter.disabled = true;
        showChartMessage(error.message, true);
      }
    }

    input.addEventListener("input", () => {
      const value = input.value.trim();
      window.clearTimeout(debounceTimer);

      if (!value) {
        showChartMessage("Syötä Steam-profiilin URL.");
        return;
      }

      if (!isProfileUrl(value)) {
        showChartMessage("Syötä validi Steam-profiilin URL.");
        return;
      }

      debounceTimer = window.setTimeout(() => fetchTimeline(value), 650);
    });

    groupFilter.addEventListener("change", () => {
      localStorage.setItem(groupStorageKey, groupFilter.value);
      renderChart();
    });

    const savedProfileUrl = localStorage.getItem(profileStorageKey);

    if (savedProfileUrl) {
      input.value = savedProfileUrl;
      fetchTimeline(savedProfileUrl);
    }
  </script>
</body>
</html>
"""


class SteamFriendsHandler(BaseHTTPRequestHandler):
    def send_json(self, status_code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path not in {"/rakkaatystavat", "/rakkaatystavat/index.html"}:
            self.send_error(404)
            return

        body = INDEX_HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/api/timeline":
            self.send_error(404)
            return

        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length)

        try:
            payload = json.loads(raw_body.decode("utf-8"))
            profile_url = payload.get("profileUrl", "")
            data = build_timeline(profile_url)
            self.send_json(200, data)
        except requests.HTTPError as error:
            if error.response is not None and error.response.status_code == 401:
                self.send_json(401, {
                    "error": "Steam ei palauttanut kaverilistaa. Tarkista, että profiili ja kaverilista ovat julkisia."
                })
            else:
                self.send_json(502, {"error": "Steam API -haku epäonnistui."})
        except Exception as error:
            self.send_json(400, {"error": str(error)})

    def log_message(self, format, *args):
        print("%s - %s" % (self.address_string(), format % args))


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8000), SteamFriendsHandler)
    print("SteamFriends käynnissä: http://127.0.0.1:8000")
    server.serve_forever()
