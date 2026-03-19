#!/usr/bin/env python3
"""
Run fault diagnosis evaluation.

Usage:
    python -m diagnosis.run                    # run all agents
    python -m diagnosis.run --agent rule       # rule-based only
    python -m diagnosis.run --agent active     # active rule-based only
    python -m diagnosis.run -n 50 --seed 123   # 50 scenarios, seed 123
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from diagnosis.evaluate import run_evaluation
from diagnosis.agents import rule_based_agent, active_rule_agent


def main():
    parser = argparse.ArgumentParser(description="HVAC fault diagnosis evaluation")
    parser.add_argument("--agent", choices=["rule", "active", "all"], default="all")
    parser.add_argument("-n", type=int, default=20, help="Number of scenarios")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    agents = {}
    if args.agent in ("rule", "all"):
        agents["Rule-based (single reading)"] = rule_based_agent
    if args.agent in ("active", "all"):
        agents["Active rule-based (fan test)"] = active_rule_agent

    for name, agent_fn in agents.items():
        print(f"\n{'='*60}")
        print(f"Agent: {name}")
        print(f"{'='*60}")
        results = run_evaluation(agent_fn, n_scenarios=args.n, seed=args.seed)
        print()


if __name__ == "__main__":
    main()
