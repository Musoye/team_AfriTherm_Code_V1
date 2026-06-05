# Team AfriTherm — SPE Geothermal Design Challenge

**Challenge:** Design a geothermal-based heating and cooling system for a mixed urban district in the Utrecht region of the Netherlands, using the Rotliegend Slochteren sandstone reservoir.  
**Target:** ≥ 10 MWth heating demand | ≥ 5 MWth cooling demand  
**Reservoir:** Rotliegend Slochteren Sandstone Formation, Utrecht Region  
**Wells assessed:** BLT-01, JUT-01, EVD-01, PKP-01

---

## Repository Structure

```
team_AfriTherm_Code_V1/
│
├── tvd_conversion.py              # Step 0 — depth correction (run this first)
├── power_calculation.py           # Challenge 1 — geothermal power assessment
├── surface_system_design.py       # Challenge 2 — surface system design + LCoE
├── bonus_ai_workflow.py           # Bonus — full automated pipeline with AI summary
│
├── data/
│   ├── ThermoGIS_Data.xlsx        # Reservoir properties (P90/P50/P10) per well
│   ├── Lithostratigraphic_Data.xlsx  # Formation tops and bases (AH depth)
│   ├── Well_Path_Data.xlsx        # Directional survey — AH depth to TVD lookup
│   └── target_lithologies.csv    # Gamma-ray and bulk density logs (Slochteren)
│
└── outputs/
    ├── target_lithologies_tvd_corrected.csv   # TVD-corrected log data
    ├── geothermal_assessment.csv              # Per-well power results (P90/P50/P10)
    ├── surface_system_design.csv              # Design parameters and LCoE
    ├── pipeline_results.csv                   # Full automated pipeline output
    └── ai_generated_report.txt               # AI-written assessment summary
```

---

## Installation

```bash
pip install pandas numpy openpyxl anthropic
```

Place all four data files in the same directory as the scripts before running.

---

## How to Run — Step by Step

Run the scripts in this exact order. Each one feeds into the next.

```bash
python tvd_conversion.py          # Step 0 — must run first
python power_calculation.py       # Challenge 1
python surface_system_design.py   # Challenge 2
python bonus_ai_workflow.py       # Bonus (needs ANTHROPIC_API_KEY)
```

For the bonus script, set your API key first:

```bash
# Mac / Linux
export ANTHROPIC_API_KEY="your-key-here"

# Windows
set ANTHROPIC_API_KEY=your-key-here
```

---

## Script 1 — `tvd_conversion.py`

**What it solves:** All four wells are deviated (drilled at an angle). Raw depth values in the lithostratigraphic data are Along-Hole (AH) depth — the physical length of drill pipe used — not the actual depth underground. Temperature increases with true vertical depth (TVD), not pipe length, so every thermal calculation breaks if AH depth is used directly.

**Why this matters for the challenge:** The raw `target_lithologies.csv` has a `depth_tvd_m` column that is entirely empty (3,455 NaN values). More critically, the `formation_top_tvd` and `formation_base_tvd` columns appear to contain TVD values but are actually AH depths — confirmed by cross-referencing with the well path survey. The largest error is PKP-01, where AH depth overstates the true depth by **323 m**, which would inflate temperature estimates by ~10°C and power calculations proportionally.

**What it does:**

1. Loads the directional survey tables from `Well_Path_Data.xlsx` — one sheet per well, each containing (AH depth, TVD) pairs measured by gyroscope tools during drilling.
2. Reads the Slochteren Formation top and base for each well from `Lithostratigraphic_Data.xlsx` (in AH depth).
3. Converts those formation boundaries to TVD via **linear interpolation** between the two nearest survey stations.
4. Fills `depth_tvd_m` for every log row in `target_lithologies.csv` by linearly spacing samples within the corrected [TVD top, TVD base] interval. This is valid because well logs are sampled at uniform depth intervals (0.1–0.5 m steps).
5. Overwrites `formation_top_tvd` and `formation_base_tvd` with the corrected values.

**TVD corrections applied:**

| Well   | AH Top (m) | AH Base (m) | TVD Top (m) | TVD Base (m) | Correction |
|--------|-----------|------------|------------|-------------|------------|
| BLT-01 | 1,924     | 2,053      | 1,862      | 1,985       | **−62 m**  |
| JUT-01 | 1,660     | 1,787      | 1,655      | 1,781       | −4 m       |
| EVD-01 | 1,788     | 1,866      | 1,783      | 1,860       | −5 m       |
| PKP-01 | 2,531     | 2,604      | 2,207      | 2,272       | **−323 m** |

**Reads:** `Well_Path_Data.xlsx`, `Lithostratigraphic_Data.xlsx`, `target_lithologies.csv`  
**Writes:** `target_lithologies_tvd_corrected.csv`

---

## Script 2 — `power_calculation.py`

**What it solves:** Using the corrected TVD depths and ThermoGIS reservoir data, this script answers the core Challenge 1 question: can the Rotliegend reservoir supply the 10 MWth heating target, and if not, by how much does it fall short?

**The thermal power formula:**

```
Power (MW) = [Flow (m³/h) ÷ 3,600] × ρ × c_p × ΔT ÷ 10⁶

Where:
  ρ    = 1,000 kg/m³  (water density)
  c_p  = 4,186 J/kg·°C  (specific heat of water — physical constant)
  ΔT   = reservoir temperature − 30°C  (reinjection temp, Dutch industry standard)
```

The script recalculates power from first principles rather than using ThermoGIS's pre-computed power column. This serves two purposes: it verifies the ThermoGIS figures, and it allows the injection temperature assumption to be changed for sensitivity analysis.

**What it does:**

1. Parses `ThermoGIS_Data.xlsx` — one sheet per well, each containing P90/P50/P10 ranges for flow rate, temperature, permeability, porosity, thickness, and transmissivity.
2. Calculates thermal power at P90, P50, and P10 for each well independently.
3. Sums combined output and compares to the 10 MWth target.
4. Calculates the electricity input a COP-4 heat pump needs to bridge the shortfall.
5. Explains why EVD-01 and PKP-01 produce zero power despite one of them being the hottest well.

**Results — thermal power per well:**

| Well   | TVD (m) | Temp (°C) | Perm P50 (mD) | Flow P50 (m³/h) | P90 MW | P50 MW  | P10 MW  |
|--------|---------|-----------|--------------|----------------|--------|---------|---------|
| BLT-01 | 1,862   | 77        | 82           | 105            | 0.93   | **5.74**| 25.63   |
| JUT-01 | 1,655   | 72        | 40           | 55             | 1.27   | **2.69**| 5.37    |
| EVD-01 | 1,783   | 72        | 6            | 0              | 0.00   | 0.00    | 0.00    |
| PKP-01 | 2,207   | 88        | 1            | 0              | 0.00   | 0.00    | 0.00    |
| **TOTAL** |      |           |              |                | **2.20** | **8.43** | **31.00** |

**Challenge 1 finding:** Geothermal alone supplies **8.43 MWth at P50** — 84% of the heating target. The 1.57 MWth gap is bridged by a heat pump requiring only **0.40 MW of electrical input** (COP = 4.0). EVD-01 has 6 mD permeability — too tight for flow. PKP-01 at 88°C is the hottest well but has 1 mD permeability and delivers zero flow at all scenarios.

**Reads:** `ThermoGIS_Data.xlsx`  
**Writes:** `geothermal_assessment.csv`

---

## Script 3 — `surface_system_design.py`

**What it solves:** Challenge 2. Takes the 8.43 MWth geothermal base load from Script 2 and designs the complete above-ground system that delivers exactly 10 MWth heating and 5 MWth cooling to the neighbourhood, then calculates the LCoE to show economic viability.

**Design logic — always work from demand backwards:**

```
What does the district need?   →  10 MWth heat + 5 MWth cooling
What does geology supply?      →  8.43 MWth heat, 0 MWth cooling
What fills the heat gap?       →  water-to-water heat pump (COP 4.0)
What delivers the cooling?     →  free cooling via injection loop + absorption chiller
How do we handle peaks cheaply? →  803 m³ thermal storage tank (28 MWh)
What covers extreme cold days? →  2,000 m² solar thermal backup
What does this cost per MWh?   →  LCoE calculation
```

**The four components:**

**1. Water-to-water heat pump (1.6 MWth output)**  
Draws partially-cooled geothermal return water at ~40°C as heat source, upgrades it to 70°C for the district heating network. At COP 4.0, only 0.40 MW of electricity is needed to deliver 1.6 MW of heat — the rest comes from the geothermal loop at no fuel cost. The pump is sized at 8 MWth capacity to handle the P90 worst case where geothermal falls to 2.20 MWth.

**2. Cooling system — 5 MWth total**  
- **3 MWth free cooling:** After heat extraction, injection return water sits at ~30°C. In summer, buildings at 22–26°C are warmer than this return water, so heat flows from building to water naturally — no compressor, near-zero operating cost.  
- **2 MWth absorption chiller:** Driven by low-grade geothermal heat (not grid electricity), COP 0.7. Using waste heat from the geothermal source eliminates ~€257,000/year in electricity costs vs a conventional vapour-compression chiller.

**3. Thermal storage tank (28 MWh / ~803 m³)**  
Residential demand peaks sharply at 07:00–09:00 and drops overnight. Without storage, all equipment would be oversized for the peak. The tank stores excess heat overnight and releases it during peaks — this "peak shaving" cuts effective equipment sizing from ~12 MWth to ~7 MWth, saving an estimated €800k–1.2M in capital costs and reducing LCoE by ~€2–3/MWh.

**4. Solar thermal backup (2 MWth peak / 2,000 m²)**  
Provides resilience at P90 when geothermal + heat pump may fall short during extended cold snaps. Connects directly to the storage tank for pre-charging. Solar thermal chosen over PV because the system already distributes energy as hot water — direct heat conversion (50–60% efficiency) outperforms PV-to-electricity-to-heatpump (net ~20–25%).

**LCoE calculation:**

| Item | Value |
|------|-------|
| Total CAPEX | €12.8M |
| Annual OPEX | €560k/year |
| Discount rate | 5% |
| Project lifetime | 30 years |
| Capital Recovery Factor | 0.0651 |
| Annual energy delivered | 47,500 MWh/year |
| **LCoE** | **€29.3/MWh** |

| Benchmark | LCoE | CO₂ |
|-----------|------|-----|
| Natural gas district heating | ~€70/MWh | 0.18 kg/kWh |
| All-electric heat pump | ~€110/MWh | 0.07 kg/kWh |
| **This system** | **€29.3/MWh** | **~0.01 kg/kWh** |

**Reads:** No input files — all parameters are hard-coded with cited sources  
**Writes:** `surface_system_design.csv`

---

## Script 4 — `bonus_ai_workflow.py`

**What it solves:** The three scripts above require manual execution and produce results across multiple output files. If any input data changes, the whole analysis must be rerun by hand. This script automates the complete pipeline in a single command and calls the Claude AI API to generate a plain-English interpretation of the results — the AI-assisted workflow the bonus challenge asks for.

**What it does:**

1. **Runs the full pipeline automatically** — TVD conversion, power calculation, and system design numbers in sequence, without needing to run separate scripts.
2. **Passes all computed results to the Claude API** as a structured JSON payload and prompts it to write a professional report section (300–400 words) covering geological findings, gap analysis, system design rationale, LCoE context, and P90 risk.
3. **Saves two output files:** `pipeline_results.csv` (all computed numbers for reproducibility) and `ai_generated_report.txt` (the AI-written summary).

**Why this is genuine AI integration, not a wrapper:**  
The pipeline computes real numbers from the real data files, formats them as structured JSON, and sends that JSON to the model. The model interprets calculated outputs — not generic prompts. The result is a report section grounded in the actual reservoir data, not a generic description of geothermal energy.

**Pipeline flow:**

```
Well_Path_Data.xlsx ──┐
Lithostratigraphic  ──┼──► TVD correction ──► power calculation ──► system design
ThermoGIS_Data.xlsx ──┘                                                    │
                                                                            ▼
                                                               Google Gemini API (gemini-2.5-pro)
                                                                            │
                                                                            ▼
                                                               ai_generated_report.txt
```

**Reads:** `Well_Path_Data.xlsx`, `Lithostratigraphic_Data.xlsx`, `ThermoGIS_Data.xlsx`  
**Writes:** `pipeline_results.csv`, `ai_generated_report.txt`  
**Requires:** `GEMINI_API_KEY` environment variable

---

## Key Findings Summary

| Question | Answer |
|----------|--------|
| How many wells are viable? | 2 of 4 — BLT-01 and JUT-01 |
| Why are EVD-01 and PKP-01 excluded? | Permeability ≤ 6 mD — rock too tight for flow |
| What does PKP-01's 88°C temperature mean? | Nothing useful — zero flow at all scenarios |
| Combined geothermal supply at P50 | 8.43 MWth |
| Heating gap to bridge | 1.57 MWth |
| How is the gap bridged? | Heat pump — 0.40 MW electricity → 1.6 MWth heat |
| How is 5 MWth cooling delivered? | Free cooling (3 MW) + absorption chiller (2 MW) |
| LCoE | €29.3/MWh over 30 years |
| vs natural gas | 58% cheaper |
| Annual CO₂ saving vs gas | ~8,550 tonnes/year |

---

## Data Sources

| File | Source | Used for |
|------|--------|----------|
| `ThermoGIS_Data.xlsx` | ThermoGIS / TNO | Flow rates, temperatures, P90/P50/P10 ranges |
| `Lithostratigraphic_Data.xlsx` | Well completion reports | Formation tops and bases in AH depth |
| `Well_Path_Data.xlsx` | Directional survey data | AH-to-TVD conversion |
| `target_lithologies.csv` | Wireline logs | Gamma-ray and density for rock quality assessment |

---

## Assumptions

- Reinjection temperature: **30°C** (Dutch geothermal industry standard)
- Heat pump COP: **4.0** (IEA benchmark, water-to-water, 40°C → 70°C)
- Discount rate: **5%** | Project life: **30 years**
- Electricity price: **€120/MWh** (Dutch industrial rate, 2024)
- Cost figures: TNO Geothermal Cost Study 2022 and IEA Heat Pump Technology Roadmap
- No inter-well thermal interference modelled between BLT-01 and JUT-01

---

*Team AfriTherm — SPE Geothermal Design Challenge, May 2026*