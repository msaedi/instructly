#!/bin/bash
# investigate-github-repos.sh
# Run this from your local terminal (not the sandbox) to investigate
# unknown repos on your GitHub account.
#
# Prerequisites: gh CLI authenticated (gh auth status)

set -euo pipefail

OUTPUT_FILE="github-repo-audit-$(date +%Y%m%d).md"

echo "# GitHub Repository Audit" > "$OUTPUT_FILE"
echo "*Generated: $(date)*" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

# 1. List all repos sorted by creation date
echo "## All Repositories (newest first)" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"
echo "| Name | Created | Private | Fork | Description |" >> "$OUTPUT_FILE"
echo "|------|---------|---------|------|-------------|" >> "$OUTPUT_FILE"

gh repo list --json name,createdAt,isPrivate,isFork,description --limit 200 \
  --jq 'sort_by(.createdAt) | reverse | .[] | "| \(.name) | \(.createdAt[:10]) | \(.isPrivate) | \(.isFork) | \(.description // "—") |"' \
  >> "$OUTPUT_FILE"

echo "" >> "$OUTPUT_FILE"

# 2. Repos created in the last 90 days (most likely to be unexpected)
echo "## Repos Created in Last 90 Days" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

NINETY_DAYS_AGO=$(date -v-90d +%Y-%m-%d 2>/dev/null || date -d "90 days ago" +%Y-%m-%d)

gh api /user/repos --paginate \
  --jq ".[] | select(.created_at > \"${NINETY_DAYS_AGO}\") | \"- **\(.name)** created \(.created_at[:10]) | private=\(.private) fork=\(.fork) | \(.description // \"no description\")\"" \
  >> "$OUTPUT_FILE"

echo "" >> "$OUTPUT_FILE"

# 3. Forked repos (often created automatically by bots/tools)
echo "## Forked Repos (may be auto-created)" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

gh repo list --fork --json name,createdAt,parent --limit 100 \
  --jq '.[] | "- **\(.name)** forked \(.createdAt[:10]) from \(.parent.nameWithOwner // "unknown")"' \
  >> "$OUTPUT_FILE"

echo "" >> "$OUTPUT_FILE"

# 4. OAuth apps with repo access
echo "## Authorized OAuth Apps" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"
echo "Check these URLs in your browser:" >> "$OUTPUT_FILE"
echo "- https://github.com/settings/applications (Authorized OAuth Apps)" >> "$OUTPUT_FILE"
echo "- https://github.com/settings/installations (Installed GitHub Apps)" >> "$OUTPUT_FILE"
echo "- https://github.com/settings/tokens (Personal Access Tokens)" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"
echo "Any app with 'repo' scope can create repositories on your behalf." >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

# 5. Common culprits
echo "## Common Causes of Unknown Repos" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"
echo "1. **Dependabot** — creates forks for PRs on repos you contribute to" >> "$OUTPUT_FILE"
echo "2. **Vercel** — may create repos when importing projects" >> "$OUTPUT_FILE"
echo "3. **Render** — can create repos for blueprint deploys" >> "$OUTPUT_FILE"
echo "4. **GitHub Codespaces** — creates repos for dev containers" >> "$OUTPUT_FILE"
echo "5. **Template repos** — 'Use this template' creates new repos" >> "$OUTPUT_FILE"
echo "6. **GitHub Classroom** — auto-creates assignment repos" >> "$OUTPUT_FILE"
echo "7. **n8n / automation tools** — if granted repo scope" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

echo "Audit saved to: $OUTPUT_FILE"
echo "Review the file, then delete any repos you don't recognize:"
echo "  gh repo delete OWNER/REPO --yes"
