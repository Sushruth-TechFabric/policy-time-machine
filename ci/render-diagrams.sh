#!/usr/bin/env bash
# Renders every docs/diagrams/*.mmd with mermaid-cli. A diagram that fails to
# render fails the build — same policy as chip execution and generator
# validation (04-implementation-plan.md §5 P7).
#
# Also asserts that each .mmd's source is embedded verbatim in a spec document,
# so the reviewable copy in the markdown can never disagree with the file.
set -euo pipefail
cd "$(dirname "$0")/.."

shopt -s nullglob
diagrams=(docs/diagrams/*.mmd)
if [ ${#diagrams[@]} -eq 0 ]; then
  echo "No diagrams found under docs/diagrams/" >&2
  exit 1
fi

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT
printf '{"args":["--no-sandbox"]}' > "$workdir/puppeteer.json"

status=0
for f in "${diagrams[@]}"; do
  if output=$(npx --yes @mermaid-js/mermaid-cli \
      --puppeteerConfigFile "$workdir/puppeteer.json" \
      -i "$f" -o "$workdir/$(basename "$f" .mmd).svg" 2>&1); then
    echo "render OK      $f"
  else
    echo "render FAILED  $f"
    echo "$output"
    status=1
  fi
done

python3 - "${diagrams[@]}" <<'EOF' || status=1
import pathlib, sys
specs = ""
for doc in pathlib.Path("docs").rglob("*.md"):
    specs += doc.read_text()
ok = True
for path in sys.argv[1:]:
    src = pathlib.Path(path).read_text().strip()
    if src in specs:
        print(f"embed  OK      {path}")
    else:
        print(f"embed  FAILED  {path} — source not embedded verbatim in any docs/**/*.md")
        ok = False
sys.exit(0 if ok else 1)
EOF

exit $status
