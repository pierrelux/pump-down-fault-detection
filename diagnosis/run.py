#!/usr/bin/env python3
"""
Run fault diagnosis evaluation.

Usage:
    python -m diagnosis.run                    # run baselines
    python -m diagnosis.run -n 50 --seed 123   # 50 scenarios
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from diagnosis.evaluate import run_evaluation
from diagnosis.agents import anomaly_detector, random_agent


def main():
    parser = argparse.ArgumentParser(description="HVAC fault diagnosis evaluation")
    parser.add_argument("-n", type=int, default=21, help="Number of scenarios")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    agents = {
        "Random guess": random_agent,
        "Anomaly detector (10% threshold)": anomaly_detector,
    }

    for name, agent_fn in agents.items():
        print(f"\n{'='*60}")
        print(f"Agent: {name}")
        print(f"{'='*60}")
        run_evaluation(agent_fn, n_scenarios=args.n, seed=args.seed)
        print()


if __name__ == "__main__":
    main()
