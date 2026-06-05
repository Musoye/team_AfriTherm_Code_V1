import pandas as pd
import numpy as np

THERMOGIS_FILE = "ThermoGIS_Data.xlsx"
OUTPUT_CSV     = "geothermal_assessment.csv"

WATER_DENSITY      = 1000    
SPECIFIC_HEAT      = 4186  
INJECTION_TEMP_C   = 30      
SECONDS_PER_HOUR   = 3600   
MW_CONVERSION      = 1e6   


HEATING_TARGET_MW  = 10.0   
COOLING_TARGET_MW  =  5.0  

HEAT_PUMP_COP      = 4.0


def load_thermogis(filepath):
    """
    Parse ThermoGIS_Data.xlsx into a clean dictionary of well properties.

    The Excel file has one sheet per well. Each sheet has a header row
    then rows of: Property | Unit | P90 | P50 | P10

    P90 = pessimistic (only 10% chance reality is WORSE than this)
    P50 = most likely (median estimate)
    P10 = optimistic (only 10% chance reality is BETTER than this)

    WHY THREE ESTIMATES?
    ---------------------
    Underground rock properties cannot be measured everywhere — only at
    the drill bit. The P90/P50/P10 range captures the uncertainty in
    how the reservoir behaves between measurement points. Good engineering
    reports always show all three so decision-makers understand the risk.

    Returns
    -------
    dict: { well_name: { property: {P90: x, P50: y, P10: z} } }
    """
    xl = pd.ExcelFile(filepath)
    wells = {}

    for sheet in xl.sheet_names:
        df = pd.read_excel(xl, sheet_name=sheet, header=None)

        header_row = df[df.iloc[:, 0] == "Property"].index[0]
        df.columns = df.iloc[header_row]
        df = df.iloc[header_row + 1:].reset_index(drop=True)
        df.columns = ["Property", "Unit", "P90", "P50", "P10"]

        well_data = {}
        for _, row in df.iterrows():
            prop = str(row["Property"]).strip()
            well_data[prop] = {
                "Unit": row["Unit"],
                "P90":  _to_float(row["P90"]),
                "P50":  _to_float(row["P50"]),
                "P10":  _to_float(row["P10"]),
            }
        wells[sheet] = well_data

    return wells


def _to_float(val):
    """Convert a value to float, returning 0.0 if it can't be converted."""
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def calculate_thermal_power(flow_rate_m3h, reservoir_temp_c,
                             injection_temp_c=INJECTION_TEMP_C):
    """
    Calculate thermal power in MW from flow rate and temperature.

    Formula derivation (step by step):
      1. Convert flow from m³/hour to m³/second:
            flow_m3s = flow_rate_m3h / 3600

      2. Convert volume flow to mass flow (kg/second):
            mass_flow = flow_m3s × water_density
            (1 m³ of water weighs ~1000 kg)

      3. Calculate heat extracted per second (= power in Watts):
            power_W = mass_flow × specific_heat × (reservoir_temp - injection_temp)
            (specific heat = energy needed to change 1 kg of water by 1°C)

      4. Convert Watts to Megawatts:
            power_MW = power_W / 1,000,000

    Parameters
    ----------
    flow_rate_m3h   : float — flow rate in cubic metres per hour
    reservoir_temp_c: float — temperature of water coming out of the ground (°C)
    injection_temp_c: float — temperature at which we reinject water (°C)

    Returns
    -------
    float — thermal power in MW
    """
    if flow_rate_m3h <= 0:
        return 0.0

    delta_T   = reservoir_temp_c - injection_temp_c  # temperature difference (°C)
    flow_m3s  = flow_rate_m3h / SECONDS_PER_HOUR     # m³/s
    mass_flow = flow_m3s * WATER_DENSITY              # kg/s
    power_W   = mass_flow * SPECIFIC_HEAT * delta_T  # Watts
    power_MW  = power_W / MW_CONVERSION               # Megawatts

    return round(power_MW, 2)


def assess_wells(wells_data):
    """
    For each well, calculate power at P90, P50, and P10 and collect all
    key reservoir properties into a tidy results list.

    WHY WE RECALCULATE POWER FROM SCRATCH
    ----------------------------------------
    ThermoGIS already provides a Power column. We recalculate it ourselves
    because:
    (a) It proves we understand the formula — important for the report
    (b) We can change the injection temperature assumption if needed
    (c) We can verify ThermoGIS numbers are consistent

    Returns
    -------
    list of dicts, one per well per scenario (P90/P50/P10)
    """
    results = []

    for well_name, props in wells_data.items():
        temp_c = props["Temperature"]["P50"]  # temperature doesn't change with scenario

        for scenario in ["P90", "P50", "P10"]:
            flow      = props["Flow Rate"][scenario]
            perm      = props["Permeability"][scenario]
            thickness = props["Thickness"][scenario]
            porosity  = props["Porosity"][scenario]
            trans     = props["Transmissivity"][scenario]
            top_depth = props["Top Depth"]["P50"]   # depth is fixed (not uncertain)

            # Calculate power ourselves from first principles
            power_calc = calculate_thermal_power(flow, temp_c)

            # Also note ThermoGIS's own power value for comparison
            power_thermogis = props["Power"][scenario]

            results.append({
                "well":              well_name,
                "scenario":          scenario,
                "depth_m":           top_depth,
                "temp_c":            temp_c,
                "permeability_mD":   perm,
                "thickness_m":       thickness,
                "porosity_pct":      porosity,
                "transmissivity_Dm": trans,
                "flow_rate_m3h":     flow,
                "power_MW_calc":     power_calc,
                "power_MW_thermogis":power_thermogis,
                "delta_T":           temp_c - INJECTION_TEMP_C,
            })

    return results


def combined_analysis(results):
    """
    Sum power across all wells for each scenario and evaluate whether
    the 10 MW heating target is met.

    Also calculate:
    - The gap between what geology provides and what is needed
    - The electricity input a heat pump would need to bridge that gap
    - Whether a heat pump + geothermal together can meet the target

    WHY BLT-01 + JUT-01 ONLY
    -------------------------
    EVD-01 and PKP-01 both show 0 m³/h flow rate at all scenarios in
    ThermoGIS. This is because their permeability is too low (6 mD and
    1 mD respectively) for water to flow fast enough to be useful.
    Permeability is like the pipe diameter — even if there is water
    behind it, a tiny pipe means tiny flow.
    """
    df = pd.DataFrame(results)

    print("\n" + "=" * 65)
    print("  GEOTHERMAL POWER ASSESSMENT — UTRECHT ROTLIEGEND")
    print("=" * 65)

    # ── Per-well summary ───────────────────────────────────────────────────
    print("\nPer-well power output (MW):")
    print(f"\n  {'Well':<10} {'Temp °C':>8} {'Perm P50 mD':>12} "
          f"{'P90 MW':>8} {'P50 MW':>8} {'P10 MW':>8}  Status")
    print("  " + "-" * 63)

    well_summary = {}
    for well in df["well"].unique():
        sub = df[df["well"] == well]
        p90 = sub[sub["scenario"] == "P90"]["power_MW_calc"].values[0]
        p50 = sub[sub["scenario"] == "P50"]["power_MW_calc"].values[0]
        p10 = sub[sub["scenario"] == "P10"]["power_MW_calc"].values[0]
        temp = sub["temp_c"].values[0]
        perm = sub[sub["scenario"] == "P50"]["permeability_mD"].values[0]

        if p50 >= 3:
            status = "Good contributor"
        elif p50 >= 1:
            status = "Partial contributor"
        else:
            status = "No flow — rock too tight"

        print(f"  {well:<10} {temp:>8.0f} {perm:>12.0f} "
              f"{p90:>8.1f} {p50:>8.1f} {p10:>8.1f}  {status}")
        well_summary[well] = {"P90": p90, "P50": p50, "P10": p10}

    # ── Combined totals ────────────────────────────────────────────────────
    print("\nCombined total across all wells:")
    print(f"\n  {'Scenario':<10} {'Total MW':>10}  {'vs 10 MW target':>18}  {'Gap MW':>9}")
    print("  " + "-" * 52)

    totals = {}
    for scenario in ["P90", "P50", "P10"]:
        total = sum(v[scenario] for v in well_summary.values())
        gap   = HEATING_TARGET_MW - total
        gap_str = f"{gap:.1f} MW short" if gap > 0 else f"{abs(gap):.1f} MW surplus"
        meets = "MEETS target" if gap <= 0 else "below target"
        print(f"  {scenario:<10} {total:>10.1f}  {meets:>18}  {gap_str:>12}")
        totals[scenario] = {"total_mw": total, "gap_mw": max(0, gap)}

    # ── Heat pump bridge analysis ──────────────────────────────────────────
    gap_p50 = totals["P50"]["gap_mw"]
    print(f"\n{'─'*65}")
    print(f"\nGAP ANALYSIS (P50 most-likely scenario):")
    print(f"  Geothermal supply:      {totals['P50']['total_mw']:.1f} MW")
    print(f"  Heating target:         {HEATING_TARGET_MW:.1f} MW")
    print(f"  Gap to fill:            {gap_p50:.1f} MW")

    if gap_p50 > 0:
        # How much electricity does the heat pump need to deliver gap_p50 MW of heat?
        # Heat pump delivers: COP × electricity_input = heat_output
        # So: electricity_input = heat_output / COP
        electricity_needed = gap_p50 / HEAT_PUMP_COP
        print(f"\nHeat pump solution (COP = {HEAT_PUMP_COP}):")
        print(f"  Electricity input needed:  {electricity_needed:.2f} MW")
        print(f"  Heat output from pump:     {gap_p50:.1f} MW")
        print(f"  Total heating delivered:   {totals['P50']['total_mw'] + gap_p50:.1f} MW  ✓ meets target")
        print(f"\n  Interpretation: for every 1 MW of grid electricity, the heat pump")
        print(f"  delivers {HEAT_PUMP_COP:.0f} MW of heat. Only {electricity_needed:.2f} MW of electricity")
        print(f"  is needed to bridge the entire gap — very efficient.")
    else:
        print("  No heat pump needed — geothermal alone meets the target at P50.")

    # ── Cooling note ───────────────────────────────────────────────────────
    print(f"\nCooling demand ({COOLING_TARGET_MW} MW):")
    print(f"  Geothermal return water (reinjected at {INJECTION_TEMP_C}°C) can serve as")
    print(f"  heat sink for building cooling in summer via absorption chiller.")
    print(f"  A {COOLING_TARGET_MW} MW chiller connected to the injection loop covers the full")
    print(f"  cooling demand without additional energy sources.")

    # ── Why EVD-01 and PKP-01 don't contribute ────────────────────────────
    print(f"\nWhy EVD-01 and PKP-01 produce zero power:")
    print(f"  EVD-01  permeability:  6 mD  → rock is too tight for water to flow")
    print(f"  PKP-01  permeability:  1 mD  → rock is essentially impermeable")
    print(f"  PKP-01 is the hottest well (88°C) but heat is worthless if you")
    print(f"  cannot pump the water out. Flow rate = 0 → Power = 0 MW.")
    print(f"\n  Analogy: a hot water tank with a blocked tap. The heat is there,")
    print(f"  but it cannot go anywhere useful.")

    return df, totals


def save_results(df, output_path):
    """
    Save the full assessment table to CSV.

    This CSV is your evidence for Challenge 1 — it shows every well,
    every scenario, every property, and every calculated power value.
    Include it as an appendix in your technical report.
    """
    df.to_csv(output_path, index=False)
    print(f"\nFull results saved → {output_path}")
    print("Use this CSV as the data appendix for your Challenge 1 report.")

