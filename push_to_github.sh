#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd "$(dirname "$0")" && pwd)"
cd "$repo_dir"
if [ ! -d .git ]; then
  git init -b main
fi
git add -A
git commit -m "chore: import HA-ready Paw Control (Silver-safe, Gold-ready, CI & tests)"
git remote remove origin 2>/dev/null || true
git remote add origin git@github.com:Bigdaddy1990/pawcontrol.git
git push -u origin main
echo "Pushed to https://github.com/Bigdaddy1990/pawcontrol (branch: main)"
