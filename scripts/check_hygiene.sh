#!/usr/bin/env bash
# Fails if the repository contains real employer or client names, credentials or private keys.
# Run by CI on every push. The synthetic data room must stay synthetic.
set -euo pipefail
cd "$(dirname "$0")/.."

files=$(git ls-files | grep -vE '^scripts/check_hygiene\.sh$|package-lock\.json$|\.(pdf|xlsx|png|gif)$')

fail=0
check() {
  local label=$1 pattern=$2
  if matches=$(echo "$files" | xargs grep -nIE -- "$pattern" 2>/dev/null); then
    echo "::error::$label found:"
    echo "$matches"
    fail=1
  fi
}

# Real organisations: employers, banks, funds and recruiters must never appear.
check "real organisation name" '\b(LGT|Credit Suisse|UBS|BNP|Paribas|Orbis|Mubadala|ADIA|ADQ|Julius B[aä]r|Pictet|Lombard Odier)\b'
# Credentials and keys.
check "private key" '-----BEGIN ([A-Z]+ )?PRIVATE KEY-----'
check "OpenAI-style API key" 'sk-[A-Za-z0-9_-]{20,}'
check "Azure storage key" 'AccountKey=[A-Za-z0-9+/=]{40,}'
check "AWS access key" 'AKIA[0-9A-Z]{16}'
check "GitHub token" 'gh[pousr]_[A-Za-z0-9]{36,}'

# PDFs: check the extracted text too.
for f in $(git ls-files 'data/dataroom/files/*.pdf'); do
  if pdftotext -q "$f" - 2>/dev/null | grep -qE '\b(LGT|Credit Suisse|UBS|BNP|Orbis)\b'; then
    echo "::error::real organisation name in $f"
    fail=1
  fi
done

if [ "$fail" -eq 0 ]; then
  echo "hygiene check passed: no real organisations, credentials or keys"
fi
exit "$fail"
