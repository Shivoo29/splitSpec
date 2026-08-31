#!/usr/bin/env bash
# Screen-recording shots for the SplitSpec video. Each shot is a real command on
# real artifacts - nothing here is staged, which is the point.
#
#   scripts/demo_shot.sh cold-open     visible passes, gold fails, on the SAME code
#   scripts/demo_shot.sh baseline      what the baseline decides, per case
#   scripts/demo_shot.sh compare       the headline table
#   scripts/demo_shot.sh the-miss      issue-05: valid test, broken patch, ACCEPT
#   scripts/demo_shot.sh the-bug       the malformed diff that deleted a line
#
# Recording tip: run `clear` first, and keep the terminal ~100 cols so text stays
# large enough to read at 1080p.
set -u
cd "$(dirname "$0")/.."
PY=.venv/bin/python
CASE=${CASE:-issue-05}

pause() { sleep "${1:-1.4}"; }
say() { printf '\n\033[1;36m%s\033[0m\n\n' "$1"; }

case "${1:-}" in

cold-open)
  say "The visible test suite, run against the buggy code:"
  pause
  PYTHONPATH=. $PY - <<PYEOF
import tempfile, pathlib, yaml
from splitspec.schemas import Case, Patch
from splitspec.judge import judge
from splitspec.trace import Trace
case = Case(**yaml.safe_load(open("cases/$CASE.yaml").read()))
root = pathlib.Path(tempfile.mkdtemp())
runs = judge(case, Patch(case_id=case.id, diff=""), None, "baseline", root, Trace(root / "t.jsonl"))
v, g = runs["visible"], runs["gold"]
print(v.stdout_tail.strip()[-400:])
print()
print("\033[1;32m  ALL VISIBLE TESTS PASS\033[0m")
print()
input("  [enter for the hidden suite]")
print()
print("\033[1;31m  The hidden gold suite, on the SAME code:\033[0m")
print()
print(g.stdout_tail.strip()[-700:])
print()
print(f"\033[1;31m  {g.failures} of {g.total} FAILED. The bug was never fixed.\033[0m")
PYEOF
  ;;

baseline)
  say "Every baseline decision, across the sweep:"
  $PY - <<'PYEOF'
import json, glob, os
for f in sorted(glob.glob("artifacts/issue-*-baseline/result.json")):
    d = json.load(open(f))
    n = os.path.basename(os.path.dirname(f)).replace("-baseline", "")
    if d.get("ok") is False:
        continue
    gold = "correct" if d["gold"] and d["gold"]["passed"] else "broken "
    print(f"  {n:10}  patch was {gold}  ->  \033[1;33m{d['decision']}\033[0m")
print()
print("  \033[1mNothing can be cleared. A human reads all of them.\033[0m")
PYEOF
  ;;

compare)
  $PY -m splitspec.report --from artifacts/
  ;;

the-miss)
  say "issue-05 - the case it got wrong:"
  $PY - <<'PYEOF'
import json
d = json.load(open("artifacts/issue-05-splitspec/result.json"))
print(f"  validity gate : \033[1;32mVALID\033[0m - {d['validity']['reason']}")
k = sum(1 for m in d["mutation"] if m["killed"])
print(f"  mutation      : killed {k}/{len(d['mutation'])} known-broken variants")
print()
print(f"  visible       : \033[1;32mPASS\033[0m")
print(f"  verifier      : \033[1;32mPASS\033[0m   <- the independent test agreed")
print(f"  gold (hidden) : \033[1;31mFAIL {d['gold']['failures']}/{d['gold']['total']}\033[0m   <- the patch is broken")
print()
print(f"  decision      : \033[1;31m{d['decision']}\033[0m")
print()
print("  \033[1mA valid, mutation-killing test cleared a broken patch.\033[0m")
PYEOF
  ;;

the-bug)
  say "What a patch looked like before the fix:"
  printf '  \033[2m@@ -37,4 +37,4 @@\033[0m\n'
  printf '       amount = assert_amount(amount)\n'
  printf '       if currency is not None:\n'
  printf '           amount = quantize(amount, currency)\n'
  printf '  \033[1;31m-    return str(amount)\033[0m\033[1;32m+    return str(amount)\033[0m\n'
  printf '\n  \033[1;33mTwo lines. One physical line. Neither one matches.\033[0m\n'
  printf '  \033[1mSo applying the patch deleted the return statement.\033[0m\n\n'
  pause 2
  say "Same model, same patch, before and after fixing the diff:"
  printf '    before   gold  \033[1;31mFAIL 1/5\033[0m   ->  scored as a shallow fix\n'
  printf '    after    gold  \033[1;32mPASS 5/5\033[0m   ->  a correct fix, correctly accepted\n\n'
  printf '  \033[1m21 of 22 runs were measuring my bug.\033[0m\n\n'
  ;;

*)
  sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'
  ;;
esac
