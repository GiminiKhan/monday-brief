#!/usr/bin/env python3
"""
Monday Brief Generator — Fetches data from cloud-only sources.

Sources:
  1. GitHub REST API — user activity (commits, PRs, issues)
  2. Open-Meteo API — weather data (no API key required)
  3. ZenQuotes API — daily inspirational quote

Tier 3 success signal: briefs/YYYY-MM.md committed to repository.

Environment variables:
  GITHUB_TOKEN          — GitHub PAT with 'repo' scope (required)
  GITHUB_REPOSITORY     — owner/repo (set automatically in Actions)
  GITHUB_USER           — GitHub username (default: GiminiKhan)
  WEATHER_CITY          — City name (default: Islamabad)
  WEATHER_LAT           — Latitude (default: 33.6941)
  WEATHER_LON           — Longitude (default: 73.0479)
  BRIEF_TIMEZONE        — IANA timezone (default: Asia/Karachi)
"""

import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

# ─── Configuration ────────────────────────────────────────────────────

GITHUB_USER = os.environ.get("GITHUB_USER", "GiminiKhan")
WEATHER_CITY = os.environ.get("WEATHER_CITY", "Islamabad")
WEATHER_LAT = os.environ.get("WEATHER_LAT", "33.6941")
WEATHER_LON = os.environ.get("WEATHER_LON", "73.0479")
BRIEF_TIMEZONE = os.environ.get("BRIEF_TIMEZONE", "Asia/Karachi")
REPO = os.environ.get("GITHUB_REPOSITORY", f"{GITHUB_USER}/monday-brief")

# ─── Helpers ──────────────────────────────────────────────────────────


def log(msg):
    """Print to stderr for logging (doesn't capture in command substitution)."""
    print(msg, file=sys.stderr)


def fetch_json(url, token=None):
    """Fetch JSON from a URL with optional Bearer token."""
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, json.JSONDecodeError, Exception) as e:
        log(f"  Warning: Failed to fetch {url}: {e}")
        return None


def resolve_token():
    """Resolve GitHub token from env or gh CLI."""
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token

    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except FileNotFoundError:
        pass

    print("ERROR: No GitHub token found.", file=sys.stderr)
    print("  Set GITHUB_TOKEN env var, or run: gh auth login", file=sys.stderr)
    sys.exit(1)


# ─── WMO Weather Code Mapping ────────────────────────────────────────

WMO_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
}


def wind_direction_name(degrees):
    """Convert wind degrees to cardinal direction."""
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    idx = round(degrees / 22.5) % 16
    return dirs[idx]


# ─── GitHub Activity ──────────────────────────────────────────────────


def fetch_github_activity(token):
    """Fetch GitHub activity for the past 7 days."""
    since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    sections = []
    has_activity = False

    # Events (commits, etc.)
    log("  Fetching GitHub events...")
    events = fetch_json(
        f"https://api.github.com/users/{GITHUB_USER}/events/public?per_page=100",
        token
    )
    if events:
        push_count = sum(1 for e in events if e.get("type") == "PushEvent")
        pr_count = sum(1 for e in events if e.get("type") == "PullRequestEvent")
        issue_count = sum(1 for e in events if e.get("type") == "IssuesEvent")
        review_count = sum(1 for e in events if e.get("type") == "PullRequestReviewEvent")

        if push_count:
            sections.append(f"### Commits\n- **{push_count} push event(s)** to public repositories in the past week\n")
            has_activity = True
        if pr_count:
            sections.append(f"### Pull Requests\n- **{pr_count} PR event(s)** in the past week\n")
            has_activity = True
        if issue_count:
            sections.append(f"### Issues\n- **{issue_count} issue event(s)** in the past week\n")
            has_activity = True
        if review_count:
            sections.append(f"### Reviews\n- **{review_count} PR review(s)** in the past week\n")
            has_activity = True

    # Search for PRs created this week
    log("  Searching for recent PRs...")
    prs = fetch_json(
        f"https://api.github.com/search/issues?q=author:{GITHUB_USER}+type:pr+created:>={since}&sort=created&order=desc&per_page=5",
        token
    )
    if prs and prs.get("total_count", 0) > 0:
        count = prs["total_count"]
        sections.append(f"### Pull Requests Created\n- **{count} PR(s)** created since {since}\n")
        for item in prs.get("items", [])[:5]:
            title = item.get("title", "Untitled")
            repo_url = item.get("repository_url", "")
            repo_name = repo_url.split("/")[-1] if repo_url else "unknown"
            sections.append(f"  - [{title}](https://github.com/{GITHUB_USER}/{repo_name}/pull/{item.get('number', '?')})")
        sections.append("")
        has_activity = True

    # Search for issues created this week
    log("  Searching for recent issues...")
    issues = fetch_json(
        f"https://api.github.com/search/issues?q=author:{GITHUB_USER}+type:issue+created:>={since}&sort=created&order=desc&per_page=5",
        token
    )
    if issues and issues.get("total_count", 0) > 0:
        count = issues["total_count"]
        sections.append(f"### Issues Created\n- **{count} issue(s)** created since {since}\n")
        for item in issues.get("items", [])[:5]:
            title = item.get("title", "Untitled")
            sections.append(f"  - {title}")
        sections.append("")
        has_activity = True

    if not has_activity:
        return (
            "No commits · No pull requests · No issues in the past 7 days.\n\n"
            "_This is normal — rest days are productive too._"
        )

    return "\n".join(sections)


# ─── Weather ──────────────────────────────────────────────────────────


def fetch_weather():
    """Fetch current weather from Open-Meteo (no API key required)."""
    log("  Fetching weather data...")
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={WEATHER_LAT}&longitude={WEATHER_LON}"
        f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,"
        f"weather_code,wind_speed_10m,wind_direction_10m"
        f"&timezone={BRIEF_TIMEZONE}"
    )
    data = fetch_json(url)
    if not data or "current" not in data:
        return f"| {WEATHER_CITY} | Data unavailable | — | — | — |"

    cur = data["current"]
    temp = cur.get("temperature_2m", "?")
    feels = cur.get("apparent_temperature", "?")
    humidity = cur.get("relative_humidity_2m", "?")
    wind_speed = cur.get("wind_speed_10m", "?")
    wind_dir = cur.get("wind_direction_10m", 0)
    code = cur.get("weather_code", -1)

    desc = WMO_CODES.get(code, f"Code {code}")
    cardinal = wind_direction_name(wind_dir) if isinstance(wind_dir, (int, float)) else "?"

    return (
        f"| {WEATHER_CITY} "
        f"| {temp}°C (feels like {feels}°C) "
        f"| {desc} "
        f"| {humidity}% "
        f"| {wind_speed} km/h {cardinal} |"
    )


# ─── Quote ────────────────────────────────────────────────────────────

FALLBACK_QUOTE = (
    '"The best time to plant a tree was 20 years ago. '
    'The second best time is now." — Chinese Proverb'
)


def fetch_quote():
    """Fetch daily inspirational quote from ZenQuotes."""
    log("  Fetching daily quote...")
    data = fetch_json("https://zenquotes.io/api/today")
    if data and isinstance(data, list) and len(data) > 0:
        q = data[0].get("q", "")
        a = data[0].get("a", "Unknown")
        if q:
            return f'"{q}" — {a}'
    return FALLBACK_QUOTE


# ─── Generate Brief ───────────────────────────────────────────────────


def generate_brief(token):
    """Generate the full Markdown brief."""
    now_utc = datetime.now(timezone.utc)
    today = now_utc.strftime("%Y-%m-%d")

    # Local date for display
    try:
        import zoneinfo
        local_tz = zoneinfo.ZoneInfo(BRIEF_TIMEZONE)
    except ImportError:
        # Fallback: just use UTC
        local_tz = timezone.utc

    local_now = now_utc.astimezone(local_tz)
    local_date = local_now.strftime("%A, %B %d, %Y")

    # Fetch all data
    log("\nFetching GitHub activity...")
    github_section = fetch_github_activity(token)

    log("\nFetching weather...")
    weather_row = fetch_weather()

    log("\nFetching quote...")
    quote_text = fetch_quote()

    # Build brief
    brief = f"""<!-- @monday-brief v1 -->
<!-- GENERATED_UTC: {now_utc.strftime('%Y-%m-%dT%H:%M:%SZ')} -->
<!-- STATUS: SUCCESS -->
<!-- REPO: {REPO} -->

# Monday Brief — {local_date}

_Generated automatically on {now_utc.strftime('%Y-%m-%dT%H:%M:%SZ')}_

---

## GitHub Activity

{github_section}

---

## Weather

| Location | Temperature | Condition | Humidity | Wind |
|----------|-------------|-----------|----------|------|
{weather_row}

_Source: Open-Meteo (open-meteo.com)_

---

## Daily Quote

> {quote_text}

_Source: ZenQuotes (zenquotes.io)_

---

## Metadata

- **Generated**: {now_utc.strftime('%Y-%m-%dT%H:%M:%SZ')}
- **Timezone**: {BRIEF_TIMEZONE}
- **Weather city**: {WEATHER_CITY}
- **Tier 3 success signal**: This file (committed to repository)
- **Workflow run**: {os.environ.get('GITHUB_RUN_ID', 'local')}
- **Status**: SUCCESS
"""
    return brief, today


# ─── Commit to Repository ─────────────────────────────────────────────


def commit_brief(brief, today, token):
    """Commit the brief to the repository."""
    log("\nCommitting brief to repository...")

    # Write brief file
    brief_path = f"briefs/{today}.md"
    os.makedirs("briefs", exist_ok=True)

    with open(brief_path, "w", encoding="utf-8") as f:
        f.write(brief)

    # Configure git
    subprocess.run(["git", "config", "user.name", "Monday Brief Bot"], check=True)
    subprocess.run(
        ["git", "config", "user.email", "monday-brief-bot@users.noreply.github.com"],
        check=True
    )

    # Set up auth for push
    if os.environ.get("GITHUB_ACTIONS"):
        # In GitHub Actions: use token in remote URL
        remote_url = f"https://x-access-token:{token}@github.com/{REPO}.git"
        subprocess.run(["git", "remote", "set-url", "origin", remote_url], check=True)
    else:
        # Local: try gh auth setup-git
        try:
            subprocess.run(["gh", "auth", "setup-git"], capture_output=True, timeout=10)
        except FileNotFoundError:
            pass

    # Ensure we're on the right branch
    for branch in ["main", "master"]:
        result = subprocess.run(
            ["git", "checkout", branch],
            capture_output=True, timeout=5
        )
        if result.returncode == 0:
            break

    # Stage and commit
    subprocess.run(["git", "add", brief_path], check=True)

    # Check if there are changes to commit
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        capture_output=True, timeout=5
    )
    if result.returncode == 0:
        log(f"  Brief already committed for {today}. No changes.")
        return True

    commit_msg = (
        f"chore: generate Monday brief for {today}\n\n"
        f"Automated brief generation.\n"
        f"Tier 3 success signal: {brief_path}\n"
        f"Generated at: {now_utc_str()}"
    )
    subprocess.run(["git", "commit", "-m", commit_msg], check=True)

    # Push
    result = subprocess.run(
        ["git", "push", "origin", "HEAD"],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        log(f"  WARNING: Push failed: {result.stderr}")
        log(f"  Brief committed locally at {brief_path}")
        return True

    log("")
    log("=" * 50)
    log("  TIER 3 SUCCESS SIGNAL CREATED")
    log(f"  File: {brief_path}")
    log(f"  Repo: {REPO}")
    log(f"  Verify: gh api repos/{REPO}/contents/{brief_path}")
    log(f"  Or visit: https://github.com/{REPO}/blob/main/{brief_path}")
    log("=" * 50)

    return True


def now_utc_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ─── Main ─────────────────────────────────────────────────────────────


def main():
    log("=== Monday Brief Generator ===")
    log(f"Repository: {REPO}")
    log(f"Weather: {WEATHER_CITY}")
    log("")

    token = resolve_token()
    brief, today = generate_brief(token)
    commit_brief(brief, today, token)

    log("\nDone.")


if __name__ == "__main__":
    main()
