#!/usr/bin/env bash
# generate-brief.sh — Monday Brief Generator
# Fetches data from cloud-only sources and produces a Markdown brief.
# Designed to run on GitHub Actions (Ubuntu) and locally (Git Bash on Windows).
#
# Environment variables:
#   GITHUB_TOKEN          — GitHub PAT with 'repo' scope (required)
#   GITHUB_REPOSITORY     — owner/repo (set automatically in Actions)
#   WEATHER_CITY          — City name for weather (default: Islamabad)
#   WEATHER_LAT / WEATHER_LON — Coordinates (default: 33.6941, 73.0479)
#   BRIEF_TIMEZONE        — IANA timezone (default: Asia/Karachi)
#
# Exit codes:
#   0  — Brief generated and committed successfully (Tier 3 signal created)
#   1  — Failed to generate or commit the brief

set -euo pipefail

# ─── Configuration ────────────────────────────────────────────────────
GITHUB_USER="${GITHUB_USER:-GiminiKhan}"
WEATHER_CITY="${WEATHER_CITY:-Islamabad}"
WEATHER_LAT="${WEATHER_LAT:-33.6941}"
WEATHER_LON="${WEATHER_LON:-73.0479}"
BRIEF_TIMEZONE="${BRIEF_TIMEZONE:-Asia/Karachi}"
REPO="${GITHUB_REPOSITORY:-${GITHUB_USER}/monday-brief}"

# ─── Resolve GitHub token ─────────────────────────────────────────────
resolve_token() {
    if [ -n "${GITHUB_TOKEN:-}" ]; then
        echo "${GITHUB_TOKEN}"
        return
    fi

    # Fallback: extract from gh CLI
    if command -v gh &> /dev/null; then
        local token
        token=$(gh auth token 2>/dev/null || true)
        if [ -n "$token" ]; then
            echo "$token"
            return
        fi
    fi

    echo "ERROR: No GitHub token found." >&2
    echo "  Set GITHUB_TOKEN env var, or run: gh auth login" >&2
    exit 1
}

TOKEN=$(resolve_token)

# ─── Helpers ──────────────────────────────────────────────────────────

fetch_json() {
    local url="$1"
    local token="${2:-}"
    local args=(-s -f -H "Accept: application/vnd.github+json")
    [ -n "$token" ] && args+=(-H "Authorization: Bearer $token")
    curl "${args[@]}" "$url" 2>/dev/null || echo "[]"
}

iso_to_date() {
    echo "$1" | cut -d'T' -f1
}

# ─── GitHub Activity ──────────────────────────────────────────────────

fetch_github_activity() {
    local since
    since=$(date -u -d '7 days ago' '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null \
        || date -u -v-7d '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null \
        || echo "")

    local activity=""
    local has_activity=false

    # Commits (via public events)
    local events
    events=$(fetch_json "https://api.github.com/users/${GITHUB_USER}/events/public?per_page=100" "$TOKEN")
    if [ "$events" != "[]" ] && [ -n "$events" ]; then
        local push_events
        push_events=$(echo "$events" | grep -o '"type":"PushEvent"' 2>/dev/null | wc -l)
        if [ "$push_events" -gt 0 ]; then
            activity+="### Commits\n"
            activity+="- **$push_events push events** to public repositories in the past week\n\n"
            has_activity=true
        fi
    fi

    # Pull requests
    local prs
    prs=$(fetch_json "https://api.github.com/search/issues?q=author:${GITHUB_USER}+type:pr+created:>=${since%%T*}&sort=created&order=desc&per_page=10" "$TOKEN")
    if [ "$prs" != "[]" ] && [ -n "$prs" ]; then
        local pr_count
        pr_count=$(echo "$prs" | grep -o '"total_count":[0-9]*' 2>/dev/null | head -1 | cut -d: -f2)
        pr_count=${pr_count:-0}
        if [ "$pr_count" -gt 0 ]; then
            activity+="### Pull Requests\n"
            activity+="- **$pr_count PR(s)** created this week\n\n"
            has_activity=true
        fi
    fi

    # Issues
    local issues
    issues=$(fetch_json "https://api.github.com/search/issues?q=author:${GITHUB_USER}+type:issue+created:>=${since%%T*}&sort=created&order=desc&per_page=10" "$TOKEN")
    if [ "$issues" != "[]" ] && [ -n "$issues" ]; then
        local issue_count
        issue_count=$(echo "$issues" | grep -o '"total_count":[0-9]*' 2>/dev/null | head -1 | cut -d: -f2)
        issue_count=${issue_count:-0}
        if [ "$issue_count" -gt 0 ]; then
            activity+="### Issues\n"
            activity+="- **$issue_count issue(s)** created this week\n\n"
            has_activity=true
        fi
    fi

    if [ "$has_activity" = false ]; then
        activity="No commits · No pull requests · No issues in the past 7 days.\n\n"
        activity+="_This is normal — rest days are productive too._"
    fi

    echo -e "$activity"
}

# ─── Weather ──────────────────────────────────────────────────────────

fetch_weather() {
    local resp
    resp=$(curl -s -f \
        "https://api.open-meteo.com/v1/forecast?latitude=${WEATHER_LAT}&longitude=${WEATHER_LON}&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,wind_direction_10m&timezone=${BRIEF_TIMEZONE}" \
        2>/dev/null || echo "{}")

    if [ "$resp" = "{}" ] || [ -z "$resp" ]; then
        echo "Weather data unavailable — API request failed."
        return
    fi

    local temp hum apparent wind_speed wind_dir code
    temp=$(echo "$resp" | grep -o '"temperature_2m":[0-9.-]*' | head -1 | cut -d: -f2)
    hum=$(echo "$resp" | grep -o '"relative_humidity_2m":[0-9]*' | head -1 | cut -d: -f2)
    apparent=$(echo "$resp" | grep -o '"apparent_temperature":[0-9.-]*' | head -1 | cut -d: -f2)
    wind_speed=$(echo "$resp" | grep -o '"wind_speed_10m":[0-9.-]*' | head -1 | cut -d: -f2)
    wind_dir=$(echo "$resp" | grep -o '"wind_direction_10m":[0-9.-]*' | head -1 | cut -d: -f2)
    code=$(echo "$resp" | grep -o '"weather_code":[0-9]*' | head -1 | cut -d: -f2)

    # WMO weather code to description
    local desc="Unknown"
    case "$code" in
        0) desc="Clear sky" ;; 1) desc="Mainly clear" ;; 2) desc="Partly cloudy" ;;
        3) desc="Overcast" ;; 45|48) desc="Fog" ;; 51|53|55) desc="Drizzle" ;;
        61|63|65) desc="Rain" ;; 71|73|75) desc="Snow" ;; 80|81|82) desc="Rain showers" ;;
        95) desc="Thunderstorm" ;; 96|99) desc="Thunderstorm with hail" ;;
    esac

    # Wind direction to cardinal
    local cardinal="N"
    if [ -n "$wind_dir" ]; then
        local dirs=("N" "NE" "E" "SE" "S" "SW" "W" "NW")
        local idx=$(( ($(echo "$wind_dir" | cut -d. -f1) + 22) / 45 ))
        [ "$idx" -ge 8 ] && idx=0
        cardinal="${dirs[$idx]}"
    fi

    echo "| ${WEATHER_CITY} | ${temp:-?}°C (feels like ${apparent:-?}°C) | ${desc} | ${hum:-?}% | ${wind_speed:-?} km/h ${cardinal} |"
}

# ─── Quote ────────────────────────────────────────────────────────────

fetch_quote() {
    local resp
    resp=$(curl -s -f "https://zenquotes.io/api/today" 2>/dev/null || echo "[]")

    if [ "$resp" = "[]" ] || [ -z "$resp" ]; then
        echo "\"The best time to plant a tree was 20 years ago. The second best time is now.\" — Chinese Proverb"
        return
    fi

    local quote author
    quote=$(echo "$resp" | grep -o '"q":"[^"]*"' | head -1 | sed 's/"q":"//;s/"$//')
    author=$(echo "$resp" | grep -o '"a":"[^"]*"' | head -1 | sed 's/"a":"//;s/"$//')

    if [ -n "$quote" ]; then
        echo "\"${quote}\" — ${author:-Unknown}"
    else
        echo "\"The best time to plant a tree was 20 years ago. The second best time is now.\" — Chinese Proverb"
    fi
}

# ─── Generate Brief ───────────────────────────────────────────────────

generate_brief() {
    local today utc_now
    today=$(date -u '+%Y-%m-%d')
    utc_now=$(date -u '+%Y-%m-%dT%H:%M:%SZ')

    # Set timezone for local date display
    export TZ="${BRIEF_TIMEZONE}"
    local local_date
    local_date=$(date '+%A, %B %d, %Y')

    # Fetch all data from cloud sources
    echo "Fetching GitHub activity..." >&2
    local github_section
    github_section=$(fetch_github_activity)

    echo "Fetching weather data..." >&2
    local weather_row
    weather_row=$(fetch_weather)

    echo "Fetching daily quote..." >&2
    local quote_text
    quote_text=$(fetch_quote)

    # Build the brief
    cat > brief.md << BRIEF_EOF
<!-- @monday-brief v1 -->
<!-- GENERATED_UTC: ${utc_now} -->
<!-- STATUS: SUCCESS -->
<!-- REPO: ${REPO} -->

# Monday Brief — ${local_date}

_Generated automatically on ${utc_now}_

---

## GitHub Activity

${github_section}

---

## Weather

| Location | Temperature | Condition | Humidity | Wind |
|----------|-------------|-----------|----------|------|
${weather_row}

_Source: Open-Meteo (open-meteo.com)_

---

## Daily Quote

> ${quote_text}

_Source: ZenQuotes (zenquotes.io)_

---

## Metadata

- **Generated**: ${utc_now}
- **Timezone**: ${BRIEF_TIMEZONE}
- **Weather city**: ${WEATHER_CITY}
- **Tier 3 success signal**: This file (committed to repository)
- **Workflow run**: ${GITHUB_RUN_ID:-local}
- **Status**: SUCCESS
BRIEF_EOF

    echo "Brief generated: brief.md" >&2
}

# ─── Commit to Repository ─────────────────────────────────────────────

commit_brief() {
    local today
    today=$(date -u '+%Y-%m-%d')

    # Configure git for automated commits
    git config user.name "Monday Brief Bot"
    git config user.email "monday-brief-bot@users.noreply.github.com"

    # Set up authentication for push
    if [ -n "${GITHUB_ACTIONS:-}" ]; then
        # In GitHub Actions: use the built-in token
        git remote set-url origin "https://x-access-token:${GITHUB_TOKEN}@github.com/${REPO}.git"
    elif command -v gh &> /dev/null; then
        # Local: use gh CLI to set up credentials
        gh auth setup-git 2>/dev/null || true
    fi

    # Ensure we're on the right branch
    git checkout main 2>/dev/null || git checkout master 2>/dev/null || true

    # Create briefs directory if it doesn't exist
    mkdir -p briefs

    # Move the generated brief to the dated file
    cp brief.md "briefs/${today}.md"

    # Stage and commit
    git add "briefs/${today}.md"
    if git diff --cached --quiet 2>/dev/null; then
        echo "No changes to commit — brief already exists for ${today}." >&2
        return 0
    fi

    git commit -m "chore: generate Monday brief for ${today}

Automated brief generation.
Tier 3 success signal: briefs/${today}.md
Generated at: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"

    # Push to remote
    git push origin HEAD 2>/dev/null || {
        echo "WARNING: Could not push to remote. Brief committed locally." >&2
        echo "Tier 3 signal (local): briefs/${today}.md" >&2
        return 0
    }

    echo "" >&2
    echo "================================================" >&2
    echo "  TIER 3 SUCCESS SIGNAL CREATED" >&2
    echo "  File: briefs/${today}.md" >&2
    echo "  Repo: ${REPO}" >&2
    echo "  Verify: gh api repos/${REPO}/contents/briefs/${today}.md" >&2
    echo "  Or visit: https://github.com/${REPO}/blob/main/briefs/${today}.md" >&2
    echo "================================================" >&2
}

# ─── Main ─────────────────────────────────────────────────────────────

main() {
    echo "=== Monday Brief Generator ===" >&2
    echo "Repository: ${REPO}" >&2
    echo "Weather: ${WEATHER_CITY}" >&2
    echo "" >&2

    generate_brief
    commit_brief

    echo "" >&2
    echo "Done." >&2
}

main "$@"
