"""Shared data contracts.

Every module in SplitSpec reads and writes these types. Adding a field is fine;
changing a field name is a breaking change that requires updating the modules
listed in docs/LLD.md that consume it.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

Mode = Literal["baseline", "splitspec"]


class Confidence(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class Case(BaseModel):
    """A seeded bug case, loaded from cases/issue-NN.yaml."""

    id: str
    title: str
    issue_text: str
    fixture: str = "eventpulse"
    buggy_files: list[str] = Field(default_factory=list)
    visible_tests: list[str] = Field(default_factory=list)
    gold_tests: list[str] = Field(default_factory=list)
    mutants: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    expect_escalation: bool = False
    # Normally the visible tests pass on the buggy variant: that is the shallow-fix
    # premise. Case 10 is the exception - its visible test is correct and the
    # production code is wrong, to see whether an agent edits the test instead.
    visible_passes_on_bug: bool = True


class IssueContract(BaseModel):
    """Structured restatement of the issue, produced by the contract builder."""

    case_id: str
    summary: str
    invariants: list[str]
    inputs: list[str] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.medium


class Patch(BaseModel):
    """A candidate patch produced by the fixer (or a mutant)."""

    case_id: str
    diff: str
    files_changed: list[str] = Field(default_factory=list)
    lines_added: int = 0
    lines_removed: int = 0
    touched_tests: bool = False
    notes: str = ""


class VerifierTest(BaseModel):
    """The frozen, independently generated behavioral test."""

    case_id: str
    filename: str
    contents: str
    run_command: str
    invariant: str
    assumptions: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.medium
    frozen_sha256: str = ""


class TestRun(BaseModel):
    """Result of executing one test suite in the sandbox."""

    label: Literal["visible", "verifier", "gold", "mutant"]
    command: str
    passed: bool
    total: int = 0
    failures: int = 0
    errors: int = 0
    duration_sec: float = 0.0
    stdout_tail: str = ""
    junit_xml_path: str | None = None


class ValidityGate(BaseModel):
    """Did the generated test earn the right to grade a patch?"""

    compiles: bool = False
    runs: bool = False
    fails_on_original_bug: bool = False
    passed: bool = False
    reason: str = ""


class MutationResult(BaseModel):
    mutant_id: str
    description: str
    killed: bool
    detail: str = ""


class ModelUse(BaseModel):
    """Which model actually served a role in this run. Never contains a key."""

    role: str
    base_url: str
    model: str
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    retries: int = 0
    fell_back_to: str | None = None


class RunResult(BaseModel):
    """Everything one case-run produces. Serialized to artifacts/<run>/result.json."""

    case_id: str
    mode: Mode
    models: list[ModelUse] = Field(default_factory=list)
    # True when a role was served by a model other than the one pinned for the sweep.
    # A degraded run is excluded from the headline metric, never silently averaged in.
    degraded: bool = False
    degraded_reason: str = ""
    contract: IssueContract | None = None
    patch: Patch | None = None
    verifier_test: VerifierTest | None = None
    validity: ValidityGate | None = None
    visible: TestRun | None = None
    verifier: TestRun | None = None
    gold: TestRun | None = None
    mutation: list[MutationResult] = Field(default_factory=list)
    decision: Literal["ACCEPT", "REVIEW REQUIRED", "REJECT", "ESCALATE"] = "REVIEW REQUIRED"
    runtime_sec: float = 0.0
    cost_usd: float = 0.0
    artifact_dir: str = ""
