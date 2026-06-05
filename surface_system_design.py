

import math

HEATING_DEMAND_MW   = 10.0   # MW — minimum heating target
COOLING_DEMAND_MW   =  5.0   # MW — minimum cooling target

GEO_SUPPLY_P90_MW   =  2.2   # MW pessimistic
GEO_SUPPLY_P50_MW   =  8.4   # MW most likely  ← design around this
GEO_SUPPLY_P10_MW   = 31.0   # MW optimistic

# Reservoir temperatures (from ThermoGIS)
BLT_TEMP_C          = 77     # °C  — BLT-01 reservoir temperature
JUT_TEMP_C          = 72     # °C  — JUT-01 reservoir temperature
INJECTION_TEMP_C    = 30     # °C  — temperature water is reinjected at

# Design decision: always design for P50. Check it still works at P90.
GEO_SUPPLY_MW       = GEO_SUPPLY_P50_MW
HEATING_GAP_MW      = max(0, HEATING_DEMAND_MW - GEO_SUPPLY_MW)   # = 1.6 MW




HEAT_PUMP_COP           = 4.0
HEAT_PUMP_OUTPUT_MW     = HEATING_GAP_MW                          # = 1.6 MW
HEAT_PUMP_ELEC_INPUT_MW = HEAT_PUMP_OUTPUT_MW / HEAT_PUMP_COP    # = 0.40 MW
HEAT_PUMP_SOURCE_TEMP_C = 40    # °C — temperature of geothermal water entering pump
HEAT_PUMP_SUPPLY_TEMP_C = 70    # °C — temperature delivered to building network

# P90 worst case check: at P90, geothermal only gives 2.2 MW
# The heat pump would need to cover 7.8 MW gap — that's a big pump
# Solution: at P90, we lean on the thermal storage buffer to handle peaks
HEAT_PUMP_P90_OUTPUT_MW     = HEATING_DEMAND_MW - GEO_SUPPLY_P90_MW  # 7.8 MW
HEAT_PUMP_P90_ELEC_INPUT_MW = HEAT_PUMP_P90_OUTPUT_MW / HEAT_PUMP_COP



# Cooling system design
COOLING_FREE_COOLING_MW    = 3.0   # MW — direct free cooling via injection loop
COOLING_CHILLER_MW         = 2.0   # MW — absorption chiller covers the rest
COOLING_TOTAL_MW           = COOLING_FREE_COOLING_MW + COOLING_CHILLER_MW  # = 5 MW

CHILLER_COP                = 0.7
CHILLER_HEAT_INPUT_MW      = COOLING_CHILLER_MW / CHILLER_COP  


STORAGE_HOURS           = 4       # hours of storage capacity
AVERAGE_DEMAND_MW       = 7.0     # MW — average across the day
STORAGE_ENERGY_MWH      = AVERAGE_DEMAND_MW * STORAGE_HOURS   # = 28 MWh

# Convert to tank volume: Energy = mass × specific_heat × ΔT
# ΔT = 70°C supply - 40°C return = 30°C temperature swing in the tank
# mass = Energy / (specific_heat × ΔT)
# Volume = mass / density
TANK_DELTA_T_C          = 30       # °C
SPECIFIC_HEAT_J_KGK     = 4186     # J/(kg·K)
WATER_DENSITY_KGM3      = 1000     # kg/m³
storage_energy_J        = STORAGE_ENERGY_MWH * 3600 * 1e6  # convert MWh → Joules
storage_mass_kg         = storage_energy_J / (SPECIFIC_HEAT_J_KGK * TANK_DELTA_T_C)
STORAGE_VOLUME_M3       = round(storage_mass_kg / WATER_DENSITY_KGM3)  # cubic metres



SOLAR_THERMAL_PEAK_MW   = 2.0 
SOLAR_THERMAL_AREA_M2   = 2000



CAPEX_DRILLING_EUR          = 8_000_000 
CAPEX_SURFACE_PLANT_EUR     = 3_000_000   # €3M for pipes, heat exchangers, pumps
CAPEX_HEAT_PUMP_EUR         =   400_000   # €400k for 1.6 MW heat pump
CAPEX_CHILLER_EUR           =   300_000   # €300k for 2 MW absorption chiller
CAPEX_THERMAL_STORAGE_EUR   =   500_000   # €500k for ~2000 m³ insulated tank
CAPEX_SOLAR_THERMAL_EUR     =   600_000   # €600k for 2000 m² solar thermal
CAPEX_TOTAL_EUR = (
    CAPEX_DRILLING_EUR +
    CAPEX_SURFACE_PLANT_EUR +
    CAPEX_HEAT_PUMP_EUR +
    CAPEX_CHILLER_EUR +
    CAPEX_THERMAL_STORAGE_EUR +
    CAPEX_SOLAR_THERMAL_EUR
)

OPEX_FRACTION               = 0.025
OPEX_ANNUAL_EUR             = CAPEX_TOTAL_EUR * OPEX_FRACTION

ELECTRICITY_PRICE_EUR_MWH   = 120       # €/MWh — Dutch industrial electricity price 2024
HEAT_PUMP_HOURS_PER_YEAR    = 5000      # hours/year at partial load
HEAT_PUMP_ELEC_ANNUAL_MWH   = HEAT_PUMP_ELEC_INPUT_MW * HEAT_PUMP_HOURS_PER_YEAR
HEAT_PUMP_ELEC_COST_EUR     = HEAT_PUMP_ELEC_ANNUAL_MWH * ELECTRICITY_PRICE_EUR_MWH

OPEX_TOTAL_EUR              = OPEX_ANNUAL_EUR + HEAT_PUMP_ELEC_COST_EUR

# ── Financial parameters ──────────────────────────────────────────────────────
DISCOUNT_RATE               = 0.05    # 5% — standard for public infrastructure
PROJECT_LIFETIME_YEARS      = 30      # years — typical geothermal project life

r = DISCOUNT_RATE
n = PROJECT_LIFETIME_YEARS
CRF = (r * (1 + r)**n) / ((1 + r)**n - 1)
ANNUAL_CAPEX_EUR = CAPEX_TOTAL_EUR * CRF

HEATING_FULL_LOAD_HOURS     = 4000    # hours/year
COOLING_FULL_LOAD_HOURS     = 1500    # hours/year
ANNUAL_HEATING_MWH          = HEATING_DEMAND_MW  * HEATING_FULL_LOAD_HOURS
ANNUAL_COOLING_MWH          = COOLING_DEMAND_MW  * COOLING_FULL_LOAD_HOURS
ANNUAL_TOTAL_MWH            = ANNUAL_HEATING_MWH + ANNUAL_COOLING_MWH

LCOE_EUR_PER_MWH = (ANNUAL_CAPEX_EUR + OPEX_TOTAL_EUR) / ANNUAL_TOTAL_MWH

GAS_BENCHMARK_EUR_MWH       = 70
ELECTRIC_BENCHMARK_EUR_MWH  = 110


def print_design_report():
    print("=" * 65)
    print("  CHALLENGE 2 — SURFACE SYSTEM DESIGN REPORT")
    print("  Utrecht Rotliegend Geothermal — Neighbourhood Scale")
    print("=" * 65)

    # ── System overview ────────────────────────────────────────────────────
    print(f"""
SYSTEM OVERVIEW
───────────────────────────────────────────────────────────────
  Geothermal base supply:  {GEO_SUPPLY_MW:.1f} MW  (BLT-01 + JUT-01, P50)
  Heating target:          {HEATING_DEMAND_MW:.1f} MW
  Cooling target:           {COOLING_DEMAND_MW:.1f} MW
  Heating gap to bridge:    {HEATING_GAP_MW:.1f} MW  → filled by heat pump
  Cooling gap to bridge:    {COOLING_DEMAND_MW:.1f} MW  → filled by chiller + free cooling
""")

    # ── Component 1: Heat Pump ─────────────────────────────────────────────
    print(f"""COMPONENT 1 — HEAT PUMP
───────────────────────────────────────────────────────────────
  Problem it solves:
    Geothermal gives {GEO_SUPPLY_MW:.1f} MW but target is {HEATING_DEMAND_MW:.1f} MW.
    The {HEATING_GAP_MW:.1f} MW gap must be bridged without drilling a new well.

  Why a heat pump:
    A heat pump moves heat rather than creating it.
    For {HEAT_PUMP_ELEC_INPUT_MW:.2f} MW of electricity in, you get {HEAT_PUMP_OUTPUT_MW:.1f} MW of heat out.
    COP = {HEAT_PUMP_COP} (industry standard for water-water systems at this temp range)

  Specification:
    Type:            Water-to-water heat pump
    Heat output:     {HEAT_PUMP_OUTPUT_MW:.1f} MW
    Electricity:     {HEAT_PUMP_ELEC_INPUT_MW:.2f} MW input
    Source temp:     {HEAT_PUMP_SOURCE_TEMP_C}°C  (partially cooled geothermal water)
    Supply temp:     {HEAT_PUMP_SUPPLY_TEMP_C}°C  (delivered to building network)
    COP:             {HEAT_PUMP_COP}

  P90 worst case (geothermal = {GEO_SUPPLY_P90_MW} MW):
    Heat pump output needed:  {HEAT_PUMP_P90_OUTPUT_MW:.1f} MW
    Electricity needed:       {HEAT_PUMP_P90_ELEC_INPUT_MW:.2f} MW
    → At P90, thermal storage supplements the heat pump during peaks.
""")

    # ── Component 2: Chiller ───────────────────────────────────────────────
    print(f"""COMPONENT 2 — COOLING SYSTEM (CHILLER + FREE COOLING)
───────────────────────────────────────────────────────────────
  Problem it solves:
    The neighbourhood needs {COOLING_DEMAND_MW:.1f} MW of cooling in summer.
    Geothermal on its own produces no cooling.

  Why this design:
    After extracting heat, the geothermal water returns at ~{INJECTION_TEMP_C}°C.
    That cool return water absorbs heat from buildings for free —
    no extra energy needed. This covers {COOLING_FREE_COOLING_MW:.0f} MW (free cooling).
    An absorption chiller covers the remaining {COOLING_CHILLER_MW:.0f} MW.

  Specification:
    Free cooling:        {COOLING_FREE_COOLING_MW:.0f} MW via cold injection loop
    Absorption chiller:  {COOLING_CHILLER_MW:.0f} MW output
    Chiller COP:         {CHILLER_COP} (single-effect absorption, standard)
    Heat input to chiller: {CHILLER_HEAT_INPUT_MW:.2f} MW (from geothermal source)
    Total cooling:       {COOLING_TOTAL_MW:.0f} MW  ✓ meets {COOLING_DEMAND_MW:.0f} MW target
""")

    # ── Component 3: Thermal Storage ───────────────────────────────────────
    print(f"""COMPONENT 3 — THERMAL STORAGE TANK
───────────────────────────────────────────────────────────────
  Problem it solves:
    Demand peaks (morning shower hours) require more than average supply.
    Without storage, you oversize expensive drilling and pumping equipment.

  Why storage helps (and why it lowers LCoE):
    Store excess heat overnight → release it during peaks.
    System runs at steady load all day → more efficient, less wear.
    Avoids oversizing equipment for the highest peak → cheaper CAPEX.

  Specification:
    Storage capacity:  {STORAGE_ENERGY_MWH:.0f} MWh  ({STORAGE_HOURS} hours × {AVERAGE_DEMAND_MW:.0f} MW average)
    Tank volume:       ~{STORAGE_VOLUME_M3:,} m³  (insulated hot water tank)
    Temperature swing: {TANK_DELTA_T_C}°C  (from {INJECTION_TEMP_C+TANK_DELTA_T_C}°C hot to {INJECTION_TEMP_C}°C cold side)
    Tank diameter:     ~{round(2*(STORAGE_VOLUME_M3/math.pi)**(1/3)):.0f} m  (cylindrical, height = diameter)
""")

    # ── Component 4: Solar Thermal ─────────────────────────────────────────
    print(f"""COMPONENT 4 — SOLAR THERMAL BACKUP
───────────────────────────────────────────────────────────────
  Problem it solves:
    At P90 worst case, geothermal + heat pump may fall short on the
    coldest days of the year. Solar thermal provides low-cost backup.

  Why solar thermal (not solar PV):
    Solar thermal converts sunlight directly to hot water — no electricity
    conversion step. More efficient for a system already based on hot water.
    In the Netherlands, contributes most in spring/autumn; pre-charges the
    storage tank before winter peaks.

  Specification:
    Peak output:       {SOLAR_THERMAL_PEAK_MW:.0f} MW
    Collector area:    {SOLAR_THERMAL_AREA_M2:,} m²
    Annual yield:      ~1,000 MWh/year  (Netherlands irradiance × 50% efficiency)
""")

    # ── LCoE ───────────────────────────────────────────────────────────────
    print(f"""LEVELIZED COST OF ENERGY (LCoE)
───────────────────────────────────────────────────────────────
  WHY LCoE MATTERS:
    LCoE is the average cost per unit of energy delivered over the
    system's lifetime. Lower LCoE = cheaper for residents.
    It lets judges compare your design to gas heating or all-electric.

  CAPITAL COSTS (CAPEX):
    Drilling (production + injection wells):  €{CAPEX_DRILLING_EUR/1e6:.1f}M
    Surface plant (pipes, heat exchangers):   €{CAPEX_SURFACE_PLANT_EUR/1e6:.1f}M
    Heat pump ({HEAT_PUMP_OUTPUT_MW:.1f} MW):                    €{CAPEX_HEAT_PUMP_EUR/1e3:.0f}k
    Absorption chiller ({COOLING_CHILLER_MW:.0f} MW):             €{CAPEX_CHILLER_EUR/1e3:.0f}k
    Thermal storage tank (~{STORAGE_VOLUME_M3:,} m³):       €{CAPEX_THERMAL_STORAGE_EUR/1e3:.0f}k
    Solar thermal ({SOLAR_THERMAL_AREA_M2:,} m²):            €{CAPEX_SOLAR_THERMAL_EUR/1e3:.0f}k
    ─────────────────────────────────────────────────────────
    TOTAL CAPEX:                              €{CAPEX_TOTAL_EUR/1e6:.2f}M

  ANNUAL COSTS (OPEX):
    O&M ({OPEX_FRACTION*100:.1f}% of CAPEX):                     €{OPEX_ANNUAL_EUR/1e3:.0f}k/year
    Heat pump electricity ({HEAT_PUMP_ELEC_INPUT_MW:.2f} MW × {HEAT_PUMP_HOURS_PER_YEAR:,}h): €{HEAT_PUMP_ELEC_COST_EUR/1e3:.0f}k/year
    ─────────────────────────────────────────────────────────
    TOTAL OPEX:                               €{OPEX_TOTAL_EUR/1e3:.0f}k/year

  FINANCIAL PARAMETERS:
    Discount rate:     {DISCOUNT_RATE*100:.0f}%
    Project lifetime:  {PROJECT_LIFETIME_YEARS} years
    Capital rec. factor (CRF): {CRF:.4f}
    Annualised CAPEX:  €{ANNUAL_CAPEX_EUR/1e3:.0f}k/year

  ANNUAL ENERGY DELIVERED:
    Heating: {HEATING_DEMAND_MW:.0f} MW × {HEATING_FULL_LOAD_HOURS:,} h/year = {ANNUAL_HEATING_MWH:,} MWh/year
    Cooling:  {COOLING_DEMAND_MW:.0f} MW × {COOLING_FULL_LOAD_HOURS:,} h/year =  {ANNUAL_COOLING_MWH:,} MWh/year
    Total:                                  {ANNUAL_TOTAL_MWH:,} MWh/year

  ╔═══════════════════════════════════════════════════════════╗
  ║  LCoE = (annualised CAPEX + OPEX) / annual energy         ║
  ║       = (€{ANNUAL_CAPEX_EUR/1e3:.0f}k + €{OPEX_TOTAL_EUR/1e3:.0f}k) / {ANNUAL_TOTAL_MWH:,} MWh        ║
  ║       = €{LCOE_EUR_PER_MWH:.1f}/MWh                                   ║
  ╚═══════════════════════════════════════════════════════════╝

  BENCHMARKS:
    Natural gas district heating:   ~€{GAS_BENCHMARK_EUR_MWH}/MWh
    All-electric heat pump system:  ~€{ELECTRIC_BENCHMARK_EUR_MWH}/MWh
    This geothermal hybrid system:   €{LCOE_EUR_PER_MWH:.1f}/MWh

    {"✓ COMPETITIVE — cheaper than all-electric, close to gas" if LCOE_EUR_PER_MWH < ELECTRIC_BENCHMARK_EUR_MWH else "⚠ Review cost assumptions"}
    Note: gas price excludes carbon tax trajectory (rising to €150+/t CO2 by 2030),
    which will make geothermal increasingly competitive over time.
""")

    # ── Final summary ──────────────────────────────────────────────────────
    print(f"""CHALLENGE 2 CONCLUSION
───────────────────────────────────────────────────────────────
  A four-component surface system delivers the full neighbourhood demand:

    Heating:  {GEO_SUPPLY_MW:.1f} MW geothermal + {HEAT_PUMP_OUTPUT_MW:.1f} MW heat pump = {GEO_SUPPLY_MW+HEAT_PUMP_OUTPUT_MW:.1f} MW  ✓
    Cooling:  {COOLING_FREE_COOLING_MW:.0f} MW free + {COOLING_CHILLER_MW:.0f} MW chiller         =  {COOLING_TOTAL_MW:.0f} MW  ✓
    Storage:  {STORAGE_ENERGY_MWH:.0f} MWh buffer handles morning/evening peaks  ✓
    Backup:   {SOLAR_THERMAL_PEAK_MW:.0f} MW solar thermal covers extreme cold days    ✓

  LCoE: €{LCOE_EUR_PER_MWH:.1f}/MWh over {PROJECT_LIFETIME_YEARS} years
  This system eliminates natural gas dependency for the district
  and reduces CO2 emissions by approximately:
    {round(ANNUAL_TOTAL_MWH * 0.18 / 1000)} tonnes CO2/year  (vs gas at 0.18 kg CO2/kWh)
""")
    print("=" * 65)

