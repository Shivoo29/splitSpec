"""Central config + paths. Every module imports paths from here, never hardcodes."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES_DIR = ROOT / "cases"
FIXTURES_DIR = ROOT / "fixtures"
VISIBLE_TESTS_DIR = ROOT / "visible_tests"
GOLD_TESTS_DIR = ROOT / "gold_hidden_tests"
MUTANTS_DIR = ROOT / "mutant_patches"
ARTIFACTS_DIR = ROOT / "artifacts"
TRAJECTORIES_DIR = ROOT / "trajectories"


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    api_key: str = ""
    model: str = "claude-sonnet-5"
    max_tokens_per_agent: int = 200_000
    agent_timeout_sec: int = 900
    sandbox_image: str = "splitspec-sandbox:latest"
    sandbox_network: str = "none"

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            model=os.environ.get("SPLITSPEC_MODEL", cls.model),
            max_tokens_per_agent=_int("SPLITSPEC_MAX_TOKENS_PER_AGENT", cls.max_tokens_per_agent),
            agent_timeout_sec=_int("SPLITSPEC_AGENT_TIMEOUT_SEC", cls.agent_timeout_sec),
            sandbox_image=os.environ.get("SPLITSPEC_SANDBOX_IMAGE", cls.sandbox_image),
            sandbox_network=os.environ.get("SPLITSPEC_SANDBOX_NETWORK", cls.sandbox_network),
        )
