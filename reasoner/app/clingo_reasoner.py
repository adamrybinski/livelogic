"""LiveLogic Reasoner - Async Clingo wrapper with SolveResult dataclass."""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import clingo

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class SolveResult:
    """Immutable result from a Clingo solve call."""

    satisfiable: bool | None = None
    unsatisfiable: bool | None = None
    models: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    unsat_core: list[str] = dataclasses.field(default_factory=list)
    timed_out: bool = False
    error: str | None = None
    solve_time_ms: float = 0.0


class ClingoReasoner:
    """Async-safe wrapper around clingo.Control with timeout support."""

    DEFAULT_TIMEOUT = 5.0  # seconds

    def __init__(
        self,
        lp_path: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_models: int = 10,
    ) -> None:
        self.lp_path = lp_path
        self.timeout = timeout
        self.max_models = max_models
        self._executor = ThreadPoolExecutor(max_workers=1)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def solve(
        self,
        facts: str,
        lp_path: str | None = None,
        timeout: float | None = None,
    ) -> SolveResult:
        """Run Clingo with *facts* + base knowledge base and return results."""

        effective_lp = lp_path or self.lp_path
        effective_timeout = timeout or self.timeout

        loop = asyncio.get_running_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(
                self._executor,
                self._run_clingo,
                facts,
                effective_lp,
                effective_timeout,
            ),
            timeout=effective_timeout + 1,  # outer guard
        )

    async def check_unsat_core(
        self,
        facts: str,
        lp_path: str | None = None,
        timeout: float | None = None,
    ) -> SolveResult:
        """Solve with unsat-core extraction enabled."""

        effective_lp = lp_path or self.lp_path
        effective_timeout = timeout or self.timeout

        loop = asyncio.get_running_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(
                self._executor,
                self._run_clingo_unsat_core,
                facts,
                effective_lp,
                effective_timeout,
            ),
            timeout=effective_timeout + 1,
        )

    # ------------------------------------------------------------------
    # Sync internals (run in executor)
    # ------------------------------------------------------------------

    def _run_clingo(
        self,
        facts: str,
        lp_path: str | None,
        timeout: float,
    ) -> SolveResult:
        try:
            ctl = clingo.Control(["--warn=none"])
            if lp_path:
                ctl.load(lp_path)
            ctl.add("base", [], facts)
            ctl.ground([("base", [])])

            models: list[dict[str, Any]] = []
            timed_out = False

            def on_model(m: clingo.Model) -> None:
                if len(models) < self.max_models:
                    models.append({str(a): True for a in m.symbols(shown=True)})

            result = ctl.solve(on_model=on_model, yield_=False)
            return SolveResult(
                satisfiable=result.satisfiable,
                unsatisfiable=result.unsatisfiable,
                models=models,
                timed_out=timed_out,
            )
        except Exception as exc:
            logger.exception("Clingo solve failed")
            return SolveResult(error=str(exc))

    def _run_clingo_unsat_core(
        self,
        facts: str,
        lp_path: str | None,
        timeout: float,
    ) -> SolveResult:
        try:
            ctl = clingo.Control(["--warn=none", "--unsat-cores=1"])
            if lp_path:
                ctl.load(lp_path)
            ctl.add("base", [], facts)
            ctl.ground([("base", [])])

            models: list[dict[str, Any]] = []
            unsat_core: list[str] = []

            def on_model(m: clingo.Model) -> None:
                if len(models) < self.max_models:
                    models.append({str(a): True for a in m.symbols(shown=True)})

            result = ctl.solve(on_model=on_model, yield_=False)

            if result.unsatisfiable:
                # Extract unsat core from the model's assumptions
                unsat_core = ["constraint_conflict"]  # placeholder; refine with clingo API

            return SolveResult(
                satisfiable=result.satisfiable,
                unsatisfiable=result.unsatisfiable,
                models=models,
                unsat_core=unsat_core,
            )
        except Exception as exc:
            logger.exception("Clingo unsat-core solve failed")
            return SolveResult(error=str(exc))
