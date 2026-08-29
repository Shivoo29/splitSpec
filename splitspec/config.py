"""Central config + paths. Every module imports paths from here, never hardcodes.

Provider config is per role. The fixer and verifier are pinned to their own model for
the whole sweep, because the model is the experiment's main variable: a run whose fixer
silently changed mid-sweep cannot support a result table.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES_DIR = ROOT / "cases"
FIXTURES_DIR = ROOT / "fixtures"
VISIBLE_TESTS_DIR = ROOT / "visible_tests"
GOLD_TESTS_DIR = ROOT / "gold_hidden_tests"
MUTANTS_DIR = ROOT / "mutant_patches"
ARTIFACTS_DIR = ROOT / "artifacts"
TRAJECTORIES_DIR = ROOT / "trajectories"

Role = str  # "fixer" | "verifier" | "contract" | "fallback"


def load_dotenv(path: Path | None = None) -> None:
    """Load ``SPLITSPEC_*`` style KEY=VALUE lines from .env into os.environ.

    Real environment variables win: this uses setdefault, so exporting a var still
    overrides the file. Stdlib parse - a dependency for a dozen lines would not
    earn its keep.

    Called by the CLI entry points, NOT by Settings.from_env(): .env is the
    documented place to put credentials (the CLI's own error message says so), but
    loading it inside from_env() would make every unit test read the developer's
    real .env and silently override its own monkeypatched environment. Keep
    Settings hermetic; load the file at the edge.
    """
    env_file = Path(path) if path is not None else ROOT / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.removeprefix("export ").strip()
        os.environ.setdefault(key, value.strip().strip('"').strip("'"))


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _keys(name: str) -> list[str]:
    raw = os.environ.get(name, "")
    return [k.strip() for k in raw.split(",") if k.strip()]


@dataclass(frozen=True)
class Provider:
    """One OpenAI-compatible endpoint pinned to one model.

    `api_keys` holds several keys for the SAME model. Rotating them is throughput only
    and changes nothing about the experiment; rotating models would.
    """

    role: Role
    base_url: str
    model: str
    api_keys: list[str] = field(default_factory=list)

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.model and self.api_keys)

    def describe(self) -> dict:
        """What gets recorded into result.json. Never includes a key."""
        return {"role": self.role, "base_url": self.base_url, "model": self.model,
                "key_count": len(self.api_keys)}

    @classmethod
    def from_env(cls, role: Role, fallback_to: Provider | None = None) -> Provider:
        prefix = f"SPLITSPEC_{role.upper()}"
        base_url = os.environ.get(f"{prefix}_BASE_URL", "").strip()
        model = os.environ.get(f"{prefix}_MODEL", "").strip()
        api_keys = _keys(f"{prefix}_API_KEYS")
        if not (base_url and model) and fallback_to is not None:
            return Provider(role, fallback_to.base_url, fallback_to.model, fallback_to.api_keys)
        return cls(role=role, base_url=base_url, model=model, api_keys=api_keys)


@dataclass(frozen=True)
class Settings:
    fixer: Provider
    verifier: Provider
    contract: Provider
    fallback: Provider | None = None
    allow_cross_model_fallback: bool = False
    max_tokens_per_agent: int = 200_000
    agent_timeout_sec: int = 900
    max_retries: int = 5
    retry_base_delay_sec: int = 2
    sandbox_image: str = "splitspec-sandbox:latest"
    sandbox_network: str = "none"

    @classmethod
    def from_env(cls) -> Settings:
        fixer = Provider.from_env("fixer")
        verifier = Provider.from_env("verifier")
        fallback = Provider.from_env("fallback")
        return cls(
            fixer=fixer,
            verifier=verifier,
            contract=Provider.from_env("contract", fallback_to=verifier),
            fallback=fallback if fallback.configured else None,
            allow_cross_model_fallback=_bool("SPLITSPEC_ALLOW_CROSS_MODEL_FALLBACK"),
            max_tokens_per_agent=_int("SPLITSPEC_MAX_TOKENS_PER_AGENT", 200_000),
            agent_timeout_sec=_int("SPLITSPEC_AGENT_TIMEOUT_SEC", 900),
            max_retries=_int("SPLITSPEC_MAX_RETRIES", 5),
            retry_base_delay_sec=_int("SPLITSPEC_RETRY_BASE_DELAY_SEC", 2),
            sandbox_image=os.environ.get("SPLITSPEC_SANDBOX_IMAGE", "splitspec-sandbox:latest"),
            sandbox_network=os.environ.get("SPLITSPEC_SANDBOX_NETWORK", "none"),
        )

    def provider(self, role: Role) -> Provider:
        return {"fixer": self.fixer, "verifier": self.verifier, "contract": self.contract}[role]

    def independence_note(self) -> str:
        """Recorded in the review packet: same-model fixer and verifier weaken the claim."""
        if self.fixer.model == self.verifier.model and self.fixer.base_url == self.verifier.base_url:
            return ("fixer and verifier share a model and provider; independence is procedural "
                    "(separate workspaces and frozen tests) but not architectural")
        return "fixer and verifier run on different models"
