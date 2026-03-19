#!/usr/bin/env python3
"""
LLM agent for HVAC fault diagnosis using Claude with tool use.

The agent gets:
- A system prompt with the spec sheet (no model code, no fault parameters)
- A tool: read_sensors(fan_speed) → sensor readings
- Asked to diagnose the fault

Usage:
    python -m diagnosis.llm_agent              # run 21 scenarios
    python -m diagnosis.llm_agent -n 5         # run 5 scenarios
    python -m diagnosis.llm_agent --verbose     # print agent reasoning

Requires: ANTHROPIC_API_KEY environment variable.
"""

import sys
import os
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import anthropic

from diagnosis.environment import HVACEnvironment, FaultScenario, random_fault, FAULT_TYPES
from diagnosis.evaluate import Diagnosis, run_evaluation

# The tool definition exposed to the LLM
TOOLS = [
    {
        "name": "read_sensors",
        "description": (
            "Read the current sensor values from the HVAC system. "
            "You can optionally change the condenser fan speed to perform "
            "a perturbation test. The system will reach steady state at "
            "the new fan speed before returning readings.\n\n"
            "Fan speed values:\n"
            "  0.20 = low speed\n"
            "  0.45 = normal operating speed\n"
            "  0.80 = high speed\n\n"
            "You can call this tool multiple times with different fan speeds "
            "to observe how the system responds to perturbations."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fan_speed": {
                    "type": "number",
                    "description": "Condenser fan frontal air velocity in m/s. Default 0.45 (normal).",
                    "default": 0.45,
                }
            },
            "required": [],
        },
    }
]

SYSTEM_PROMPT_TEMPLATE = """You are an HVAC diagnostic technician. You have been called to diagnose a residential air conditioning system that may or may not have a fault.

Here is the manufacturer spec sheet for the unit:

<spec_sheet>
{spec_sheet}
</spec_sheet>

Here are sensor readings from the last maintenance visit, when the system was verified healthy and operating correctly at the same outdoor temperature:

<baseline_readings>
{baseline}
</baseline_readings>

You have access to a tool called `read_sensors` that lets you take current pressure and temperature readings from the system. You can also change the condenser fan speed to perform perturbation tests.

Your task:
1. Take current readings and compare them to the baseline
2. If needed, perform perturbation tests (e.g., change fan speed) to disambiguate faults
3. Diagnose the system

Possible fault types:
- healthy: system is operating normally
- low_charge: system is undercharged (refrigerant leak)
- high_charge: system is overcharged
- evap_fouling: evaporator coil is fouled (reduced indoor airflow)
- compressor_wear: compressor has reduced capacity (valve wear)
- txv_stuck_open: thermostatic expansion valve is stuck open
- txv_stuck_closed: thermostatic expansion valve is stuck closed

When you have enough information, state your diagnosis in exactly this format:
DIAGNOSIS: <fault_type>
CONFIDENCE: <0.0 to 1.0>
REASONING: <your explanation>

Be efficient — try to diagnose in as few sensor readings as possible."""


def build_llm_agent(model: str = "claude-sonnet-4-20250514", verbose: bool = False):
    """Create an LLM agent function compatible with run_evaluation."""

    client = anthropic.Anthropic()

    def agent_fn(env: HVACEnvironment, spec_sheet: str) -> Diagnosis:
        baseline_text = str(env.baseline)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            spec_sheet=spec_sheet, baseline=baseline_text)

        messages = [
            {"role": "user", "content": "Please diagnose this HVAC system. Start by taking current sensor readings and comparing to the baseline."}
        ]

        # Tool-use loop
        for _ in range(10):  # max 10 rounds
            response = client.messages.create(
                model=model,
                max_tokens=1024,
                system=system_prompt,
                tools=TOOLS,
                messages=messages,
            )

            # Check for tool use
            tool_calls = [b for b in response.content if b.type == "tool_use"]
            text_blocks = [b for b in response.content if b.type == "text"]

            if verbose and text_blocks:
                for tb in text_blocks:
                    print(f"    AGENT: {tb.text[:200]}")

            if not tool_calls:
                # Agent is done — parse diagnosis from text
                full_text = " ".join(tb.text for tb in text_blocks)
                return parse_diagnosis(full_text)

            # Execute tool calls
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for tc in tool_calls:
                if tc.name == "read_sensors":
                    fan_speed = tc.input.get("fan_speed", 0.45)
                    readings = env.read_sensors(fan_speed=fan_speed)
                    result_text = json.dumps(readings.to_dict(), indent=2)
                    if verbose:
                        print(f"    TOOL read_sensors(fan={fan_speed}): SC={readings.subcooling_F:.1f}°F "
                              f"SH={readings.superheat_F:.1f}°F P_suc={readings.suction_pressure_psi:.0f}")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tc.id,
                        "content": result_text,
                    })

            messages.append({"role": "user", "content": tool_results})

            # If stop_reason is end_turn (not tool_use), we're done
            if response.stop_reason == "end_turn":
                full_text = " ".join(tb.text for tb in text_blocks)
                return parse_diagnosis(full_text)

        # Fallback if max rounds exceeded
        return Diagnosis(fault_type="healthy", confidence=0.0,
                         reasoning="Max rounds exceeded without diagnosis")

    return agent_fn


def parse_diagnosis(text: str) -> Diagnosis:
    """Parse the agent's diagnosis from its text output."""
    fault_type = "healthy"
    confidence = 0.5
    reasoning = text

    # Look for DIAGNOSIS: line
    for line in text.split("\n"):
        line_lower = line.lower().strip()
        if line_lower.startswith("diagnosis:"):
            raw = line.split(":", 1)[1].strip().lower()
            raw = raw.replace(" ", "_").replace("-", "_")
            # Clean up common variations
            for ft in FAULT_TYPES:
                if ft in raw:
                    fault_type = ft
                    break
            else:
                # Try partial matches
                if "low" in raw and "charge" in raw:
                    fault_type = "low_charge"
                elif "under" in raw:
                    fault_type = "low_charge"
                elif "high" in raw and "charge" in raw:
                    fault_type = "high_charge"
                elif "over" in raw:
                    fault_type = "high_charge"
                elif "evap" in raw or "fouling" in raw or "airflow" in raw:
                    fault_type = "evap_fouling"
                elif "compressor" in raw or "wear" in raw:
                    fault_type = "compressor_wear"
                elif "txv" in raw and "open" in raw:
                    fault_type = "txv_stuck_open"
                elif "txv" in raw and "closed" in raw:
                    fault_type = "txv_stuck_closed"
                elif "normal" in raw or "healthy" in raw or "no_fault" in raw:
                    fault_type = "healthy"

        if line_lower.startswith("confidence:"):
            try:
                confidence = float(line.split(":", 1)[1].strip())
            except ValueError:
                pass

        if line_lower.startswith("reasoning:"):
            reasoning = line.split(":", 1)[1].strip()

    return Diagnosis(fault_type=fault_type, confidence=confidence, reasoning=reasoning)


def main():
    parser = argparse.ArgumentParser(description="LLM agent HVAC fault diagnosis")
    parser.add_argument("-n", type=int, default=21, help="Number of scenarios")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--model", default="claude-sonnet-4-20250514")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    agent_fn = build_llm_agent(model=args.model, verbose=args.verbose)

    print(f"Model: {args.model}")
    print(f"Scenarios: {args.n}, seed: {args.seed}")
    print(f"{'='*60}")

    results = run_evaluation(agent_fn, n_scenarios=args.n, seed=args.seed)

    # Print reasoning for wrong answers
    wrong = [r for r in results if not r.correct]
    if wrong:
        print(f"\n--- Incorrect diagnoses ({len(wrong)}) ---")
        for r in wrong:
            print(f"\n  Truth: {r.scenario.fault_type} ({r.scenario.description()})")
            print(f"  Pred:  {r.diagnosis.fault_type} (confidence={r.diagnosis.confidence:.1f})")
            print(f"  Why:   {r.diagnosis.reasoning[:200]}")


if __name__ == "__main__":
    main()
