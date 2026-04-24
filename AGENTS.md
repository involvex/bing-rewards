# Bing Rewards Agent Guide

## Development Setup
- Install uv: `pip install uv` or via package manager
- Setup: `uv run pre-commit install --install-hooks`
- Verify: `uv run bing-rewards --help`

## Key Commands
- Run searches: `uv run bing-rewards [options]`
- Lint: `uv run ruff check`
- Format: `uv run ruff format --check`
- Dry run (test): `uv run bing-rewards --dryrun`

## Important Notes
- Config: `%APPDATA%\bing-rewards\config.json` (Windows) or `$XDG_CONFIG_HOME/bing-rewards/config.json`
- Requires Chrome/Chromium in PATH or use `--exe <path>`
- Must be logged into bing.com at least once
- No other Chrome instances should run during execution
- Press ESC to exit early during search
- `--profile` accepts multiple values for sequential runs
- Mobile/desktop modes: `--mobile`, `--desktop`, or neither for both

## Project Structure
- Main entry: `bing_rewards.app:main`
- Core logic: `bing_rewards/app.py`
- Config/args: `bing_rewards/options.py`
- Keywords: `bing_rewards/data/keywords.txt`

## CI/CD
- Linting: GitHub Actions runs ruff on PRs to master
- Release: Push to master triggers automated release via release-please