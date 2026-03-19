#!/usr/bin/env python3
"""
Evaluate an LLM agent on HVAC fault diagnosis.

Generates fault scenarios, presents them to the agent (via a callback),
and scores the agent's diagnosis against ground truth.

Usage:
    from diagnosis.evaluate import run_evaluation
    results = run_evaluation(agent_fn, n_scenarios=20, seed=42)
"""

import json
import random
from dataclasses import dataclass, asdict
from typing import Callable, Optional

from .environment import HVACEnvironment, FaultScenario, random_fault, FAULT_TYPES


@dataclass
class Diagnosis:
    """The agent's output."""
    fault_type: str            # one of FAULT_TYPES
    confidence: float = 0.0    # 0-1
    reasoning: str = ""        # free-text explanation
    severity: str = ""         # e.g. "20% undercharged"


@dataclass
class EvalResult:
    """Result for a single scenario."""
    scenario: FaultScenario
    diagnosis: Diagnosis
    correct: bool
    queries_used: int


def score_diagnosis(scenario: FaultScenario, diagnosis: Diagnosis) -> bool:
    """Check if the diagnosis matches the ground truth.

    Charge faults: low_charge and high_charge must match exactly.
    Other faults: fault_type must match.
    Healthy must be diagnosed as healthy.
    """
    gt = scenario.fault_type
    pred = diagnosis.fault_type

    # Normalize
    pred = pred.lower().strip().replace(" ", "_").replace("-", "_")

    # Allow common aliases
    aliases = {
        "undercharge": "low_charge",
        "low charge": "low_charge",
        "overcharge": "high_charge",
        "high charge": "high_charge",
        "evaporator_fouling": "evap_fouling",
        "evaporator fouling": "evap_fouling",
        "compressor_degradation": "compressor_wear",
        "compressor degradation": "compressor_wear",
        "txv_open": "txv_stuck_open",
        "txv_closed": "txv_stuck_closed",
        "normal": "healthy",
        "no_fault": "healthy",
        "no fault": "healthy",
    }
    pred = aliases.get(pred, pred)

    return pred == gt


def run_evaluation(
    agent_fn: Callable[[HVACEnvironment, str], Diagnosis],
    n_scenarios: int = 20,
    seed: int = 42,
    spec_sheet_path: str = None,
) -> list[EvalResult]:
    """Run the full evaluation.

    Parameters
    ----------
    agent_fn : callable(env: HVACEnvironment, spec_sheet: str) -> Diagnosis
        The agent. It receives the environment (for querying sensors) and the
        spec sheet text. It should return a Diagnosis.
    n_scenarios : number of fault scenarios to test
    seed : random seed for reproducibility
    spec_sheet_path : path to spec sheet file (default: diagnosis/spec_sheet.txt)

    Returns
    -------
    list of EvalResult
    """
    import os
    if spec_sheet_path is None:
        spec_sheet_path = os.path.join(os.path.dirname(__file__), "spec_sheet.txt")
    with open(spec_sheet_path) as f:
        spec_sheet = f.read()

    rng = random.Random(seed)
    results = []

    for i in range(n_scenarios):
        scenario = random_fault(rng)
        env = HVACEnvironment(scenario)

        diagnosis = agent_fn(env, spec_sheet)

        correct = score_diagnosis(scenario, diagnosis)
        results.append(EvalResult(
            scenario=scenario,
            diagnosis=diagnosis,
            correct=correct,
            queries_used=env.query_count,
        ))

        status = "CORRECT" if correct else "WRONG"
        print(f"  [{i+1:2d}/{n_scenarios}] {status:7s}  "
              f"truth={scenario.fault_type:<20s} "
              f"pred={diagnosis.fault_type:<20s} "
              f"queries={env.query_count}")

    # Summary
    n_correct = sum(1 for r in results if r.correct)
    avg_queries = sum(r.queries_used for r in results) / len(results)
    print(f"\nAccuracy: {n_correct}/{n_scenarios} ({100*n_correct/n_scenarios:.0f}%)")
    print(f"Avg queries: {avg_queries:.1f}")

    # Per-fault breakdown
    print(f"\nPer-fault accuracy:")
    for ft in FAULT_TYPES:
        subset = [r for r in results if r.scenario.fault_type == ft]
        if subset:
            n_ok = sum(1 for r in subset if r.correct)
            print(f"  {ft:<20s} {n_ok}/{len(subset)}")

    return results
