# HPDM Reverse-Engineering & Reproduction Plan

**Goal:** Build `pyhpdm`, a Python reimplementation of the DOE/ORNL Heat Pump Design Model,
validated against the original HPDM web interface via browser automation.

**Motivation:** Reproduce the charge prediction results of Li, Shen, Welch & Gluesenkamp (2024),
"A Refrigerant Charge Prediction Method Based on Pump Down Operation," which relies on HPDM's
segment-by-segment condenser model and compressor maps.

**Execution environment:** Claude Code with Playwright browser automation.

---

## 0. Intelligence Already Gathered

We have extracted detailed internal documentation from public sources:

| Source | What it contains |
|--------|-----------------|
| ORNL/CON-343 (Rice 1991), full PDF via `web.ornl.gov/~jacksonwl/hpdm/814355.pdf` | Mark IV user's guide: HPDATA input format, charge inventory model, solution logic (Figs 14-15), compressor map fitting, void fraction options, TXV/capillary/accumulator models, full subroutine listing (Appendices E-F) |
| Flex HPDM presentation via `web.ornl.gov/~wlj/hpdm/Flex_HPDM_General_Introduction.pdf` | Component architecture, segment-to-segment HX model, ε-NTU formulation, variable attributes (i/g/o/r/t), arbitrary circuitry |
| ACEEE 2017 slides (Shen et al.) | Compressor 10-coeff map equation, superheat correction formula, wrapped-tank coil model |
| HPDM web interface (`hpdmflex.ornl.gov`) | All configuration names, full category tree, download links |
| HPDM-STD205 GitHub repo (`github.com/ORNL/HPDM-STD205`) | Output file format (`Out.xls`), ASHRAE 205 conversion code |
| Shen, Braun & Groll (2009) IJR paper | Two-point charge tuning method, off-design modeling improvements, charge inventory validation |
| Li & Shen (2024) charge prediction paper | Pump-down method equations, validation data (Tables 1-3, Figs 3-11) |

---

## 1. Data Collection Phase (Browser Automation)

### 1.1 Download Desktop Package & Templates

```
URL: https://hpdmflex.ornl.gov/hpdm/installer/HPDM.Zip
URL: https://hpdmflex.ornl.gov/hpdm/installer/Compressor.zip
URL: https://hpdmflex.ornl.gov/hpdm/installer/HeatExchangers.zip
URL: https://hpdmflex.ornl.gov/hpdm/installer/Fans.zip
URL: https://hpdmflex.ornl.gov/hpdm/installer/Lines.zip
```

**Task:** Use Playwright to navigate to the download page and download all files.
The ZIP contains the Fortran executable, Excel VBA templates with all field definitions,
and example HPDATA.DAT files.

**Priority:** CRITICAL. The Excel templates are the Rosetta Stone — they define every
input variable, its units, valid ranges, and default values.

### 1.2 Scrape Component-Level Example Inputs

For each standalone component model, load the web wizard, capture the default inputs,
and run the model to capture outputs.

**Component configurations to scrape:**

| Config ID | What it is | Why |
|-----------|-----------|-----|
| `Compressor10` | AHRI 10-coeff compressor map | Get real coefficient sets |
| `CompressorEff` | Simple efficiency compressor | Baseline comparison |
| `Compressor10Eff` | 10-coeff + efficiency calc | Volumetric/isentropic η extraction |
| `CondenserFtcSimple` | Fin-tube condenser | HX geometry + HTC correlations |
| `EvaporatorFtcSimple` | Fin-tube evaporator | Same |
| `CondenserMHX` | Microchannel condenser | Needed for Li & Shen paper |
| `EvaporatorMHX` | Microchannel evaporator | Same |
| `CondenserBHP` | Brazed-plate condenser | Water-side HX |
| `CondenserTUBinTUB` | Tube-in-tube condenser | Fluted tube model |
| `LineModel` | Discharge/liquid line | Line charge inventory |

**Scraping procedure per component:**

```
1. Navigate to: https://hpdmflex.ornl.gov/hpdm/wizard/HPDMWiz.php?Configuration=<CONFIG_ID>
2. Wait for the input form to load
3. Extract all input fields: name, value, units, attribute (i/g/o/r)
4. Click "Run" / "Submit" to execute the model
5. Extract the output page: all calculated values
6. Click "Download" to get the JSON/dat input file
7. Store: inputs.json, outputs.json, raw_input.dat per component
```

### 1.3 Scrape System-Level Configurations

**Priority configurations** (selected to cover the paper's validation systems and
the most common residential/commercial cases):

| Config ID | Description | Priority |
|-----------|-------------|----------|
| `ScFtcs` | Residential space cooling, FT coils | HIGH — baseline residential |
| `ScMhxs` | Residential SC, MHX coils | HIGH — matches Li & Shen split system |
| `ShFtcs` | Space heating, FT coils | HIGH — heating mode validation |
| `Rtu1SysFtcs` | Commercial RTU, 1 system | HIGH — matches Li & Shen RTU |
| `ScFtcsFEO` | Residential SC, fixed orifice + accumulator | MEDIUM — tests charge model |
| `ShViEcDownsplit` | Vapor injection HP | LOW — advanced config |

**Scraping procedure per system:**

```
1. Load the configuration wizard page
2. Extract ALL input fields across all component tabs
3. Run with default inputs → capture outputs
4. Sweep outdoor temperature: 65, 75, 85, 95, 105 °F
   - For each T_outdoor: modify input, run, capture outputs
5. Sweep charge level (if charge-specifying mode available):
   - Nominal × {0.7, 0.85, 1.0, 1.15, 1.30}
6. Download each configuration file set
7. Store: config_<ID>_T<temp>_C<charge>.json
```

### 1.4 Build a Parametric Ground-Truth Database

From the sweeps above, build a structured CSV/Parquet database:

```
columns: config, T_outdoor, T_indoor, charge_kg, refrigerant,
         Q_cooling_W, Q_heating_W, COP, P_compressor_W,
         P_evap_Pa, P_cond_Pa, T_discharge_K, subcooling_K,
         superheat_K, m_dot_kg_s, charge_condenser_kg,
         charge_evaporator_kg, charge_total_kg, ...
```

This becomes the regression test suite for every module.

---

## 2. Architecture of `pyhpdm`

```
pyhpdm/
├── properties/
│   ├── refrigerant.py        # CoolProp wrapper (R410A, R22, R134a, R32, CO2, ...)
│   └── air.py                # Moist air psychrometrics
├── components/
│   ├── compressor.py          # 10-coeff AHRI map + efficiency model + VS interpolation
│   ├── heat_exchanger/
│   │   ├── base.py            # Segment-by-segment ε-NTU framework
│   │   ├── fin_tube.py        # FTC condenser/evaporator
│   │   ├── microchannel.py    # MHX condenser/evaporator
│   │   ├── brazed_plate.py    # BHP condenser/evaporator
│   │   ├── tube_in_tube.py    # Fluted tube-in-tube
│   │   ├── air_side.py        # Gray-Webb + wavy/louvered corrections
│   │   ├── refrigerant_side.py # Flow-pattern HTC + pressure drop
│   │   └── void_fraction.py   # Rouhani-Axelsson, homogeneous, Premoli, etc.
│   ├── expansion.py           # TXV, orifice, EEV, capillary tube
│   ├── accumulator.py         # J-tube accumulator (Domanski 1985)
│   ├── fan.py                 # Fan/pump power (fan laws + motor efficiency)
│   └── line.py                # Refrigerant line (liquid, suction, discharge)
├── charge/
│   ├── inventory.py           # Charge inventory integration over all components
│   ├── tuning.py              # Two-point charge tuning (Shen et al. 2009)
│   └── pump_down.py           # Transient pump-down simulation (Li & Shen 2024)
├── solver/
│   ├── system.py              # Newton-Raphson system solver
│   ├── cycle.py               # Vapor compression cycle (connect components)
│   └── configs.py             # Pre-built system configurations (ScFtcs, Rtu1SysFtcs, ...)
├── io/
│   ├── hpdata.py              # Read/write HPDATA.DAT format
│   └── web_scraper.py         # Playwright automation for HPDM web
└── tests/
    ├── test_compressor.py
    ├── test_hx.py
    ├── test_system.py
    └── ground_truth/          # Scraped HPDM outputs
```

---

## 3. Implementation Phases

### Phase 1: Data Collection & Input Format Reverse-Engineering

**Duration estimate:** 1 session

**Tasks:**

1. **Browser automation setup**
   - Install Playwright in Claude Code
   - Write `web_scraper.py` with functions:
     - `download_installer()` — fetch HPDM.Zip and template ZIPs
     - `scrape_component(config_id)` — load wizard, extract all fields, run, capture output
     - `scrape_system(config_id, T_outdoor_list, charge_list)` — parametric sweeps
   - Handle the wizard's JavaScript: collapsible categories, tabbed component editors,
     dynamic form fields

2. **Parse HPDATA.DAT format**
   - From the downloaded Excel templates, extract: field names, positions, units, ranges
   - Build `hpdata.py` reader/writer
   - Parse the variable attribute system: i (input), g (guess), o (output), r (regular), t (transfer)

3. **Scrape component-level ground truth**
   - Run all 12 component configs with defaults
   - Store raw HTML outputs + parsed JSON

4. **Scrape system-level ground truth**
   - `ScFtcs` and `Rtu1SysFtcs` with temperature sweeps
   - Download the configuration files

**Deliverable:** `ground_truth/` directory with parsed inputs and outputs for all target configs.

### Phase 2: Refrigerant Properties & Compressor Model

**Duration estimate:** 1 session

**Tasks:**

1. **Refrigerant property wrapper** (`properties/refrigerant.py`)
   - CoolProp wrapper handling R410A pseudo-pure fluid quirks (Q=0 not Q=0.5)
   - All properties needed downstream: ρ, h, s, T_sat, P_sat, σ, μ, cp, cv
   - Validate against REFPROP 9.0 values (extract from HPDM if available)
   - Special handling near critical point (HPDM uses hybrid lookup tables)

2. **Moist air psychrometrics** (`properties/air.py`)
   - h_air(T_db, W), W_sat(T_db, P), T_wb, T_dp
   - Enthalpy-based wet coil driving potential (Braun et al. 1989)

3. **Compressor model** (`components/compressor.py`)
   - AHRI 10-coefficient polynomial:
     `Y = C1 + C2·Te + C3·Tc + C4·Te² + C5·Te·Tc + C6·Tc² + C7·Te³ + C8·Tc·Te² + C9·Te·Tc² + C10·Tc³`
   - Inputs: Te, Tc in °F (AHRI convention), outputs: ṁ [lbm/h], P [W]
   - Superheat correction: `m_actual = m_map · (v_ref/v_actual) · F_mass` where `F_mass = 0.75`
   - Variable-speed: linear interpolation between discrete-speed maps
   - Efficiency model: derive η_isen and η_vol from map outputs
   - Volumetric efficiency: `η_vol = f(PR, P_discharge)` — linear in PR, quadratic in P_d

4. **Validate compressor**
   - Compare against `Compressor10` component output from Phase 1
   - Sweep (Te, Tc) grid, check ṁ and P within 0.5% of HPDM

**Deliverable:** Compressor module passing ground-truth validation.

### Phase 3: Heat Exchanger Model (The Hard Part)

**Duration estimate:** 2-3 sessions

**Tasks:**

1. **Segment-by-segment framework** (`heat_exchanger/base.py`)
   - Divide HX into N segments along refrigerant flow path
   - Per-segment ε-NTU calculation:
     - Dry coil: `Q_max = C_min · (T_h,i - T_c,i)`, `ε = 1 - exp(-NTU)`
     - Wet coil: `Q_max = ṁ_a · (h_a,i - h_s,evap)`, enthalpy-based (Braun et al. 1989)
   - Track refrigerant state: superheated → two-phase → subcooled
   - Phase-change detection at segment boundaries
   - Refrigerant pressure drop accumulated segment-by-segment

2. **Air-side heat transfer & pressure drop** (`heat_exchanger/air_side.py`)
   - Baseline: Gray & Webb (1986) plain-fin correlations
     - j-factor (Colburn): `j = f(Re_Dc, N_rows, tube_pitch, fin_pitch, ...)`
     - f-factor (friction): similar form
   - Wavy fin correction: Beecher & Fagan (1987) multipliers
   - Louvered fin correction: Makayama & Xu (1983) multipliers
   - Wang, Lee, Chang & Lin (1999) correlation for louvered fins (used in the charge paper)
   - Entrance/exit losses: Kays & London (1974) expansion/contraction coefficients

3. **Refrigerant-side heat transfer & pressure drop** (`heat_exchanger/refrigerant_side.py`)
   - Single-phase (superheated/subcooled):
     - Dittus-Boelter (turbulent): `Nu = 0.023 · Re^0.8 · Pr^n`
     - Gnielinski (transitional)
   - Two-phase condensation:
     - Shah (1979) or Cavallini-Zecchin for in-tube condensation
     - Flow-pattern-specific: annular, stratified, intermittent
   - Two-phase evaporation:
     - Gungor-Winterton (1986) or Liu-Winterton
     - Nucleate + convective boiling contributions
   - Pressure drop:
     - Single-phase: Darcy-Weisbach + Churchill (1977) friction factor
     - Two-phase: Lockhart-Martinelli or Friedel (1979)
     - Acceleration pressure drop in evaporator

4. **Void fraction models** (`heat_exchanger/void_fraction.py`)
   - Rouhani-Axelsson (1970) — HPDM default
   - Homogeneous — baseline comparison
   - Premoli et al. (1971) — alternative
   - CISE (Premoli) drift-flux
   - Rice (1987) simplified analytical method (HPDM built-in)

5. **Fin-tube HX** (`heat_exchanger/fin_tube.py`)
   - Geometry: tube OD/ID, # tubes, # rows, # circuits, fin pitch, fin thickness
   - Circuitry: simple parallel (Mark III-VII default) or arbitrary (Flex HPDM)
   - Air-side: annular fin efficiency, fin-tube contact resistance
   - Map tube layout to segment connectivity

6. **Microchannel HX** (`heat_exchanger/microchannel.py`)
   - Geometry: # tubes, # ports per tube, port hydraulic diameter, tube width/height
   - Louvered fins between flat tubes
   - Different HTC correlations for micro-scale channels (Kim & Mudawar 2013)

7. **Validate HX models**
   - Compare against `CondenserFtcSimple`, `EvaporatorFtcSimple`, `CondenserMHX`, `EvaporatorMHX`
   - Key outputs: capacity (Q), outlet temperatures, pressure drop, charge inventory
   - Acceptance: within 3% of HPDM on capacity, within 5% on charge

**Deliverable:** All HX models passing component-level ground-truth validation.

### Phase 4: Charge Inventory & Expansion Devices

**Duration estimate:** 1 session

**Tasks:**

1. **Charge inventory** (`charge/inventory.py`)
   - Integrate refrigerant mass over all components:
     - Condenser: sum over segments (void fraction model in two-phase zone)
     - Evaporator: same
     - Lines: liquid line (liquid density × volume), suction line (vapor), discharge line (superheated vapor)
     - Compressor shell: approximate from displacement + clearance volume
     - Accumulator: j-tube model (Domanski 1985, 1986)
   - Total charge = Σ(component charges)

2. **Two-point charge tuning** (`charge/tuning.py`)
   - Shen et al. (2009) method:
     `ΔM_liqL = C + k_liqL · L_liq`
     `M_corrected = M_simulated + ΔM_liqL`
   - Fit C and k_liqL from two operating points
   - Validate: error in condenser charge should be < 5% across operating range

3. **Expansion device models** (`components/expansion.py`)
   - Thermostatic expansion valve (TXV): superheat-controlling, explicit model from ORNL/CON-343
   - Fixed orifice (short tube): ASHRAE orifice flow correlations
   - Electronic expansion valve (EEV): ideal superheat controller
   - Capillary tube: ASHRAE capillary tube sizing
   - Each model: given (P_upstream, h_upstream, P_downstream) → ṁ_expansion

4. **Accumulator** (`components/accumulator.py`)
   - J-tube model from Domanski (1985)
   - Liquid level tracking
   - Effect on active charge vs. stored charge

5. **Validate charge inventory**
   - Compare total system charge against HPDM output for `ScFtcs` and `ScFtcsFEO`
   - Acceptance: within 5% of HPDM charge prediction

**Deliverable:** Charge model passing system-level validation.

### Phase 5: System Solver

**Duration estimate:** 1-2 sessions

**Tasks:**

1. **Vapor compression cycle** (`solver/cycle.py`)
   - Connect components: compressor → condenser → expansion → evaporator → (accumulator →) compressor
   - State points at each junction: (T, P, h, ṁ)
   - Energy balance: Q_evap + W_comp = Q_cond (+ losses)
   - Mass balance: ṁ is uniform around the loop (single-speed, single-circuit)

2. **Newton-Raphson solver** (`solver/system.py`)
   - Inner loop: given (P_evap, P_cond), solve for:
     - Compressor: ṁ, W, T_discharge from map
     - Condenser: Q_cond, T_out, subcooling from ε-NTU segments
     - Expansion device: ṁ_exp as function of pressure drop
     - Evaporator: Q_evap, T_out, superheat from ε-NTU segments
     - Residuals: ṁ_comp = ṁ_exp, energy balance
   - Outer loop (charge-balancing mode):
     - Given total charge, adjust subcooling (or superheat) until
       calculated charge inventory = specified charge
   - Convergence: relative tolerance 1e-4 on all residuals

3. **Solution logic** (following Figures 14-15 of ORNL/CON-343)
   - Charge-determining mode: specify superheat + subcooling → calculate required charge
   - Charge-balancing mode: specify charge → iterate on subcooling
   - High-side-determined vs low-side-determined

4. **System configurations** (`solver/configs.py`)
   - `ScFtcs`: VS compressor + FT condenser + TXV + FT evaporator
   - `ScMhxs`: VS compressor + MHX condenser + TXV + MHX evaporator
   - `Rtu1SysFtcs`: Commercial RTU, single system
   - Factory functions that wire components with correct geometry defaults

5. **Validate system solver**
   - Run `ScFtcs` at AHRI A/B conditions (95/82°F outdoor, 80/67°F indoor)
   - Compare: COP, capacity, pressures, temperatures, charge
   - Sweep outdoor temperature: check trends match HPDM
   - Acceptance: within 3% on COP and capacity, 5% on pressures

**Deliverable:** Full system solver reproducing HPDM outputs for residential and commercial configs.

### Phase 6: Pump-Down Charge Prediction (Target Paper)

**Duration estimate:** 1 session

**Tasks:**

1. **Pump-down simulator** (`charge/pump_down.py`)
   - Use calibrated condenser model from Phase 3-4 for static charge
   - Transient LP-side model: constant-volume depletion
   - Compressor mass flow from AHRI map at each (P_suc, P_dis) time step
   - 4-way valve leakage: `VFR = Cv · √ΔP`, `ṁ = VFR · ρ_discharge`
   - Integration: `Charge_total = M_cond_static + ∫(ṁ_comp - ṁ_valve) dt`

2. **Reproduce paper results**
   - Residential 3-ton split system (Table 1 geometry, Table 2 test matrix)
   - Commercial 4-ton RTU (Table 3 test matrix)
   - Generate Figures 3-9 and 11 analogs
   - Target: prediction within 6% of actual charge (paper's reported accuracy)

**Deliverable:** Charge prediction matching paper's validation results.

---

## 4. Browser Automation Details

### 4.1 Playwright Setup

```bash
pip install playwright
playwright install chromium
```

### 4.2 HPDM Web Interface Structure

The web wizard at `hpdmflex.ornl.gov` is a PHP application. Key observations:

- **Welcome page** has a collapsible tree of categories/configurations
- Each configuration links to `HPDMWiz.php?Configuration=<ID>`
- The wizard page has tabbed panels for each component
- Each tab contains a table of input variables with:
  - Variable name (often with subscripts)
  - Value (editable input field)
  - Unit
  - Attribute dropdown (i/g/o/r/t)
- "Run" button submits the form via POST and returns results
- "Download" button exports the input file
- "Upload" button loads a saved configuration

### 4.3 Scraper Architecture

```python
# web_scraper.py — skeleton

class HPDMScraper:
    """Automate the HPDM web interface with Playwright."""

    BASE_URL = "https://hpdmflex.ornl.gov/hpdm/wizard"

    async def init(self):
        self.browser = await playwright.chromium.launch(headless=True)
        self.page = await self.browser.new_page()

    async def download_installers(self, out_dir):
        """Download HPDM.Zip and all template ZIPs."""
        ...

    async def load_configuration(self, config_id: str):
        """Navigate to a configuration wizard and wait for form load."""
        await self.page.goto(f"{self.BASE_URL}/HPDMWiz.php?Configuration={config_id}")
        await self.page.wait_for_load_state("networkidle")

    async def extract_inputs(self) -> dict:
        """Extract all input fields from the current wizard page."""
        # Find all input tables, iterate rows
        # Return: {component: {var_name: {value, unit, attribute}}}
        ...

    async def modify_input(self, var_name: str, value: str):
        """Change an input field value."""
        ...

    async def run_model(self) -> dict:
        """Click Run, wait for results, extract output values."""
        ...

    async def download_config(self, out_path: str):
        """Click Download to save the configuration file."""
        ...

    async def sweep_temperature(self, config_id, T_outdoor_list):
        """Run a configuration at multiple outdoor temperatures."""
        results = []
        await self.load_configuration(config_id)
        for T in T_outdoor_list:
            await self.modify_input("T_outdoor", str(T))
            output = await self.run_model()
            output["T_outdoor"] = T
            results.append(output)
        return results
```

### 4.4 Data Extraction Strategy

The output page likely contains:
- System-level results: COP, capacity, power, pressures, temperatures
- Component-level results: per-component heat transfer, pressure drop, charge
- Possibly: segment-by-segment HX data (if detailed output is enabled)

We need to identify the HTML structure of the results page and write robust
extraction logic. The first scraping pass should save raw HTML for manual inspection.

### 4.5 Rate Limiting & Politeness

- Add 2-3 second delays between requests
- Don't hammer the server with parallel requests
- The site note says "373,786 visits since 1998" — it's a small research server
- Download files once, cache locally

---

## 5. Key References to Fetch and Parse

These documents contain equations we need. Priority order:

| # | Document | Contains | How to get |
|---|----------|----------|-----------|
| 1 | ORNL/CON-343 (Rice 2001) | Full Mark IV user's guide with HPDATA format, all equations | Already fetched (814355.pdf) |
| 2 | HPDM.Zip desktop installer | Fortran executable + Excel templates with field definitions | Browser download |
| 3 | Shen, Braun & Groll (2009) IJR 32(7) | Charge tuning method, off-design improvements | ScienceDirect (need access) |
| 4 | Gray & Webb (1986) | Baseline air-side HTC correlations for plain fins | Standard reference |
| 5 | Rouhani & Axelsson (1970) IJHMT | Void fraction model | Standard reference |
| 6 | Wang, Lee, Chang & Lin (1999) IJHMT | Louvered fin HTC correlation | Standard reference |
| 7 | Gungor & Winterton (1986) | Two-phase evaporation HTC | Standard reference |
| 8 | Shah (1979) | In-tube condensation HTC | Standard reference |
| 9 | Friedel (1979) | Two-phase pressure drop | Standard reference |
| 10 | Li & Shen (2024) | Pump-down charge prediction (target paper) | Already fetched |

---

## 6. Validation Strategy

### 6.1 Unit-Level Validation

Each component module is validated independently against HPDM component-mode outputs.

| Module | Test | Metric | Tolerance |
|--------|------|--------|-----------|
| Refrigerant props | Compare T_sat, P_sat, ρ, h vs REFPROP/HPDM | Relative error | < 0.1% |
| Compressor | ṁ and P at (Te, Tc) grid | Relative error | < 0.5% |
| Air-side HTC | j-factor at Re range | Relative error | < 2% |
| Refrigerant-side HTC | h_tp at quality range | Relative error | < 5% |
| Void fraction | α at quality range | Absolute error | < 0.03 |
| Condenser capacity | Q_cond at standard conditions | Relative error | < 3% |
| Evaporator capacity | Q_evap at standard conditions | Relative error | < 3% |
| Condenser charge | M_cond at standard conditions | Relative error | < 5% |

### 6.2 System-Level Validation

| Test | Config | Conditions | Metrics | Tolerance |
|------|--------|-----------|---------|-----------|
| AHRI A cooling | ScFtcs | 95/67°F | COP, Q_cool, W_comp | < 3% |
| AHRI B cooling | ScFtcs | 82/67°F | COP, Q_cool, W_comp | < 3% |
| Temperature sweep | ScFtcs | 65-105°F | COP, Q trends | < 5% |
| Charge sweep | ScFtcsFEO | 0.7-1.3× nominal | Subcooling, superheat | < 1 K |
| RTU cooling | Rtu1SysFtcs | 95/67°F | COP, Q_cool | < 3% |
| Charge inventory | ScFtcs | Nominal | Total charge | < 5% |

### 6.3 Paper Reproduction Validation

| Test | System | Condition | Metric | Target |
|------|--------|-----------|--------|--------|
| Pump-down duration | 3-ton split | 71°F, 7 lbm | Duration [s] | < 100 s (Fig 8) |
| Pump-down duration | 3-ton split | 95°F, 7 lbm | Duration [s] | < 100 s (Fig 8) |
| Charge prediction | 3-ton split | All Table 2 | Charge error | < 6% |
| Charge prediction | 4-ton RTU | All Table 3 | Charge error | < 6% |
| η_vol profile | 3-ton split | 71°F, 7 lbm | Shape match | Qualitative (Fig 3) |
| Pressure profile | 3-ton split | 71°F, 7 lbm | Shape match | Qualitative (Fig 5) |

---

## 7. Risk Register

| Risk | Impact | Mitigation |
|------|--------|-----------|
| HPDM web interface changes or goes down | Blocks data collection | Cache everything locally; download desktop version as backup |
| CoolProp ≠ REFPROP near critical point | Property errors propagate | Validate carefully; implement hybrid lookup if needed |
| HPDM uses proprietary refrigerant data | Can't reproduce exactly | Use CoolProp + document deviations |
| Compressor map coefficients are synthetic (not from real hardware) | Validation is circular | Scrape real maps from HPDM examples; cross-check with AHRI directories |
| HX model has too many correlations to get right simultaneously | Slow convergence of implementation | Build incrementally: get plain fin + Dittus-Boelter working first, add complexity |
| System solver convergence issues | Can't reproduce system-level results | Start with charge-determining mode (simpler); add charge-balancing later |
| Charge paper doesn't publish enough detail to reproduce exactly | Can't hit 6% target | Use HPDM for the condenser charge part (their method); focus on pump-down integration |

---

## 8. Execution Order for Claude Code

```
Session 1: Data Collection
  ├── Install Playwright
  ├── Write web_scraper.py
  ├── Download HPDM.Zip + templates
  ├── Scrape all component configs (12 components)
  ├── Scrape ScFtcs + Rtu1SysFtcs with temperature sweeps
  └── Parse and store ground truth

Session 2: Properties + Compressor
  ├── Implement refrigerant.py with CoolProp
  ├── Implement air.py psychrometrics
  ├── Implement compressor.py (10-coeff + VS interpolation)
  ├── Validate compressor against scraped Compressor10 output
  └── Write tests

Session 3: Heat Exchanger Core
  ├── Implement base.py segment-by-segment framework
  ├── Implement air_side.py (Gray-Webb)
  ├── Implement refrigerant_side.py (Dittus-Boelter + Shah + Gungor-Winterton)
  ├── Implement void_fraction.py (Rouhani-Axelsson)
  ├── Implement fin_tube.py
  └── Validate against CondenserFtcSimple + EvaporatorFtcSimple

Session 4: HX Extensions + Charge
  ├── Implement microchannel.py
  ├── Implement brazed_plate.py (if needed for paper)
  ├── Implement charge/inventory.py
  ├── Implement charge/tuning.py
  ├── Validate charge against scraped system outputs
  └── Implement expansion.py (TXV at minimum)

Session 5: System Solver
  ├── Implement cycle.py (component wiring)
  ├── Implement system.py (Newton-Raphson)
  ├── Implement configs.py (ScFtcs, Rtu1SysFtcs)
  ├── Validate full system against HPDM outputs
  └── Debug convergence issues

Session 6: Pump-Down & Paper Reproduction
  ├── Implement pump_down.py using calibrated models
  ├── Set up residential + commercial system geometries from paper
  ├── Run pump-down simulations for full test matrices
  ├── Generate paper figure analogs
  └── Compare: target < 6% charge prediction error
```

---

## 9. Open Questions to Resolve During Execution

1. **What exact air-side correlation does HPDM Flex use for louvered fins?**
   The Mark IV guide mentions Gray-Webb + Makayama-Xu, but the charge paper
   cites Wang et al. (1999). Need to check which is used in the current web version.

2. **What void fraction model is the default in HPDM Flex?**
   The Mark IV guide offers multiple options (MVOID parameter). The charge paper
   uses Rouhani-Axelsson. Need to confirm the Flex default.

3. **How does HPDM handle microchannel HX charge?**
   Microchannel ports have very small hydraulic diameters (~0.7 mm per the paper).
   The void fraction model may need surface-tension-dominated corrections.

4. **What is the exact form of the condenser charge calibration equation?**
   Shen et al. (2009) describe `ΔM = C + k·L_liq`, but is L_liq in meters,
   fraction of total length, or number of segments?

5. **Does the HPDM web interface expose segment-by-segment output?**
   If yes, this would allow direct validation of internal HX calculations.
   Need to check during scraping.
