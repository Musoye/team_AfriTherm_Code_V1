import os
import json
import pandas as pd
import numpy as np

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False
    print("NOTE: 'groq' package not installed.")
    print("Run: pip install groq")


def run_full_pipeline(
    thermogis_file="ThermoGIS_Data.xlsx",
    well_path_file="Well_Path_Data.xlsx",
    litho_file="Lithostratigraphic_Data.xlsx",
):
    """
    Run the complete geothermal assessment pipeline.

    Returns:
        dict: All computed results for AI analysis and reporting.
    """

    print("─" * 60)
    print("STEP 1/3 — Loading and processing well data")
    print("─" * 60)

    xl_wp = pd.ExcelFile(well_path_file)
    xl_lith = pd.ExcelFile(litho_file)

    tvd_corrections = {}

    for well in ["BLT-01", "JUT-01", "EVD-01", "PKP-01"]:

        wp = (
            pd.read_excel(xl_wp, sheet_name=well)[["Depth (m)", "TVD (m)"]]
            .dropna()
        )

        lith = pd.read_excel(xl_lith, sheet_name=well)

        formation_col = lith.columns[0]

        slochteren = lith[
            lith[formation_col].str.contains(
                "Slochteren Formation",
                na=False
            )
        ].iloc[0]

        ah_top = float(slochteren["Top (m)"])
        ah_base = float(slochteren["Bottom (m)"])

        tvd_top = float(
            np.interp(
                ah_top,
                wp["Depth (m)"],
                wp["TVD (m)"]
            )
        )

        tvd_base = float(
            np.interp(
                ah_base,
                wp["Depth (m)"],
                wp["TVD (m)"]
            )
        )

        correction = ah_top - tvd_top

        tvd_corrections[well] = {
            "ah_top": ah_top,
            "ah_base": ah_base,
            "tvd_top": round(tvd_top, 1),
            "tvd_base": round(tvd_base, 1),
            "correction_m": round(correction, 1),
            "thickness_tvd_m": round(tvd_base - tvd_top, 1),
        }

        print(
            f"  {well}: "
            f"AH {ah_top:.0f}m → TVD {tvd_top:.0f}m "
            f"(correction {correction:.0f}m)"
        )

    print("\n" + "─" * 60)
    print("STEP 2/3 — Calculating thermal power per well")
    print("─" * 60)

    xl_tgis = pd.ExcelFile(thermogis_file)

    INJECTION_T = 30
    DENSITY = 1000
    SPEC_HEAT = 4186

    well_results = {}

    for sheet in xl_tgis.sheet_names:

        df = pd.read_excel(
            xl_tgis,
            sheet_name=sheet,
            header=None
        )

        header_row = df[df.iloc[:, 0] == "Property"].index[0]

        df.columns = df.iloc[header_row]

        df = df.iloc[header_row + 1:].reset_index(drop=True)

        df.columns = [
            "Property",
            "Unit",
            "P90",
            "P50",
            "P10",
        ]

        props = {
            row["Property"]: row
            for _, row in df.iterrows()
        }

        temp = float(props["Temperature"]["P50"])

        power = {}

        for scenario in ["P90", "P50", "P10"]:

            flow = float(props["Flow Rate"][scenario])

            delta_t = temp - INJECTION_T

            if flow > 0:
                thermal_power = (
                    (flow / 3600)
                    * DENSITY
                    * SPEC_HEAT
                    * delta_t
                    / 1e6
                )
            else:
                thermal_power = 0

            power[scenario] = round(
                thermal_power,
                2
            )

        well_results[sheet] = {
            "temp_c": temp,
            "perm_p50_mD": float(
                props["Permeability"]["P50"]
            ),
            "flow_p50_m3h": float(
                props["Flow Rate"]["P50"]
            ),
            "power": power,
        }

        print(
            f"  {sheet}: "
            f"{temp:.1f}°C | "
            f"flow P50={well_results[sheet]['flow_p50_m3h']:.0f} m³/h | "
            f"power P50={power['P50']:.1f} MW"
        )

    print("\n" + "─" * 60)
    print("STEP 3/3 — Computing surface system design and LCoE")
    print("─" * 60)

    total_p50 = sum(
        v["power"]["P50"]
        for v in well_results.values()
    )

    total_p90 = sum(
        v["power"]["P90"]
        for v in well_results.values()
    )

    heating_gap = max(
        0,
        10.0 - total_p50
    )

    cop = 4.0

    heat_pump_electricity = round(
        heating_gap / cop,
        2
    )

    capex_total = 12_800_000
    opex_annual = 560_000

    discount_rate = 0.05
    project_life = 30

    crf = (
        discount_rate
        * (1 + discount_rate) ** project_life
    ) / (
        (1 + discount_rate) ** project_life
        - 1
    )

    annualized_capex = capex_total * crf

    annual_energy_mwh = (
        10 * 4000
        + 5 * 1500
    )

    lcoe = (
        annualized_capex
        + opex_annual
    ) / annual_energy_mwh

    design = {
        "geo_supply_p50_mw": round(total_p50, 1),
        "geo_supply_p90_mw": round(total_p90, 1),
        "heating_gap_mw": round(heating_gap, 1),
        "heat_pump_output_mw": round(heating_gap, 1),
        "heat_pump_elec_mw": heat_pump_electricity,
        "heat_pump_cop": cop,
        "cooling_mw": 5.0,
        "storage_mwh": 28,
        "solar_thermal_mw": 2.0,
        "capex_total_eur": capex_total,
        "lcoe_eur_mwh": round(lcoe, 1),
    }

    print(
        f"  Geo supply P50: {design['geo_supply_p50_mw']} MW"
    )

    print(
        f"  Heating gap: {design['heating_gap_mw']} MW "
        f"→ heat pump"
    )

    print(
        f"  LCoE: €{design['lcoe_eur_mwh']}/MWh"
    )

    return {
        "tvd_corrections": tvd_corrections,
        "well_results": well_results,
        "design": design,
    }


def generate_ai_summary(pipeline_results):

    if not GROQ_AVAILABLE:
        print(
            "\nSkipping AI summary — "
            "groq package not installed."
        )
        return None

    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        print(
            "\nSkipping AI summary — "
            "GROQ_API_KEY not found."
        )
        return None

    print("\n" + "─" * 60)
    print("BONUS — Calling Groq API for AI-generated summary")
    print("─" * 60)

    results_json = json.dumps(
        pipeline_results,
        indent=2
    )

    prompt = f"""
You are a geothermal energy consultant writing a technical report section
for a student design challenge.

Based on the computed results below, write a concise professional summary
between 300 and 400 words covering:

1. What the geological assessment found.
2. Which wells appear most viable and why.
3. Why geothermal supply alone falls short.
4. How the proposed surface system closes the gap.
5. Interpretation of the calculated LCoE.
6. A short discussion of the P90 risk scenario.

Use the actual numerical values from the results.

Write in clear professional English suitable for an engineering report.

Do not use bullet points.

COMPUTED RESULTS:
{results_json}
"""

    try:

        client = Groq(
            api_key=api_key
        )

        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.3,
            top_p=0.9,
            max_completion_tokens=1024
        )

        summary = response.choices[0].message.content

        print("\nAI-GENERATED REPORT SUMMARY:")
        print("─" * 60)
        print(summary)
        print("─" * 60)

        with open(
            "ai_generated_report.txt",
            "w",
            encoding="utf-8"
        ) as f:

            f.write(
                "AI-GENERATED GEOTHERMAL ASSESSMENT SUMMARY\n"
            )

            f.write(
                "Generated using Groq Llama 3.3 70B Versatile\n"
            )

            f.write(
                "─" * 60 + "\n\n"
            )

            f.write(summary)

        print(
            "\nSaved → ai_generated_report.txt"
        )

        return summary

    except Exception as e:

        print(
            f"\nGroq API error: {e}"
        )

        return None

def save_pipeline_results(results):
    """
    Save all computed results to CSV.
    """

    rows = []

    for well, tvd in results["tvd_corrections"].items():

        rows.append([
            "TVD Correction",
            well,
            "AH Top (m)",
            tvd["ah_top"],
        ])

        rows.append([
            "TVD Correction",
            well,
            "TVD Top (m)",
            tvd["tvd_top"],
        ])

        rows.append([
            "TVD Correction",
            well,
            "Correction (m)",
            tvd["correction_m"],
        ])

        rows.append([
            "TVD Correction",
            well,
            "Thickness TVD (m)",
            tvd["thickness_tvd_m"],
        ])

    for well, wr in results["well_results"].items():

        rows.append([
            "Power",
            well,
            "Temperature (C)",
            wr["temp_c"],
        ])

        rows.append([
            "Power",
            well,
            "Flow P50 (m3/h)",
            wr["flow_p50_m3h"],
        ])

        rows.append([
            "Power",
            well,
            "Power P90 (MW)",
            wr["power"]["P90"],
        ])

        rows.append([
            "Power",
            well,
            "Power P50 (MW)",
            wr["power"]["P50"],
        ])

        rows.append([
            "Power",
            well,
            "Power P10 (MW)",
            wr["power"]["P10"],
        ])

    for key, value in results["design"].items():

        rows.append([
            "Design",
            "System",
            key,
            value,
        ])

    df = pd.DataFrame(
        rows,
        columns=[
            "Category",
            "Well/Component",
            "Parameter",
            "Value",
        ],
    )

    df.to_csv(
        "pipeline_results.csv",
        index=False
    )

    print(
        "\nFull results saved → pipeline_results.csv"
    )


def main():

    print("\nGEOTHERMAL DESIGN AUTOMATION PIPELINE")
    print("=" * 60)

    results = run_full_pipeline()

    save_pipeline_results(results)

    generate_ai_summary(results)

    print("\nPipeline completed successfully.")


