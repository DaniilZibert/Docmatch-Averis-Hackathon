#!/usr/bin/env bash
# Install the repository's git hooks. Run once after cloning.
#
#   ./tools/install-hooks.sh
#
# .git/hooks is not part of a clone, so a hook that only lives there protects exactly
# one machine. The copies in tools/hooks are the source of truth; this puts them where
# git will run them.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
for hook in "$root"/tools/hooks/*; do
    name="$(basename "$hook")"
    install -m 755 "$hook" "$root/.git/hooks/$name"
    echo "  installed $name"
done
