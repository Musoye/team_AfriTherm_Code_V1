"""
TVD Conversion for Geothermal Challenge
========================================

PROBLEM THIS SOLVES
-------------------
All four wells are deviated (drilled at an angle). Raw depth values in the
lithostratigraphic data are Along-Hole (AH) depth — the length of drill pipe,
NOT the real depth underground.

Converting to True Vertical Depth (TVD) is MANDATORY before any temperature
or power calculation. The error if you skip this:
  - PKP-01 Slochteren formation: 323 m shallower than AH suggests
  - BLT-01 Slochteren formation: 61 m shallower
  - JUT-01 / EVD-01: small corrections (~5 m)

HOW IT WORKS (layman version)
------------------------------
The Well_Path_Data.xlsx contains a survey table for each well — think of it
as a GPS log of the drill bit. For every measured length of pipe, it records
how deep straight-down (TVD) the bit actually is. We use those pairs as a
lookup table and interpolate for any depth in between.

OUTPUT FILES
------------
- target_lithologies_tvd_corrected.csv
    Same as the input, with depth_tvd_m correctly filled using TVD
    (not AH) depths for the Slochteren formation boundaries.
"""

import pandas as pd
import numpy as np

# ── File paths (edit these to match your folder) ──────────────────────────────
WELL_PATH_FILE  = "Well_Path_Data.xlsx"
LITHO_FILE      = "Lithostratigraphic_Data.xlsx"
CSV_FILE        = "target_lithologies.csv"
OUTPUT_FILE     = "target_lithologies_tvd_corrected.csv"


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — Load the well path lookup tables
# ══════════════════════════════════════════════════════════════════════════════

def load_well_paths(filepath):
    """
    Load the well path survey data for all four wells.

    Returns a dict: { "BLT-01": DataFrame, "JUT-01": DataFrame, ... }
    Each DataFrame has columns: "Depth (m)" (= AH depth) and "TVD (m)"

    WHY: The well path survey is measured by gyroscope tools inside the
    drill pipe. At each survey station, engineers record the pipe length
    used (AH depth) and calculate the true vertical depth from the
    inclination and azimuth angles. We use these pre-computed TVD values
    as our ground truth.
    """
    xl = pd.ExcelFile(filepath)
    well_paths = {}
    for sheet in xl.sheet_names:
        df = pd.read_excel(xl, sheet_name=sheet)
        df = df[["Depth (m)", "TVD (m)"]].dropna()
        df = df.sort_values("Depth (m)").reset_index(drop=True)
        well_paths[sheet] = df
    return well_paths


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — The core conversion function: AH depth → TVD
# ══════════════════════════════════════════════════════════════════════════════

def ah_to_tvd(ah_depth, well_path_df):
    """
    Convert one or more AH depth values to TVD for a single well.

    Uses linear interpolation between the two nearest survey stations.

    Parameters
    ----------
    ah_depth : float or array-like
        AH depth value(s) in metres
    well_path_df : DataFrame
        Survey table for this well with columns "Depth (m)" and "TVD (m)"

    Returns
    -------
    float or numpy array of TVD values

    HOW INTERPOLATION WORKS (layman version)
    -----------------------------------------
    You have two known points:
      AH = 2530 m → TVD = 2207 m    (survey station above target)
      AH = 2560 m → TVD = 2234 m    (survey station below target)

    For AH = 2545 m (halfway between):
      TVD = 2207 + (2545 - 2530) / (2560 - 2530) × (2234 - 2207)
          = 2207 + 0.5 × 27 = 2220.5 m

    numpy's interp() does this automatically for any number of values.
    """
    ah_known  = well_path_df["Depth (m)"].values
    tvd_known = well_path_df["TVD (m)"].values
    return np.interp(ah_depth, ah_known, tvd_known)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — Get the correct TVD formation boundaries from lithostratigraphy
# ══════════════════════════════════════════════════════════════════════════════

def get_slochteren_tvd_bounds(litho_file, well_paths):
    """
    Read the Slochteren formation top and base for each well from the
    lithostratigraphic data, then convert those AH depths to TVD.

    WHY THIS STEP IS NEEDED
    ------------------------
    The lithostratigraphic data (and the formation_top_tvd / formation_base_tvd
    columns in the CSV) record depths as AH — the drill pipe length at the
    time the formation was encountered. Despite the column name saying "TVD",
    the values are actually AH depths that still need correction.

    Evidence: PKP-01 Slochteren is listed as 2530–2603 m. The well path
    shows PKP-01 has inclination of ~28° at that depth. The actual TVD is
    ~2207–2272 m — a 323 m difference. Using the uncorrected value would
    give a temperature estimate ~10°C too high for PKP-01.

    Returns
    -------
    dict: { well_id: {"ah_top": x, "ah_base": y, "tvd_top": a, "tvd_base": b} }
    """
    xl = pd.ExcelFile(litho_file)
    bounds = {}

    for well in ["BLT-01", "JUT-01", "EVD-01", "PKP-01"]:
        lith = pd.read_excel(xl, sheet_name=well)
        col  = lith.columns[0]  # first column is the formation name

        # Find the Slochteren Formation row (our target reservoir)
        sloch_rows = lith[lith[col].str.contains("Slochteren Formation", na=False)]
        if sloch_rows.empty:
            print(f"  WARNING: Slochteren not found for {well}")
            continue

        # Take the first Slochteren occurrence (shallowest)
        sloch    = sloch_rows.iloc[0]
        ah_top   = float(sloch["Top (m)"])
        ah_base  = float(sloch["Bottom (m)"])

        # Convert AH → TVD using the well path table
        wp = well_paths[well]
        tvd_top  = float(ah_to_tvd(ah_top,  wp))
        tvd_base = float(ah_to_tvd(ah_base, wp))

        bounds[well] = {
            "ah_top":   ah_top,
            "ah_base":  ah_base,
            "tvd_top":  tvd_top,
            "tvd_base": tvd_base,
            "correction_m": round(ah_top - tvd_top, 1),
        }

    return bounds


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — Fill depth_tvd_m in the CSV using corrected TVD bounds
# ══════════════════════════════════════════════════════════════════════════════

def fill_tvd_in_csv(csv_path, tvd_bounds, output_path):
    """
    Fill the depth_tvd_m column for every row in the target_lithologies CSV.

    Each well has one continuous block of log samples spanning the Slochteren
    formation. We assign depth_tvd_m by linearly spacing rows between the
    correct TVD top and base (from Step 3).

    WHY LINEAR SPACING IS CORRECT
    ------------------------------
    Well logs are recorded at regular depth intervals as the logging tool
    moves through the borehole — typically every 0.1 m or 0.5 m. So the
    samples ARE evenly spaced in depth. Linear spacing from top to base
    recovers those original depths in TVD units.
    """
    df = pd.read_csv(csv_path)
    print(f"\nCSV loaded: {len(df)} rows, all depth_tvd_m currently NaN\n")

    for well_id, b in tvd_bounds.items():
        mask   = df["well_id"] == well_id
        n_rows = mask.sum()
        if n_rows == 0:
            continue

        # Assign evenly-spaced TVD values from corrected top to corrected base
        df.loc[mask, "depth_tvd_m"]         = np.linspace(b["tvd_top"], b["tvd_base"], n_rows)
        df.loc[mask, "formation_top_tvd"]    = b["tvd_top"]
        df.loc[mask, "formation_base_tvd"]   = b["tvd_base"]
        df.loc[mask, "formation_thickness_m"]= round(b["tvd_base"] - b["tvd_top"], 1)
        df.loc[mask, "flag"]                 = "tvd_corrected"
        df.loc[mask, "flag_reason"]          = (
            f"AH {b['ah_top']:.1f}-{b['ah_base']:.1f}m → "
            f"TVD {b['tvd_top']:.1f}-{b['tvd_base']:.1f}m "
            f"(correction: {b['correction_m']:.1f}m)"
        )

        step = (b["tvd_base"] - b["tvd_top"]) / (n_rows - 1)
        thickness_ah  = b["ah_base"] - b["ah_top"]
        thickness_tvd = b["tvd_base"] - b["tvd_top"]

        print(f"  {well_id}:")
        print(f"    AH depth:     {b['ah_top']:.1f} – {b['ah_base']:.1f} m  "
              f"(thickness {thickness_ah:.1f} m)")
        print(f"    TVD depth:    {b['tvd_top']:.1f} – {b['tvd_base']:.1f} m  "
              f"(thickness {thickness_tvd:.1f} m)")
        print(f"    Correction:   {b['correction_m']:.1f} m shallower than AH suggested")
        print(f"    Log samples:  {n_rows} rows at {step:.4f} m spacing")
        print()

    df.to_csv(output_path, index=False)
    return df


# ══════════════════════════════════════════════════════════════════════════════
# STEP 5 — Sanity checks and summary table
# ══════════════════════════════════════════════════════════════════════════════

def print_summary(df):
    """
    Print a summary table of the corrected TVD depths and flag any issues.

    WHAT TO LOOK FOR
    ----------------
    - No remaining NaN values in depth_tvd_m  → good
    - TVD depth < AH depth for all wells       → physically required
    - PKP-01 correction ~323 m                 → expected (most deviated)
    - BLT-01 correction ~62 m                  → expected
    - JUT-01 / EVD-01 corrections <10 m        → expected (nearly vertical)
    """
    print("─" * 65)
    print(f"{'Well':<10} {'TVD top':>10} {'TVD base':>10} "
          f"{'Thickness':>11} {'Rows':>6} {'NaN left':>9}")
    print("─" * 65)

    for well_id in df["well_id"].unique():
        sub = df[df["well_id"] == well_id]
        tvd_min   = sub["depth_tvd_m"].min()
        tvd_max   = sub["depth_tvd_m"].max()
        thickness = tvd_max - tvd_min
        n_nan     = sub["depth_tvd_m"].isna().sum()
        print(f"  {well_id:<8} {tvd_min:>10.1f} {tvd_max:>10.1f} "
              f"{thickness:>11.1f} {len(sub):>6} {n_nan:>9}")

    print("─" * 65)
    total_nan = df["depth_tvd_m"].isna().sum()
    print(f"\nTotal missing values remaining: {total_nan}")
    if total_nan == 0:
        print("All depth_tvd_m values successfully filled.")
    else:
        print("WARNING: some values still missing — check the output file.")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 65)
    print("  TVD CONVERSION PIPELINE")
    print("  Geothermal Challenge — Utrecht Rotliegend Reservoir")
    print("=" * 65)

    print("\n[Step 1] Loading well path survey tables...")
    well_paths = load_well_paths(WELL_PATH_FILE)
    for name, wp in well_paths.items():
        print(f"  {name}: {len(wp)} survey stations | "
              f"AH range {wp['Depth (m)'].max():.0f} m | "
              f"TVD range {wp['TVD (m)'].max():.0f} m | "
              f"max deviation {wp['Depth (m)'].max() - wp['TVD (m)'].max():.0f} m")

    print("\n[Step 2] Converting Slochteren AH boundaries to TVD...")
    tvd_bounds = get_slochteren_tvd_bounds(LITHO_FILE, well_paths)
    for w, b in tvd_bounds.items():
        print(f"  {w}: AH {b['ah_top']:.1f}-{b['ah_base']:.1f} m → "
              f"TVD {b['tvd_top']:.1f}-{b['tvd_base']:.1f} m  "
              f"[correction: {b['correction_m']:.1f} m]")

    print("\n[Step 3] Filling depth_tvd_m in target_lithologies.csv...")
    df_out = fill_tvd_in_csv(CSV_FILE, tvd_bounds, OUTPUT_FILE)

    print("[Step 4] Summary of corrected data:")
    print_summary(df_out)

    print(f"\nOutput saved → {OUTPUT_FILE}")
    print("Next step: run power_calculation.py on this corrected file.")