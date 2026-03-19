# Research Plan: Active Fault Diagnosis with LLM Agents

## Idea

Use an LLM agent to actively diagnose refrigerant system faults through
sequential experiment design. The agent sees only a spec sheet (not the
simulator code) and can request sensor readings or perturbation tests. The
simulator generates physically realistic readings based on a hidden fault.

## Why this is interesting

1. **No equipment-specific model needed.** The agent works from a PDF spec
   sheet + internalized HVAC knowledge. No AHRI maps, no HX geometry.

2. **Active, not passive.** The agent chooses what to measure next based on
   what it's seen. A fan speed test distinguishes faults that look identical
   in steady-state readings.

3. **Testable hypothesis.** Can an LLM, given only a spec sheet, approach
   the diagnostic accuracy of an agent with full model access?

## What we have (validated)

A charge-balance solver (`pyhpdm`) that computes steady-state operating
conditions (P_suc, P_dis, subcooling, superheat, T_discharge, mass flow)
as a function of:

- **Charge level** — validated against 10 experimental cases (0.5% error)
- **Condenser fan speed** — `V_air_frontal` parameter, correct response
- **Outdoor temperature** — `T_outdoor_K` parameter

## Fault types we can simulate

The solver accepts fault injection parameters:

```python
solve_charge_balance(
    M_target_kg=...,           # charge level
    condenser_fouling=1.0,     # 1.0=healthy, <1.0=fouled (NOT WORKING — see below)
    evap_approach_K=12.0,      # 12=healthy, >12=fouled evaporator
    compressor_degradation=1.0,# 1.0=healthy, <1.0=worn
    superheat_K=5.0,           # 5=healthy TXV, varies for TXV faults
    V_air_frontal=0.45,        # controllable: fan speed
)
```

### Working fault signatures (at nominal 8.08 lbm, 95°F outdoor)

```
                                  P_suc   P_dis     SC      SH   T_dis   mdot
HEALTHY                           180     383    15°F    9°F    160°F    279
Low charge (15%)                  180     343     0°F    9°F    147°F    281
Evap fouling (+5K)                156     374    14°F    9°F    163°F    238
Compressor wear (10%)             180     374    14°F    9°F    157°F    251
TXV stuck open                    180     382    15°F    1°F    160°F    279
TXV stuck closed                  180     383    16°F   20°F    160°F    279
```

**Key distinguishing features:**
- Low charge: SC → 0 (unique), P_suc unchanged
- Evap fouling: P_suc drops (unique), T_dis rises (unique)
- Compressor wear: mdot drops (unique), SC decreases gradually
- TXV fault: only SH changes (easy)

### NOT working: condenser fouling

The condenser model is oversized — exit temperature is pinned at T_air
regardless of fouling level. Would need a 2D solver (energy + charge
balance) to properly simulate. Not a priority for initial research.

## Architecture

```
┌──────────────────┐                    ┌──────────────────┐
│    LLM Agent     │   "read P_suc"     │   Environment    │
│                  │ ──────────────────→ │                  │
│  Input:          │   "180.2 psi"      │  solve_charge_   │
│  - spec sheet    │ ←────────────────── │  balance(...)    │
│  - tool access   │                    │                  │
│                  │   "set fan high"   │  Hidden state:   │
│  No access to:   │ ──────────────────→ │  - charge level  │
│  - simulator     │   "SC still 0°F"  │  - fault type    │
│  - fault params  │ ←────────────────── │  - severity      │
│                  │                    │                  │
│  Output:         │   "diagnosis:      │                  │
│  - fault type    │    low charge,     │                  │
│  - severity      │    ~15% under"     │                  │
│  - confidence    │                    │                  │
└──────────────────┘                    └──────────────────┘
```

## Experiment protocol

1. **Setup**: Create a "spec sheet" text for the 3-ton R410A split system
   (model number, rated capacity, refrigerant, nominal charge — info a
   technician would have).

2. **Fault injection**: Randomly sample a fault scenario:
   - Fault type: {healthy, low_charge, evap_fouling, compressor_wear, txv_fault}
   - Severity: sampled from realistic range
   - Outdoor temp: sampled from 75–105°F

3. **Agent interaction**: The agent gets the spec sheet and access to tools:
   - `read_sensors(fan_speed)` → returns P_suc, P_dis, T_discharge, T_outdoor,
     T_suction, T_liquid_line (derived from solver output)
   - The agent can call this multiple times with different fan speeds

4. **Evaluation**: Compare agent's diagnosis to ground truth.
   - Classification accuracy (fault type)
   - Severity estimation error
   - Number of queries (efficiency)

## Baselines

1. **Random guessing** — lower bound
2. **Single-reading rule-based** — ASHRAE-style lookup from one set of readings
3. **Oracle (full model access)** — upper bound
4. **LLM with spec sheet** — our method

## Research questions

1. Does the LLM correctly choose disambiguating tests (e.g., fan speed
   perturbation to distinguish low charge from compressor wear)?

2. How does diagnostic accuracy scale with the number of allowed queries?

3. Does chain-of-thought reasoning about thermodynamics improve accuracy
   over direct classification?

4. Can the agent handle combined faults (e.g., low charge + evap fouling)?

## What to build next

1. **Environment wrapper**: Thin Python class that wraps `solve_charge_balance`
   as a tool-callable interface. Hides fault parameters, exposes sensor readings.

2. **Spec sheet**: Text description of the system (not the model code).

3. **Evaluation harness**: Sample fault scenarios, run agent, score results.

4. **Agent prompt**: System prompt for Claude with spec sheet + tool descriptions.
   No HVAC-specific instructions — test what the LLM knows from training.

## Open questions

- Should the agent see T_indoor (thermostat setpoint)? Probably yes — a
  technician would know this.
- Should we add sensor noise? Yes, eventually. Start clean, add noise later.
- Should we allow the agent to ask the technician questions (e.g., "when did
  the unit last have a charge check?")? Interesting but out of scope initially.
