# Deploy the personal snapshot feed (GitHub Pages)

This replaces the AWS stack for a single-user setup. GitHub Actions collects public GCX advertised discounts once a day and publishes `snapshot.json` to GitHub Pages. The Safari extension loads that HTTPS URL once per session.

**Requirement:** the feed URL must be publicly readable (the extension fetches without login). Use a **public** repo, or a private repo with Pages enabled on a paid plan that can still serve the site publicly.

GCX terms still apply to republication. This is a personal feed of advertised catalog maxima, not a product redistribution service.

## 1. One-time: fix GitHub CLI auth (this Mac)

```bash
gh auth refresh -h github.com
gh auth status
```

## 2. Create the GitHub repo and push

From the project root:

```bash
cd /Users/kmccraney/Documents/Codex/2026-10-24/do-i/outputs/giftcard-discounts

# If .git is not initialized yet:
git init
git add -A
git status   # confirm .venv/ and build/ are not staged
git commit -m "$(cat <<'EOF'
Initial giftcard-discounts tree with GitHub Pages publish workflow.

EOF
)"

gh repo create giftcard-discounts --public --source=. --remote=origin --push
```

Use another name if `giftcard-discounts` is taken. Keep the repo **public** so Safari can fetch the snapshot without credentials.

## 3. Enable GitHub Pages (Actions source)

In the GitHub UI:

1. Repo → **Settings** → **Pages**
2. **Build and deployment** → Source: **GitHub Actions**
3. Save if prompted

No `docs/` folder or `gh-pages` branch is required; the workflow uploads an artifact.

## 4. Run the first publish

```bash
gh workflow run pages.yml
gh run watch
```

Or: **Actions** → **Publish snapshot** → **Run workflow**.

When it succeeds, open:

`https://<your-github-username>.github.io/giftcard-discounts/`

The page shows the absolute feed URL, typically:

`https://<your-github-username>.github.io/giftcard-discounts/snapshot.json`

## 5. Point the Safari extension at the feed

1. Open the Gift Card Discounts app / extension popup
2. Leave **synthetic demo data** unchecked
3. Paste the `snapshot.json` HTTPS URL
4. Save / refresh
5. Visit a mapped retailer (e.g. `https://www.dominos.com`) over HTTPS

Only advertised discounts **strictly greater than 1%** show a pill. Labels remain before-fees.

## 6. Cadence and manual refresh

- Schedule: daily at `15:17` UTC (see `.github/workflows/pages.yml`)
- Manual: `gh workflow run pages.yml`
- Local dry-run (writes `site/` but does not deploy):

```bash
python3 -m venv .venv && source .venv/bin/activate
bash scripts/build-site.sh
# inspect site/snapshot.json
```

If a scheduled collect fails (markup drift, rate limit, missing retailer), the workflow fails and **does not** replace the current Pages deployment.

## Configuration cheat sheet

| Item | Where |
| --- | --- |
| Retailers / domains / GCX paths | `config/retailers-live.json` |
| Collect + Pages build | `scripts/build-site.sh` |
| Schedule / deploy | `.github/workflows/pages.yml` |
| Landing copy | `site-src/index.html` |
| Unit tests CI | `.github/workflows/tests.yml` |
| AWS templates (unused for this path) | `infra/` — keep for reference; not required |

## Optional hardening later

- Make the repo private only if your GitHub plan can still publish a public Pages site the extension can fetch anonymously
- Narrow extension host permissions once the snapshot host is fixed
- Add a second workflow job that notifies you (email/Slack) when publish fails
