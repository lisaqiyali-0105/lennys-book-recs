#!/bin/bash
# Lenny's Archive — cron-safe update wrapper
# Sets up the environment before running the Python updater

# Load user environment (picks up PATH, ANTHROPIC_API_KEY, etc.)
source ~/.zshrc 2>/dev/null || source ~/.bash_profile 2>/dev/null || true

# Homebrew + pyenv paths often missing in cron
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

# Run the updater
python3 "$(dirname "$0")/update-books.py" 2>&1
