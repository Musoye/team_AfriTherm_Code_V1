"""
Bonus Challenge — AI-Assisted Geothermal Design Workflow
==========================================================

PROBLEM THIS SOLVES
--------------------
Right now, running the full analysis (TVD correction → power calculation
→ system design → LCoE) requires manually running three separate scripts
and reading through pages of output. If the data changes, you redo
everything by hand.

This script automates the entire pipeline AND calls the Claude AI API
to generate a plain-English interpretation of the results — the kind
of summary you would write in your technical report.

export ANTHROPIC_API_KEY="your-key-here"
"""

import os
import json
import pandas as pd
import numpy as np

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    print("NOTE: 'anthropic' package not installed. Run: pip install anthropic")
    print("      The pipeline will still run; only the AI summary will be skipped.\n")



def run_full_pipeline(
    thermogis_file   = "ThermoGIS_Data.xlsx",
    well_path_file   = "Well_Path_Data.xlsx",
    litho_file       = "Lithostratigraphic_Data.xlsx",
):
    """
    Run the complete geothermal assessment pipeline.

    Returns a dict of all key results that gets passed to the AI summary.
    """
    print("─" * 60)
    print("STEP 1/3 — Loading and processing well data")
    print("─" * 60)

    xl_wp   = pd.ExcelFile(well_path_file)
    xl_lith = pd.ExcelFile(litho_file)

    tvd_corrections = {}
    for well in ["BLT-01", "JUT-01", "EVD-01", "PKP-01"]:
        wp    = pd.read_excel(xl_wp, sheet_name=well)[["Depth (m)", "TVD (m)"]].dropna()
        lith  = pd.read_excel(xl_lith, sheet_name=well)
        col   = lith.columns[0]
        sloch = lith[lith[col].str.contains("Slochteren Formation", na=False)].iloc[0]
        ah_top   = float(sloch["Top (m)"])
        ah_base  = float(sloch["Bottom (m)"])
        tvd_top  = float(np.interp(ah_top,  wp["Depth (m)"], wp["TVD (m)"]))
        tvd_base = float(np.interp(ah_base, wp["Depth (m)"], wp["TVD (m)"]))
        tvd_corrections[well] = {
            "ah_top": ah_top, "ah_base": ah_base,
            "tvd_top": round(tvd_top, 1), "tvd_base": round(tvd_base, 1),
            "correction_m": round(ah_top - tvd_top, 1),
            "thickness_tvd_m": round(tvd_base - tvd_top, 1),
        }
        print(f"  {well}: AH {ah_top:.0f}m → TVD {tvd_top:.0f}m  (correction {ah_top-tvd_top:.0f}m)")

    # ── Power calculation (from power_calculation.py logic) ──────────────
    print("\n─" * 60)
    print("STEP 2/3 — Calculating thermal power per well")
    print("─" * 60)

    xl_tgis     = pd.ExcelFile(thermogis_file)
    INJECTION_T = 30
    DENSITY     = 1000
    SPEC_HEAT   = 4186

    well_results = {}
    for sheet in xl_tgis.sheet_names:
        df = pd.read_excel(xl_tgis, sheet_name=sheet, header=None)
        hr = df[df.iloc[:, 0] == "Property"].index[0]
        df.columns = df.iloc[hr]
        df = df.iloc[hr+1:].reset_index(drop=True)
        df.columns = ["Property", "Unit", "P90", "P50", "P10"]
        props = {r["Property"]: r for _, r in df.iterrows()}

        temp = float(props["Temperature"]["P50"])
        power = {}
        for sc in ["P90", "P50", "P10"]:
            flow  = float(props["Flow Rate"][sc])
            dT    = temp - INJECTION_T
            pw    = (flow / 3600) * DENSITY * SPEC_HEAT * dT / 1e6 if flow > 0 else 0.0
            power[sc] = round(pw, 2)

        well_results[sheet] = {
            "temp_c":      temp,
            "perm_p50_mD": float(props["Permeability"]["P50"]),
            "flow_p50_m3h":float(props["Flow Rate"]["P50"]),
            "power":       power,
        }
        print(f"  {sheet}: {temp}°C | flow P50={well_results[sheet]['flow_p50_m3h']:.0f} m³/h "
              f"| power P50={power['P50']:.1f} MW")

    print("\n─" * 60)
    print("STEP 3/3 — Computing surface system design and LCoE")
    print("─" * 60)

    total_p50 = sum(v["power"]["P50"] for v in well_results.values())
    total_p90 = sum(v["power"]["P90"] for v in well_results.values())
    gap_mw    = max(0, 10.0 - total_p50)
    cop       = 4.0
    hp_elec   = round(gap_mw / cop, 2)

    # LCoE
    capex_total = 12_800_000
    opex_annual = 560_000
    r, n = 0.05, 30
    crf = (r * (1+r)**n) / ((1+r)**n - 1)
    annual_capex = capex_total * crf
    annual_energy_mwh = 10*4000 + 5*1500
    lcoe = (annual_capex + opex_annual) / annual_energy_mwh

    design = {
        "geo_supply_p50_mw":    round(total_p50, 1),
        "geo_supply_p90_mw":    round(total_p90, 1),
        "heating_gap_mw":       round(gap_mw, 1),
        "heat_pump_output_mw":  round(gap_mw, 1),
        "heat_pump_elec_mw":    hp_elec,
        "heat_pump_cop":        cop,
        "cooling_mw":           5.0,
        "storage_mwh":          28,
        "solar_thermal_mw":     2.0,
        "capex_total_eur":      capex_total,
        "lcoe_eur_mwh":         round(lcoe, 1),
    }

    print(f"  Geo supply P50:  {design['geo_supply_p50_mw']} MW")
    print(f"  Heating gap:     {design['heating_gap_mw']} MW → heat pump")
    print(f"  LCoE:            €{design['lcoe_eur_mwh']}/MWh")

    return {
        "tvd_corrections": tvd_corrections,
        "well_results":    well_results,
        "design":          design,
    }



def generate_ai_summary(pipeline_results):
    """
    Pass all computed results to Claude and ask it to write a
    plain-English technical summary suitable for the report.

    WHY THIS IS USEFUL
    -------------------
    The pipeline produces numbers. The report needs sentences.
    Rather than writing the interpretation by hand, we let the AI
    read the structured results and write a professional summary.
    This is exactly the "AI-assisted workflow" the bonus asks for.
    """
    if not ANTHROPIC_AVAILABLE:
        print("\nSkipping AI summary — anthropic package not installed.")
        return None

    print("\n─" * 60)
    print("BONUS — Calling Claude API for AI-generated summary")
    print("─" * 60)

    # Format the results as a clean JSON block for the prompt
    results_json = json.dumps(pipeline_results, indent=2)

    prompt = f"""You are a geothermal energy consultant writing a technical report 
section for a student design challenge. Based on the computed results below, 
write a concise professional summary (300-400 words) covering:

1. What the geological assessment found (which wells are viable and why)
2. Why the geothermal supply alone falls short and by how much
3. How the surface system design bridges the gap
4. What the LCoE means in context (compare to gas and all-electric)
5. One sentence on the P90 risk scenario

Write in clear professional English. Use the actual numbers from the results.
Do not use bullet points — write in flowing paragraphs suitable for a report.

COMPUTED RESULTS:
{results_json}
"""

    client  = anthropic.Anthropic()
    message = client.messages.create(
        model      = "claude-sonnet-4-6",
        max_tokens = 1000,
        messages   = [{"role": "user", "content": prompt}]
    )

    summary = message.content[0].text
    print("\nAI-GENERATED REPORT SUMMARY:")
    print("─" * 60)
    print(summary)
    print("─" * 60)

    # Save to file
    with open("ai_generated_report.txt", "w") as f:
        f.write("AI-GENERATED GEOTHERMAL ASSESSMENT SUMMARY\n")
        f.write("Generated by Claude claude-sonnet-4-6 via Anthropic API\n")
        f.write("─" * 60 + "\n\n")
        f.write(summary)
    print("\nSaved → ai_generated_report.txt")

    return summary


def save_pipeline_results(results):
    """Save all pipeline results to a single CSV for the report appendix."""
    rows = []
    for well, tvd in results["tvd_corrections"].items():
        rows.append(["TVD Correction", well, "AH Top (m)",       tvd["ah_top"]])
        rows.append(["TVD Correction", well, "TVD Top (m)",       tvd["tvd_top"]])
        rows.append(["TVD Correction", well, "Correction (m)",    tvd["correction_m"]])
        rows.append(["TVD Correction", well, "Thickness TVD (m)", tvd["thickness_tvd_m"]])

    for well, wr in results["well_results"].items():
        rows.append(["Power", well, "Temperature (C)",   wr["temp_c"]])
        rows.append(["Power", well, "Flow P50 (m3/h)",   wr["flow_p50_m3h"]])
        rows.append(["Power", well, "Power P90 (MW)",    wr["power"]["P90"]])
        rows.append(["Power", well, "Power P50 (MW)",    wr["power"]["P50"]])
        rows.append(["Power", well, "Power P10 (MW)",    wr["power"]["P10"]])

    d = results["design"]
    for k, v in d.items():
        rows.append(["Design", "System", k, v])

    df = pd.DataFrame(rows, columns=["Category", "Well/Component", "Parameter", "Value"])
    df.to_csv("pipeline_results.csv", index=False)
    print("\nFull results saved → pipeline_results.csv")
