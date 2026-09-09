# Monday Brief

An automated weekly brief that runs entirely in the cloud. Every Monday at 09:00 UTC, GitHub Actions gathers data from cloud-reachable sources and produces a concise brief — no local computer required.

## The Six Answers

| # | Question | Answer |
|---|----------|--------|
| 1 | **Trigger** | GitHub Actions `schedule` cron — every Monday at 09:00 UTC |
| 2 | **Touch** | The workflow calls three cloud APIs (GitHub REST API, Open-Meteo weather, ZenQuotes) and compiles a Markdown brief |
| 3 | **Device independence** | GitHub Actions runs on GitHub's own servers. The workflow file, the cron schedule, the API calls, and the committed brief all exist in the cloud. Your PC can be off. |
| 4 | **Success signal (Tier 3)** | A file `briefs/YYYY-MM-DD.md` is committed to the repository with structured headers (`GENERATED_UTC`, `STATUS: SUCCESS`). Verifiable from any device via `gh` CLI or GitHub web UI. |
| 5 | **Autonomy** | Zero human intervention after initial setup. The cron fires, the script runs, data is gathered, the brief is committed, and the success signal is created — all automatically. |
| 6 | **Empty case** | If no GitHub activity exists for the week, the brief explicitly states "No commits · No pull requests · No issues" and still generates the full brief with weather, quote, and metadata. The success signal is still created. The brief is never truly empty. |

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    GitHub Actions (Cloud)                         │
│                                                                  │
│   ┌──────────────┐    Every Monday 09:00 UTC                     │
│   │  Cron Trigger │──────────────────┐                           │
│   └──────────────┘                   │                           │
│                                      ▼                           │
│                         ┌─────────────────────┐                  │
│                         │  generate-brief.sh  │                  │
│                         └─────────┬───────────┘                  │
│                                   │                              │
│                    ┌──────────────┼──────────────┐               │
│                    │              │              │               │
│                    ▼              ▼              ▼               │
│            ┌────────────┐ ┌────────────┐ ┌────────────┐         │
│            │   GitHub   │ │  Open-Meteo│ │  ZenQuotes │         │
│            │  REST API  │ │  Weather   │ │   Quote    │         │
│            └──────┬─────┘ └──────┬─────┘ └──────┬─────┘         │
│                   │              │              │               │
│                   └──────────────┼──────────────┘               │
│                                  ▼                               │
│                    ┌─────────────────────────┐                   │
│                    │  briefs/YYYY-MM-DD.md   │                   │
│                    │  (Committed to repo)    │                   │
│                    │  TIER 3 SUCCESS SIGNAL  │                   │
│                    └─────────────────────────┘                   │
└──────────────────────────────────────────────────────────────────┘
```

## Cloud Services Used

| Service | Purpose | Free Tier |
|---------|---------|-----------|
| **GitHub Actions** | Workflow orchestration and scheduling | 2,000 min/month (free tier) |
| **GitHub REST API** | Fetch user activity (commits, PRs, issues) | 5,000 req/hour |
| **Open-Meteo** | Weather data (no API key required) | 10,000 req/day |
| **ZenQuotes** | Daily inspirational quote | Free tier |

All services are cloud-reachable. No local resources are used.

## Why the Workflow Is Device-Independent

The workflow is device-independent because every component runs in the cloud:

1. **Scheduling**: GitHub Actions cron runs on GitHub's servers, not on your local machine
2. **Execution**: The workflow runs on GitHub-hosted Ubuntu runners
3. **Data sources**: All three APIs (GitHub, Open-Meteo, ZenQuotes) are cloud-hosted
4. **Storage**: The brief is committed to the GitHub repository (cloud storage)
5. **Verification**: You can verify runs from any device with `gh` CLI or a web browser

Your local computer is never involved in any part of the pipeline.

## How to Verify Scheduled Runs (Computer OFF)

After your computer is off, you can verify scheduled runs from any device:

```bash
# Check the latest workflow runs
gh run list --repo GiminiKhan/monday-brief --limit 5

# Check if today's brief exists
gh api repos/GiminiKhan/monday-brief/contents/briefs/$(date -u '+%Y-%m-%d') --jq '.name'

# Download and read the latest brief
gh api repos/GiminiKhan/monday-brief/contents/briefs --jq '.[-1].name' | \
  xargs -I{} gh api repos/GiminiKhan/monday-brief/contents/briefs/{} --jq '.content' | \
  base64 -d
```

Or visit: `https://github.com/GiminiKhan/monday-brief/tree/main/briefs`

## Manual Testing

To run the workflow manually:

```bash
# Trigger via GitHub Actions
gh workflow run "Generate Monday Brief" --repo GiminiKhan/monday-brief

# Watch the run
gh run watch --repo GiminiKhan/monday-brief
```

## Local Testing (Optional)

To test locally before pushing:

```bash
# Requires: git, curl, gh CLI authenticated
export GITHUB_TOKEN=$(gh auth token)
bash generate-brief.sh
```

## Tier 3 Success Signal

Every successful run creates a verifiable Tier 3 signal:

1. **Primary**: A file `briefs/YYYY-MM-DD.md` committed to the repository
2. **Secondary**: A GitHub Actions workflow run with status "completed"
3. **Tertiary**: A GitHub issue titled "✅ Brief generated: YYYY-MM-DD"

The primary signal (committed file) is the Tier 3 proof because:
- It exists independently of the workflow run
- It can be verified from any device
- It contains structured headers with timestamps
- It persists in the repository history

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Workflow not running | Check that the workflow file is on the default branch (`main`) |
| Permission denied | Ensure the repo has `Contents: Write` permission in Settings → Actions |
| Weather data missing | Check Open-Meteo API status at open-meteo.com |
| Quote not loading | ZenQuotes may be temporarily unavailable; the script falls back to a default quote |

## License

MIT
