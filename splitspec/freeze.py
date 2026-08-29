"""Verifier test freeze + load (Module 7).

`freeze()` persists a :class:`VerifierTest` to an artifact directory as the
human/CRU-readable ``verifier_test.py`` (PROJECT.md §13) plus a sidecar metadata
file holding the fields pytest's hash alone can't capture (filename, invariant,
confidence, ...). It records the SHA-256 of the frozen contents and makes the
artifacts read-only.

`load_frozen()` reconstructs the test and re-hashes the on-disk file on every
read, raising if it no longer matches — tampering with a frozen test invalidates
the run, per HLD §2, so this is an assertion, not a log line.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from splitspec.schemas import Confidence, VerifierTest

#: The on-disk artifact name (PROJECT.md §13); distinct from VerifierTest.filename,
#: which is the pytest-collectible test_*.py name inside a workspace.
VERIFIER_TEST_FILENAME = "verifier_test.py"
_VERIFIER_META_FILENAME = "verifier_meta.json"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def freeze(test: VerifierTest, artifact_dir: Path) -> VerifierTest:
    """Write ``test`` into ``artifact_dir`` and return it with ``frozen_sha256`` set."""
    artifact_dir = Path(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    contents = test.contents or ""
    sha = _sha256(contents.encode("utf-8"))

    test_path = artifact_dir / VERIFIER_TEST_FILENAME
    test_path.write_text(contents, encoding="utf-8")
    os.chmod(test_path, 0o444)

    meta = {
        "case_id": test.case_id,
        "filename": test.filename,
        "run_command": test.run_command,
        "invariant": test.invariant,
        "assumptions": list(test.assumptions),
        "confidence": test.confidence.value,
        "frozen_sha256": sha,
    }
    meta_path = artifact_dir / _VERIFIER_META_FILENAME
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    os.chmod(meta_path, 0o444)

    return test.model_copy(update={"frozen_sha256": sha})


def load_frozen(artifact_dir: Path) -> VerifierTest:
    """Reconstruct the frozen test, re-verifying its SHA-256; raise on mismatch."""
    artifact_dir = Path(artifact_dir)
    test_path = artifact_dir / VERIFIER_TEST_FILENAME
    meta_path = artifact_dir / _VERIFIER_META_FILENAME
    if not test_path.is_file() or not meta_path.is_file():
        raise FileNotFoundError(f"no frozen verifier test in {artifact_dir}")

    contents = test_path.read_text(encoding="utf-8")
    computed = _sha256(contents.encode("utf-8"))
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    expected = meta["frozen_sha256"]
    if computed != expected:
        raise RuntimeError(
            "frozen verifier test hash mismatch: the file on disk was tampered "
            f"(recorded {expected}, read {computed})"
        )

    return VerifierTest(
        case_id=meta["case_id"],
        filename=meta["filename"],
        contents=contents,
        run_command=meta["run_command"],
        invariant=meta["invariant"],
        assumptions=list(meta["assumptions"]),
        confidence=Confidence(meta["confidence"]),
        frozen_sha256=computed,
    )
