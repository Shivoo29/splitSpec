"""Single-case run CLI (Module 9).

`python -m splitspec.run --mode {baseline,splitspec} --case cases/issue-07.yaml
--output artifacts/issue-07-splitspec`

Builds a :class:`GraphContext` from :meth:`Settings.from_env` and a real
OpenAI-compatible client per role, runs the appropriate graph, and leaves the
full PROJECT.md §13 artifact set plus ``result.json`` in ``--output``. The
resumable multi-case sweep lives in :mod:`splitspec.evaluate`.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Annotated

import typer
import yaml

from splitspec.config import Settings, load_dotenv
from splitspec.graph import GraphContext, execute
from splitspec.llm import OpenAICompatibleClient
from splitspec.schemas import Case, Mode, RunResult

app = typer.Typer()


def _load_case(path: Path) -> Case:
    return Case.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def _assert_configured(settings: Settings, mode: Mode) -> None:
    """Refuse a real run whose pinned providers for this mode aren't configured.

    An unconfigured (or keyless) provider cannot serve its role, and silently
    falling back to nothing would produce work that never measured the pinned
    model. The modes may not skip a role's provider.
    """
    roles = ("contract", "fixer") if mode == "baseline" else ("contract", "fixer", "verifier")
    missing = [r for r in roles if not settings.provider(r).configured]
    if missing:
        raise RuntimeError(
            f"providers not configured for {mode} run: {missing}. "
            "Check SPLITSPEC_*_BASE_URL/_MODEL/_API_KEYS in .env."
        )


def assert_models_exist(settings: Settings, mode: Mode) -> None:
    """Fail fast when a pinned model id is not one the provider actually serves.

    Checking the id is not paranoia and GET /models is not optional: Mistral
    answered a request for the retired `devstral-small-latest` with HTTP 200 served
    by `mistral-medium-3-5` rather than a 404. A silent substitution is worse than
    an error, because the run completes and records the model we ASKED for, so the
    result table names a model that never ran. The whole experiment is a comparison
    between models; a mislabelled row invalidates it.
    """
    import httpx

    roles = ("contract", "fixer") if mode == "baseline" else ("contract", "fixer", "verifier")
    for role in roles:
        provider = settings.provider(role)
        try:
            response = httpx.get(
                provider.base_url.rstrip("/") + "/models",
                headers={"Authorization": f"Bearer {provider.api_keys[0]}"},
                timeout=30,
            )
            response.raise_for_status()
            # Google's OpenAI-compatible endpoint lists ids as "models/<id>";
            # everyone else lists the bare id. Accept either spelling.
            served = set()
            for entry in response.json().get("data", []):
                model_id = entry.get("id") or ""
                served.add(model_id)
                served.add(model_id.removeprefix("models/"))
        except Exception as exc:  # noqa: BLE001 - an unlistable provider is not fatal
            print(f"WARN: could not list models for {role} ({exc}); skipping the id check")
            continue
        if served and provider.model not in served:
            raise RuntimeError(
                f"{role} model {provider.model!r} is not served by {provider.base_url}. "
                "Some providers silently substitute another model instead of "
                f"returning 404, which would mislabel the run. Available: {sorted(served)}"
            )


def run_case(case: Case, mode: Mode, output: Path, settings: Settings | None = None) -> RunResult:
    """Execute one case/mode and return the written :class:`RunResult`."""
    if settings is None:
        load_dotenv()
        settings = Settings.from_env()
    _assert_configured(settings, mode)
    assert_models_exist(settings, mode)

    def make_client(provider):
        return OpenAICompatibleClient(
            provider,
            max_retries=settings.max_retries,
            retry_base_delay_sec=settings.retry_base_delay_sec,
        )

    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    # Workspaces are ephemeral and destroyed inside the graph; keep them out of
    # the artifact tree so nothing agent-authored lands among the shipped files.
    with tempfile.TemporaryDirectory(prefix=f"splitspec-ws-{case.id}-") as ws_tmp:
        ctx = GraphContext(
            settings=settings,
            make_client=make_client,
            workspace_root=Path(ws_tmp),
            artifact_dir=output,
        )
        return execute(ctx, case, mode)


@app.command()
def main(
    mode: Annotated[Mode, typer.Option(help="baseline or splitspec")],
    case: Annotated[Path, typer.Option(help="path to cases/issue-07.yaml")],
    output: Annotated[Path, typer.Option(help="artifact directory, e.g. artifacts/issue-07-splitspec")],
) -> None:
    """Run one case end to end and write its artifact set."""
    loaded = _load_case(case)
    result = run_case(loaded, mode, output)
    print(json.dumps({
        "case": result.case_id,
        "mode": result.mode,
        "models": [(m.role, m.model) for m in result.models],
        "degraded": result.degraded,
        "visible": result.visible.passed if result.visible else None,
        "verifier": result.verifier.passed if result.verifier else None,
        "gold": result.gold.passed if result.gold else None,
        "validity": result.validity.passed if result.validity else None,
        "cost_usd": result.cost_usd,
        "runtime_sec": result.runtime_sec,
        "artifact_dir": result.artifact_dir,
    }, indent=2))


if __name__ == "__main__":
    app()
