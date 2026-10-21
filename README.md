# ETF Elite v2 — mobile PWA + daily ETF ranking

## What this version does
- Mobile-friendly webpage reads `data/results.json`.
- GitHub Actions scheduled job (weekdays 16:20 China time) runs Python + AKShare and calculates a daily heuristic ranking.
- Candidate ETF codes are configured in `config/watchlist.txt`.
- Logs data freshness and failed symbols; if no data is available, workflow fails instead of pretending signals are valid.
- Manual paper-trade log remains local to the phone browser.

## Important limitations
- AKShare is a community data interface wrapper around public Eastmoney pages/endpoints, not a guaranteed official API or SLA. It may break, throttle, or return delayed/stale data.
- Daily historical bars are not intraday real-time quotes. The scheduled workflow is a daily update only.
- Rankings are heuristics and are not a promise of profit. Check liquidity, tracking error, spread, fees, and the contest's allowed ETF universe.
- This does not connect to, log into, or submit orders to the contest account.
- Do not add account passwords, cookies, API tokens, or other secrets to the public repository.

## Upload to the existing GitHub repository
1. Download and unzip the package.
2. Upload/replace all files at the repository root, including hidden `.github/workflows/daily_etf.yml` and `scripts/update_rankings.py`. GitHub's browser upload may not show hidden folders easily; if so, create the workflow file using Add file → Create new file with path `.github/workflows/daily_etf.yml`, and create the script using `scripts/update_rankings.py`, or upload using GitHub Desktop/PC.
3. Keep GitHub Pages publishing from `main` / root (as currently configured).
4. Open repository Settings → Actions → General. Under Workflow permissions, allow read and write permissions, then Save. This is needed for the scheduled workflow to commit `data/results.json`.
5. Open Actions tab → Daily ETF ranking → Run workflow to test manually.
6. Wait for the run to finish. If successful, `data/results.json` updates and the workflow commits the file. Refresh the Pages site.
7. Check `Actions` logs if the run fails. Do not trust stale data: the page displays the latest data date and status.

## Candidate universe
Edit `config/watchlist.txt` and include only codes available in the contest's actual ETF list. The sample list is illustrative and should be verified before use.

## Data source documentation
AKShare ETF historical quote docs: https://github.com/akfamily/akshare/blob/main/docs/data/fund/fund_public.md
