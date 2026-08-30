#!/usr/bin/env bash
# Live progress for a running evaluate sweep.  Usage: scripts/sweep_progress.sh
# Ctrl-C to stop watching; the sweep itself is unaffected.
TOTAL=24
while true; do
  done_n=$(ls artifacts/*/result.json 2>/dev/null | wc -l)
  fail_n=$(grep -l '"ok": false' artifacts/issue-*/result.json 2>/dev/null | wc -l)
  ok_n=$((done_n - fail_n))
  filled=$((done_n * 40 / TOTAL))
  bar=$(printf '%*s' "$filled" '' | tr ' ' '#')
  pad=$(printf '%*s' $((40 - filled)) '')
  if pgrep -f splitspec.evaluate >/dev/null; then
    now=$(find artifacts -name trajectory.jsonl -newermt '-90 seconds' -printf '%f\n' 2>/dev/null | head -1)
    cur=$(find artifacts -name trajectory.jsonl -newermt '-90 seconds' -printf '%h\n' 2>/dev/null | head -1 | xargs -r basename)
    state="running  ${cur:-starting}"
  else
    state="FINISHED"
  fi
  printf '\r[%s%s] %2d/%d  ok:%d fail:%d  %s   ' "$bar" "$pad" "$done_n" "$TOTAL" "$ok_n" "$fail_n" "$state"
  pgrep -f splitspec.evaluate >/dev/null || { echo; break; }
  sleep 10
done
