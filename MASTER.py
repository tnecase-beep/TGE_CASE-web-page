# -*- coding: utf-8 -*-
"""
MASTER.py

Fully parametric multi-layer supply-chain optimization model.

- Plants, cross-docks, DCs, and potential new locations can be switched on/off
  via input lists (active_*).
- Transport modes (air / Water / road) can be switched on/off separately
  for each layer (L1, L2, L3).
- Retailers and their demand stay as in the original models.

Returns:
    results: dict with KPIs (objective, CO2 by mode, etc.)
    model:   gurobipy Model instance
"""

from gurobipy import Model, GRB, quicksum
import pandas as pd
import numpy as np
from statistics import NormalDist as _ND; _nd = _ND(); norm = type('norm', (), {'pdf': staticmethod(_nd.pdf), 'ppf': staticmethod(_nd.inv_cdf), 'cdf': staticmethod(_nd.cdf)})()




def print_flows(flow_vars, O, D, M, title="flow"):
    """
    flow_vars: gurobi var dict like f1[p,c,mo]
    O: origins list
    D: destinations list
    M: modes list (ModesL1 / ModesL2 / ModesL3)
    Returns a pandas DataFrame with sums over modes.
    """
    if not flow_vars:
        return pd.DataFrame(index=O, columns=D).fillna(0.0)

    data = []
    for o in O:
        row = []
        for d in D:
            s = 0.0
            for mo in M:
                v = flow_vars.get((o, d, mo), None)
                if v is not None:
                    try:
                        s += float(v.X)
                    except Exception:
                        pass
            row.append(s)
        data.append(row)

    df = pd.DataFrame(data, index=O, columns=D)
    df.index.name = title
    return df



def run_scenario_master(
    # --- Location selection (None => use full default set) ---
    active_plants=None,
    active_new_locs=None,
    active_crossdocks=None,
    active_dcs=None,

    # --- Mode selection per layer (None => use default) ---
    active_modes_L1=None,   # Plant -> Crossdock
    active_modes_L2=None,   # Crossdock/NewLoc -> DC
    active_modes_L3=None,   # DC -> Retailer

    # --- Data (all optional; sensible defaults where possible) ---
    dc_capacity=None,
    demand=None,
    handling_dc=None,
    handling_crossdock=None,
    sourcing_cost=None,
    co2_prod_kg_per_unit=None,
    product_weight=2.58,           # kg per unit
    co2_cost_per_ton=37.50,        # €/ton for existing mfg CO2
    co2_cost_per_ton_New=60.00,    # €/ton for new loc mfg CO2
    CO2_base=1582.42366689614,     # baseline CO2 (tons) for % reduction
    new_loc_capacity=None,
    new_loc_openingCost=None,
    new_loc_operationCost=None,    # not essential; kept for compatibility
    new_loc_CO2=None,              # kg CO2 per unit at new locations
    co2_emission_factor=None,      # ton CO2 / (ton-km)
    data=None,                     # per-mode cost + inventory meta
    dist1=None,                    # Plant -> Crossdock (km)
    dist2=None,                    # Crossdock -> DC (km)
    dist2_new=None,                # NewLoc -> DC (km)
    dist3=None,                    # DC -> Retailer (km)
    lastmile_unit_cost=6.25,       # €/unit last-mile cost
    lastmile_CO2_kg=2.68,          # kg CO2 per unit last-mile
    CO_2_max=None,                 # direct CO2 cap (tons), if given
    CO_2_percentage=0.5,           # reduction vs CO2_base
    unit_penaltycost=1.7,          # kept for compatibility (unused here)
    unit_inventory_holdingCost=0.85,
    service_level = None,
# --- OPTIONAL: Enforce per-layer transport-mode shares (percentages) ---
# Provide dicts like {'air': 0.2, 'Water': 0.0, 'road': 0.8} (values will be normalized).
# You may also provide a tuple/list (air, Water, road).
mode_share_L1=None,
mode_share_L2=None,
mode_share_L1_by_plant=None,
mode_share_L2_by_origin=None,
mode_share_tol=1e-6,
    # NEW: per-location switches (None => backward compatible)
    # --- Layer 1 plants (existing) ---
    isTaiwan=None,
    isShanghai=None,
    # --- Layer 1/2 crossdocks (existing) ---
    isVienna=None,
    isGdansk=None,
    isParis=None,
    # --- Layer 2 new manufacturing locations (existing) ---
    isBudapest=None,
    isPrague=None,
    isCork=None,
    isHelsinki=None,
    isWarsaw=None,

    # NEW: generic switch dicts (lets you add new facilities/crossdocks without editing code)
    # Example: plant_switches={"TW": True, "SHA": False, "NEWP": True}
    plant_switches=None,
    crossdock_switches=None,
    newloc_switches=None,

    # NEW: allow overriding the superset node lists (useful when you add 2 more plants / more crossdocks)
    plants_all=None,
    crossdocks_all=None,
    new_locs_all=None,

    # --- Scenario toggles ---
    suez_canal=False,              # blocks Water on L1
    oil_crises=False,              # increases transport cost
    volcano=False,                 # blocks all air
    trade_war=False,               # increases sourcing cost
    tariff_rate=1.0,               # used with trade_war

    # --- Output verbosity ---
    print_results="YES",
    # road_lead_time=None,
):
    # ======================================================
    # 1. MASTER SETS & DEFAULT NETWORK DATA
    # ======================================================

    # Superset of locations (same IDs as your SC1F/SC2F)
    # Superset of locations (same IDs as your SC1F/SC2F)
    # You can override these from outside via plants_all / crossdocks_all / new_locs_all.
    Plants_all_default     = ["Taiwan", "Shanghai"]
    Crossdocks_all_default = ["Vienna", "Gdansk", "Paris"]
    New_Locs_all_default   = ["Budapest", "Prague", "Cork", "Helsinki", "Warsaw"]
    Dcs_all                = ["Pardubice", "Calais", "Riga", "Algeciras"]

    Plants_all     = Plants_all_default if plants_all is None else list(plants_all)
    Crossdocks_all = Crossdocks_all_default if crossdocks_all is None else list(crossdocks_all)
    New_Locs_all   = New_Locs_all_default if new_locs_all is None else list(new_locs_all)


    # Default demand (same as in SC2F)
    if demand is None:
        demand = {
            "Cologne": 17000,
            "Antwerp": 9000,
            "Krakow": 13000,
            "Kaunas": 19000,
            "Oslo": 15000,
            "Dublin": 20000,
            "Stockholm": 18000,
        }
    Retailers = list(demand.keys())

    # DC capacities (default)

    if service_level is None:
        print("[WARN] service_level not provided, defaulting to 0.9")
        service_level = 0.9
    else:
        print("[INFO] service_level received:", service_level)

    
    
    if dc_capacity is None:
        dc_capacity = {"Pardubice": 45000, "Calais": 150000, "Riga": 75000, "Algeciras": 100000}

    # Handling costs (€/unit)
    if handling_dc is None:
        handling_dc = {"Pardubice": 4.768269231, "Calais": 5.675923077,
                       "Riga": 4.426038462, "Algeciras": 7.0865}
    if handling_crossdock is None:
        handling_crossdock = {"Vienna": 6.533884615,
                              "Gdansk": 4.302269231,
                              "Paris": 5.675923077}
    # Sourcing & production CO2 at existing plants
    if sourcing_cost is None:
        sourcing_cost = {"Taiwan": 3.343692308, "Shanghai": 3.423384615}
    if co2_prod_kg_per_unit is None:
        co2_prod_kg_per_unit = {"Taiwan": 6.3, "Shanghai": 9.8}

    # New location parameters
    if new_loc_capacity is None:
        new_loc_capacity = {
            "Budapest": 37000, "Prague": 35500, "Cork": 46000,
            "Helsinki": 35000, "Warsaw": 26500,
        }
    if new_loc_openingCost is None:
        new_loc_openingCost = {
            "Budapest": 2.775e6, "Prague": 2.6625e6, "Cork": 3.45e6,
            "Helsinki": 2.625e6,   "Warsaw": 1.9875e6,
        }
    if new_loc_operationCost is None:
        new_loc_operationCost = {
            "Budapest": 250000, "Prague": 305000, "Cork": 450000,
            "Helsinki": 420000, "Warsaw": 412500,
        }
    if new_loc_CO2 is None:
        new_loc_CO2 = {
            "Budapest": 3.2, "Prague": 2.8, "Cork": 4.6,
            "Helsinki": 5.8, "Warsaw": 6.2,
        }

    # Transport emission factor (ton CO2 per ton-km)
    if co2_emission_factor is None:
        co2_emission_factor = {"air": 0.000971, "Water": 0.000027, "road": 0.000076}

    # Per-mode transport & inventory meta
    if data is None:
        data = {
            "transportation": ["air", "Water", "road"],
            "t (€/kg-km)":    [0.0105, 0.0013, 0.0054],
        }
    df = pd.DataFrame(data).set_index("transportation")

    # Add holding cost if not present
    if "h (€/unit)" not in df.columns:
        df["h (€/unit)"] = unit_inventory_holdingCost

    # Service level per mode
    service_level = {
        "air": service_level,
        "Water": service_level,
        "road": service_level,
    }
    df["h (â‚¬/unit)"] = 0.85

    # Build LT, z, φ, and SS(€/unit) if missing
    if True:
        average_distance = 9600  # rough benchmark
        speed = {"air": 800, "Water": 10, "road": 40}
        std_demand = np.std(list(demand.values()))

        # transportation artık index olduğu için mode sırasını df.index'ten alıyoruz
        modes = list(df.index)

        df["LT (days)"] = [
            np.round((average_distance * (1.2 if m == "Water" else 1)) / (speed[m] * 24), 13)
            for m in modes
        ]

        # Override with the fixed manual table used in SC1F.
        lt_manual = {"air": 0.5, "Water": 48.0, "road": 10.0}
        ss_manual = {
            "air": 2109.25627631292,
            "Water": 12055.4037653689,
            "road": 5711.89299799521,
        }
        df["LT (days)"] = [lt_manual[m] for m in df.index]
    df["SS (â‚¬/unit)"] = [ss_manual[m] for m in df.index]

        # Z ve phi değerlerini de aynı sırayla (df.index sırasıyla) üret
    z_values = [norm.ppf(service_level[m]) for m in modes]
    phi_values = [norm.pdf(z) for z in z_values]

    if True:

        df["Z-score Φ^-1(α)"] = z_values
        df["Density φ(Φ^-1(α))"] = phi_values

        df["SS (€/unit)"] = [
            np.sqrt(df.loc[m, "LT (days)"] + 1) * std_demand
            * (unit_penaltycost + df.loc[m, "h (€/unit)"])
            * df.loc[m, "Density φ(Φ^-1(α))"]
            for m in modes
        ]


 
    
    tau = {m: df.loc[m, "t (€/kg-km)"] for m in df.index}

    df["LT (days)"] = [0.5, 48.0, 10.0]
    df["SS (â‚¬/unit)"] = [2109.25627631292, 12055.4037653689, 5711.89299799521]

    # Distances (km); where missing, we use simple placeholders
    # Plant -> Crossdock (2 x 3)
    if dist1 is None:
        dist1 = pd.DataFrame(
            [[8997.94617146616, 8558.96520835034, 9812.38584027454],
             [8468.71339377354, 7993.62774285959, 9240.26233801075]],
            index=["Taiwan", "Shanghai"],
            columns=["Vienna", "Gdansk", "Paris"]
        )

    # Crossdock -> DC (3 x 4)
    if dist2 is None:
        dist2 = pd.DataFrame(
            [[220.423995674989, 1019.43140587827, 1098.71652257982, 1262.62587924823],
             [519.161031102087, 1154.87176862626, 440.338211856603, 1855.94939751482],
             [962.668288266132, 149.819604703365, 1675.455462176, 2091.1437090641]],
            index=["Vienna", "Gdansk", "Paris"],
            columns=["Pardubice", "Calais", "Riga", "Algeciras"]
        )

    # NewLoc -> DC (5 x 4)
    if dist2_new is None:
        dist2_new = pd.DataFrame(
            [[367.762425639798, 1216.10262027458, 1098.57245368619, 1120.13248546123],
             [98.034644813461, 818.765381327031, 987.72775809091, 1529.9990581232],
             [1558.60889112091, 714.077816812742, 1949.83469918776, 2854.35402610261],
             [1265.72892702748, 1758.18103997611, 367.698822815676, 2461.59771450036],
             [437.686419974076, 1271.77800922148, 554.373376462774, 1592.14058614186]],
            index=["Budapest", "Prague", "Cork", "Helsinki", "Warsaw"],
            columns=["Pardubice", "Calais", "Riga", "Algeciras"]
        )

    # DC -> Retailer (4 x 7) — placeholder; feel free to overwrite with true distances
    if dist3 is None:
        dist3 = pd.DataFrame(
            [[1184.65051865833, 933.730015948432, 557.144058480586, 769.757089072695, 2147.98445345001, 2315.79621115423, 1590.07662902924],
             [311.994969562194, 172.326685809878, 622.433010022067, 1497.40239816531, 1387.73696467636, 1585.6370207201, 1984.31926933368],
             [1702.34810062205, 1664.62283033352, 942.985120680279, 222.318687415142, 2939.50970842422, 3128.54724287652, 713.715034612432],
             [2452.23922908608, 2048.41487682505, 2022.91355628344, 1874.11994156457, 2774.73634842816, 2848.65086298747, 2806.05576441898]],
            index=["Pardubice","Calais","Riga","Algeciras"],
            columns=["Cologne","Antwerp","Krakow","Kaunas","Oslo","Dublin","Stockholm"]
        )
    # ======================================================
    # 2. ACTIVE SETS & MODES
    # ======================================================

    def _apply_switches(base_list, explicit_flags, extra_flags=None):
        """Apply per-node switches.
        - If ANY flag is explicitly provided (True/False), keep only nodes with True.
        - If all flags are None, keep base_list (backward compatible).
        """
        flags = dict(explicit_flags or {})
        if extra_flags:
            flags.update(extra_flags)

        if flags and any(v is not None for v in flags.values()):
            selected = {k for k, v in flags.items() if bool(v)}
            return [x for x in base_list if x in selected]
        return list(base_list)

    def _fill_missing_dict(d, keys, name="param", fallback=None):
        """Ensure dict covers all keys.
        Missing keys are filled with fallback (mean of existing values if fallback is None)."""
        dd = {} if d is None else dict(d)
        if fallback is None:
            fallback = float(np.mean(list(dd.values()))) if len(dd) > 0 else 0.0
        for k in keys:
            if k not in dd:
                dd[k] = fallback
        return dd

    # Base selection (existing behavior) via active_* lists
    Plants_base     = Plants_all if active_plants is None else list(active_plants)
    Crossdocks_base = Crossdocks_all if active_crossdocks is None else list(active_crossdocks)
    New_Locs_base   = New_Locs_all if active_new_locs is None else list(active_new_locs)
    Dcs             = Dcs_all if active_dcs is None else list(active_dcs)

    # --- Explicit flags (UI style) ---
    plant_flags_explicit = {"Taiwan": isTaiwan, "Shanghai": isShanghai}
    crossdock_flags_explicit = {"Vienna": isVienna, "Gdansk": isGdansk, "Paris": isParis}
    newloc_flags_explicit = {
        "Budapest": isBudapest,
        "Prague": isPrague,
        "Cork": isCork,
        "Helsinki": isHelsinki,
        "Warsaw": isWarsaw,
    }

    # --- Apply switches (explicit + dict-based) ---
    Plants     = _apply_switches(Plants_base, plant_flags_explicit, plant_switches)
    Crossdocks = _apply_switches(Crossdocks_base, crossdock_flags_explicit, crossdock_switches)
    New_Locs   = _apply_switches(New_Locs_base, newloc_flags_explicit, newloc_switches)

    # Make sure parameter dicts cover the active sets (if the user adds new nodes)
    handling_crossdock = _fill_missing_dict(handling_crossdock, Crossdocks, name="handling_crossdock")
    sourcing_cost = _fill_missing_dict(sourcing_cost, Plants, name="sourcing_cost")
    co2_prod_kg_per_unit = _fill_missing_dict(co2_prod_kg_per_unit, Plants, name="co2_prod_kg_per_unit")
    new_loc_capacity = _fill_missing_dict(new_loc_capacity, New_Locs, name="new_loc_capacity")
    new_loc_openingCost = _fill_missing_dict(new_loc_openingCost, New_Locs, name="new_loc_openingCost")
    new_loc_operationCost = _fill_missing_dict(new_loc_operationCost, New_Locs, name="new_loc_operationCost")
    new_loc_CO2 = _fill_missing_dict(new_loc_CO2, New_Locs, name="new_loc_CO2")
    dc_capacity = _fill_missing_dict(dc_capacity, Dcs, name="dc_capacity")
    handling_dc = _fill_missing_dict(handling_dc, Dcs, name="handling_dc")

    # --- Ensure distance matrices cover the active node sets ---
    def _ensure_dist_matrix(mat, idx, cols, name, fallback=None):
        """Reindex a distance DataFrame to (idx x cols) and fill missing with fallback.
        fallback defaults to the mean of existing numeric entries (or 10_000 if empty).
        """
        if mat is None:
            base = pd.DataFrame(index=idx, columns=cols, data=np.nan)
        else:
            base = mat.copy()

        if fallback is None:
            try:
                vals = pd.to_numeric(base.stack(), errors="coerce")
                fallback = float(vals.mean()) if np.isfinite(vals.mean()) else 10000.0
            except Exception:
                fallback = 10000.0

        out = base.reindex(index=idx, columns=cols)
        out = out.apply(pd.to_numeric, errors="coerce")
        if out.isna().any().any():
            if print_results == "YES":
                missing = int(out.isna().sum().sum())
                print(f"[WARN] {name} had {missing} missing distances; filled with {fallback}.")
            out = out.fillna(fallback)
        return out

    dist1 = _ensure_dist_matrix(dist1, Plants, Crossdocks, "dist1 (Plant->Crossdock)")
    dist2 = _ensure_dist_matrix(dist2, Crossdocks, Dcs, "dist2 (Crossdock->DC)")
    dist2_new = _ensure_dist_matrix(dist2_new, New_Locs, Dcs, "dist2_new (NewLoc->DC)")
    dist3 = _ensure_dist_matrix(dist3, Dcs, Retailers, "dist3 (DC->Retailer)")

    # Basic mode defaults


    ModesL1_default = ["air", "Water"]
    ModesL2_default = ["air", "Water", "road"]
    ModesL3_default = ["air", "Water", "road"]

    ModesL1 = ModesL1_default if active_modes_L1 is None else list(active_modes_L1)
    # L1 (Plant -> Crossdock): road is forbidden
    ModesL1 = [m for m in ModesL1 if m != "road"]
    ModesL2 = ModesL2_default if active_modes_L2 is None else list(active_modes_L2)
    ModesL3 = ModesL3_default if active_modes_L3 is None else list(active_modes_L3)

    # --- Mode-share parsing (node-based) ---
    # Goal:
    #   - Layer 1 (Plant -> Crossdock): enforce per-plant mode shares (air/Water only). Road is forbidden.
    #   - Layer 2 (Crossdock/NewLoc -> DC): enforce per-origin (crossdock or new loc) mode shares (air/Water/road).
    # Backward compatible:
    #   - If mode_share_L1_by_plant / mode_share_L2_by_origin are None, we fall back to global mode_share_L1 / mode_share_L2.

    def _parse_share_spec(spec, allowed_modes, name='mode_share'):
        """Parse a share spec into a dict over allowed_modes.

        spec can be:
          - dict like {'air':0.3, 'Water':None} (at most one None -> remainder to 1)
          - tuple/list aligned with allowed_modes length

        Missing keys are treated as 0.0.
        If no None is present, we accept sums close to 1; otherwise we normalize (with a warning) when sum != 1.
        """
        if spec is None:
            return None

        # Build raw dict
        if isinstance(spec, (list, tuple)):
            if len(spec) != len(allowed_modes):
                raise ValueError(f"{name}: expected {len(allowed_modes)} values for {allowed_modes}, got {len(spec)}")
            raw = {m: spec[i] for i, m in enumerate(allowed_modes)}
        elif isinstance(spec, dict):
            raw = {m: spec.get(m, 0.0) for m in allowed_modes}
        else:
            raise ValueError(f"{name}: must be a dict or a tuple/list of length {len(allowed_modes)}")

        # Count None (auto-remainder)
        none_modes = [m for m in allowed_modes if raw.get(m, 0.0) is None]
        if len(none_modes) > 1:
            raise ValueError(f"{name}: at most one mode can be None (auto remainder). Got None for {none_modes}")

        out = {}
        sum_known = 0.0
        for m in allowed_modes:
            v = raw.get(m, 0.0)
            if v is None:
                continue
            try:
                v = float(v)
            except Exception:
                raise ValueError(f"{name}: value for {m} must be numeric or None")
            if v < -mode_share_tol:
                raise ValueError(f"{name}: negative share for {m} is not allowed")
            v = 0.0 if abs(v) < mode_share_tol else v
            out[m] = v
            sum_known += v

        if len(none_modes) == 1:
            rem = 1.0 - sum_known
            if rem < -mode_share_tol:
                raise ValueError(f"{name}: shares sum to {sum_known:.6f} (>1). Cannot fill remainder.")
            rem = 0.0 if abs(rem) < mode_share_tol else rem
            out[none_modes[0]] = rem
        else:
            # No None: accept if sum close to 1, else normalize to avoid infeasibility
            s = sum_known
            if s <= mode_share_tol:
                # Degenerate (all zeros) -> keep zeros
                out = {m: 0.0 for m in allowed_modes}
            elif abs(s - 1.0) > 1e-4:
                if print_results == 'YES':
                    print(f"[WARN] {name}: shares sum to {s:.6f} (not 1). Normalizing to 1.")
                out = {m: v / s for m, v in out.items()}
            else:
                # Close enough
                out = {m: v for m, v in out.items()}

        # Ensure all allowed modes present
        out = {m: float(out.get(m, 0.0)) for m in allowed_modes}
        return out

    # ---- Build node-based share maps ----
    # L1: per plant shares over (air, Water)
    share_L1_by_plant = None
    if mode_share_L1_by_plant is not None:
        share_L1_by_plant = {}
        for p in Plants:
            if p not in mode_share_L1_by_plant:
                raise ValueError(f"mode_share_L1_by_plant missing entry for active plant '{p}'")
            share_L1_by_plant[p] = _parse_share_spec(
                mode_share_L1_by_plant[p],
                allowed_modes=['air', 'Water'],
                name=f"L1 share for plant {p}",
            )
    elif mode_share_L1 is not None:
        g = _parse_share_spec(mode_share_L1, allowed_modes=['air', 'Water'], name='global L1 share')
        share_L1_by_plant = {p: g for p in Plants}

    # L2: per origin (crossdock OR new loc) shares over (air, Water, road)
    share_L2_by_origin = None
    if mode_share_L2_by_origin is not None:
        share_L2_by_origin = {}
        # Crossdocks
        for c in Crossdocks:
            if c not in mode_share_L2_by_origin:
                raise ValueError(f"mode_share_L2_by_origin missing entry for active crossdock '{c}'")
            share_L2_by_origin[c] = _parse_share_spec(
                mode_share_L2_by_origin[c],
                allowed_modes=['air', 'Water', 'road'],
                name=f"L2 share for origin {c}",
            )
        # New locations
        for n in New_Locs:
            if n not in mode_share_L2_by_origin:
                raise ValueError(f"mode_share_L2_by_origin missing entry for active new loc '{n}'")
            share_L2_by_origin[n] = _parse_share_spec(
                mode_share_L2_by_origin[n],
                allowed_modes=['air', 'Water', 'road'],
                name=f"L2 share for origin {n}",
            )
    elif mode_share_L2 is not None:
        g = _parse_share_spec(mode_share_L2, allowed_modes=['air', 'Water', 'road'], name='global L2 share')
        share_L2_by_origin = {o: g for o in list(Crossdocks) + list(New_Locs)}

    # Ensure any positively requested mode exists in the per-layer mode sets (so vars/constraints exist)
    if share_L2_by_origin is not None:
        for o, smap in share_L2_by_origin.items():
            for mo, frac in smap.items():
                if frac > mode_share_tol and mo not in ModesL2:
                    ModesL2.append(mo)
    # Volcano: block all air → we keep modes in data but disallow flows via constraints
    if volcano:
        if "air" in ModesL1:
            ModesL1.remove("air")
        if "air" in ModesL2:
            ModesL2.remove("air")
        if "air" in ModesL3:
            ModesL3.remove("air")

    # Global set of modes used anywhere in the model
    Modes = sorted(set(ModesL1) | set(ModesL2) | set(ModesL3))

    # ======================================================
    # 3. SCENARIO IMPACTS ON COST PARAMETERS
    # ======================================================

    # Oil crisis: increase all transport costs
    if oil_crises:
        for m in tau:
            tau[m] *= 1.3

    # Trade war: increase sourcing cost at plants
    if trade_war:
        for p in sourcing_cost:
            sourcing_cost[p] *= tariff_rate

    product_weight_ton = product_weight / 1000.0

    # Simple per-unit variable cost at new locations (derived from capacity)
    new_loc_unitCost = {
        loc: (1.0 / new_loc_capacity[loc]) * 90000.0
        for loc in new_loc_capacity
    }

    # ======================================================
    # 4. MODEL & DECISION VARIABLES
    # ======================================================

    model = Model("MASTER_SC_Model")

    # Flows
    f1 = {}
    if len(Plants) > 0 and len(Crossdocks) > 0 and len(ModesL1) > 0:
        f1 = model.addVars(
            ((p, c, mo) for p in Plants for c in Crossdocks for mo in ModesL1),
            lb=0,
            name="f1",   # Plant → Crossdock
        )

    f2 = {}
    if len(Crossdocks) > 0 and len(Dcs) > 0 and len(ModesL2) > 0:
        f2 = model.addVars(
            ((c, d, mo) for c in Crossdocks for d in Dcs for mo in ModesL2),
            lb=0,
            name="f2",   # Crossdock → DC
        )

    f2_new = {}
    f2_2_bin = {}
    if len(New_Locs) > 0 and len(Dcs) > 0 and len(ModesL2) > 0:
        f2_new = model.addVars(
            ((n, d, mo) for n in New_Locs for d in Dcs for mo in ModesL2),
            lb=0,
            name="f2_2",   # NewLoc → DC
        )
        f2_2_bin = model.addVars(New_Locs, vtype=GRB.BINARY, name="f2_2_bin")
        
        
        

    f3 = {}
    if len(Dcs) > 0 and len(Retailers) > 0 and len(ModesL3) > 0:
        f3 = model.addVars(
            ((d, r, mo) for d in Dcs for r in Retailers for mo in ModesL3),
            lb=0,
            name="f3",   # DC → Retailer
        )

    # ======================================================
    # 4b. MODE-SHARE CONSTRAINTS
    # ======================================================

    # NOTE: Mode-share constraints are enforced in Section 6 (Constraints) on a per-node basis.

    # ======================================================
    # 5. COST & CO2 EXPRESSIONS
    # ======================================================

    # ---- Transport cost ----
    Transport_L1 = {}
    if f1:
        for mo in ModesL1:
            Transport_L1[mo] = quicksum(
                tau[mo] * dist1.loc[p, c] * product_weight * f1[p, c, mo]
                for p in Plants for c in Crossdocks
            )
    Total_Transport_L1 = quicksum(Transport_L1.values()) if Transport_L1 else 0

    Transport_L2 = {}
    if f2:
        for mo in ModesL2:
            Transport_L2[mo] = quicksum(
                tau[mo] * dist2.loc[c, d] * product_weight * f2[c, d, mo]
                for c in Crossdocks for d in Dcs
            )
    Total_Transport_L2 = quicksum(Transport_L2.values()) if Transport_L2 else 0

    Transport_L2_new = {}
    if f2_new:
        for mo in ModesL2:
            Transport_L2_new[mo] = quicksum(
                tau[mo] * dist2_new.loc[n, d] * product_weight * f2_new[n, d, mo]
                for n in New_Locs for d in Dcs
            )
    Total_Transport_L2_new = quicksum(Transport_L2_new.values()) if Transport_L2_new else 0

    Transport_L3 = {}
    if f3:
        for mo in ModesL3:
            Transport_L3[mo] = quicksum(
                tau[mo] * dist3.loc[d, r] * product_weight * f3[d, r, mo]
                for d in Dcs for r in Retailers
            )
    Total_Transport_L3 = quicksum(Transport_L3.values()) if Transport_L3 else 0

    Total_Transport = (
        Total_Transport_L1 + Total_Transport_L2 +
        Total_Transport_L2_new + Total_Transport_L3
    )

    # Last-mile cost
    LastMile_Cost = 0
    if f3:
        LastMile_Cost = lastmile_unit_cost * quicksum(
            f3[d, r, mo] for d in Dcs for r in Retailers for mo in ModesL3
        )

    # Handling cost
    Handling_L2 = 0
    if f2:
        Handling_L2 = quicksum(
            handling_crossdock[c] * f2[c, d, mo]
            for c in Crossdocks
            for d in Dcs
            for mo in ModesL2
        )

    Handling_L3 = 0
    if f3:
        Handling_L3 = quicksum(
            handling_dc[d] * f3[d, r, mo]
            for d in Dcs
            for r in Retailers
            for mo in ModesL3
        )

    # Sourcing at plants
    Sourcing_L1 = 0
    if f1:
        Sourcing_L1 = quicksum(
            sourcing_cost[p] * f1[p, c, mo]
            for p in Plants
            for c in Crossdocks
            for mo in ModesL1
        )

    # New location variable + fixed cost
    Cost_NewLoc_var = 0
    if f2_new:
        Cost_NewLoc_var = quicksum(
            new_loc_unitCost[n] * f2_new[n, d, mo]
            for n in New_Locs for d in Dcs for mo in ModesL2
        )

    Cost_NewLoc_fixed = 0
    if f2_2_bin:
        Cost_NewLoc_fixed = quicksum(
            new_loc_openingCost[n] * f2_2_bin[n]
            for n in New_Locs
        )

    Cost_NewLocs = Cost_NewLoc_var + Cost_NewLoc_fixed

    # ---- Inventory cost (transit + safety stock proxy, SC1F-style) ----
    total_demand = sum(demand.values())

    # L1: Plant -> Crossdock
    InvCost_L1 = 0
    if f1:
        InvCost_L1 = quicksum(
            f1[p, c, mo] * (
                df.loc[mo, "LT (days)"] * df.loc[mo, "h (€/unit)"]
                + df.loc[mo, "SS (€/unit)"] / total_demand
            )
            for p in Plants for c in Crossdocks for mo in ModesL1
        )

    # L2 (existing): Crossdock -> DC
    InvCost_L2 = 0
    if f2:
        InvCost_L2 = quicksum(
            f2[c, d, mo] * (
                df.loc[mo, "LT (days)"] * df.loc[mo, "h (€/unit)"]
                + df.loc[mo, "SS (€/unit)"] / total_demand
            )
            for c in Crossdocks for d in Dcs for mo in ModesL2
        )

    # L2 (new plants): New_Loc -> DC
    InvCost_L2_new = 0
    if f2_new:
        InvCost_L2_new = quicksum(
            f2_new[n, d, mo] * (
                df.loc[mo, "LT (days)"] * df.loc[mo, "h (€/unit)"]
                + df.loc[mo, "SS (€/unit)"] / total_demand
            )
            for n in New_Locs for d in Dcs for mo in ModesL2
        )

    # L3: DC -> Retailer
    InvCost_L3 = 0
    if f3:
        InvCost_L3 = quicksum(
            f3[d, r, mo] * (
                df.loc[mo, "LT (days)"] * df.loc[mo, "h (€/unit)"]
                + df.loc[mo, "SS (€/unit)"] / total_demand
            )
            for d in Dcs for r in Retailers for mo in ModesL3
        )

    Total_InvCost_Model = InvCost_L1 + InvCost_L2 + InvCost_L2_new + InvCost_L3




    # ---- CO2 emissions ----
    # Production at existing plants
    CO2_prod_L1 = 0
    if f1:
        CO2_prod_L1 = quicksum(
            (co2_prod_kg_per_unit[p] / 1000.0) *
            quicksum(f1[p, c, mo] for c in Crossdocks for mo in ModesL1)
            for p in Plants
        )

    # Production at new locations
    CO2_prod_new = 0
    if f2_new:
        CO2_prod_new = quicksum(
            (new_loc_CO2[n] / 1000.0) *
            quicksum(f2_new[n, d, mo] for d in Dcs for mo in ModesL2)
            for n in New_Locs
        )

    # Transport CO2 by layer/mode
    CO2_tr_L1_by_mode = {}
    if f1:
        for mo in ModesL1:
            CO2_tr_L1_by_mode[mo] = quicksum(
                co2_emission_factor[mo] * dist1.loc[p, c] * product_weight_ton * f1[p, c, mo]
                for p in Plants for c in Crossdocks
            )

    CO2_tr_L2_by_mode = {}
    if f2:
        for mo in ModesL2:
            CO2_tr_L2_by_mode[mo] = quicksum(
                co2_emission_factor[mo] * dist2.loc[c, d] * product_weight_ton * f2[c, d, mo]
                for c in Crossdocks for d in Dcs
            )

    CO2_tr_L2_new_by_mode = {}
    if f2_new:
        for mo in ModesL2:
            CO2_tr_L2_new_by_mode[mo] = quicksum(
                co2_emission_factor[mo] * dist2_new.loc[n, d] * product_weight_ton * f2_new[n, d, mo]
                for n in New_Locs for d in Dcs
            )

    CO2_tr_L3_by_mode = {}
    if f3:
        for mo in ModesL3:
            CO2_tr_L3_by_mode[mo] = quicksum(
                co2_emission_factor[mo] * dist3.loc[d, r] * product_weight_ton * f3[d, r, mo]
                for d in Dcs for r in Retailers
            )

    # Summed by layer
    CO2_tr_L1 = quicksum(CO2_tr_L1_by_mode.values()) if CO2_tr_L1_by_mode else 0
    CO2_tr_L2 = quicksum(CO2_tr_L2_by_mode.values()) if CO2_tr_L2_by_mode else 0
    CO2_tr_L2_new = quicksum(CO2_tr_L2_new_by_mode.values()) if CO2_tr_L2_new_by_mode else 0
    CO2_tr_L3 = quicksum(CO2_tr_L3_by_mode.values()) if CO2_tr_L3_by_mode else 0

    # Last-mile CO2
    LastMile_CO2 = 0
    if f3:
        LastMile_CO2 = (lastmile_CO2_kg / 1000.0) * quicksum(
            f3[d, r, mo] for d in Dcs for r in Retailers for mo in ModesL3
        )

    Total_CO2 = CO2_prod_L1 + CO2_prod_new + CO2_tr_L1 + CO2_tr_L2 + CO2_tr_L2_new + CO2_tr_L3 + LastMile_CO2

    # Simple CO2 cost (manufacturing only, like your original)
    CO2_Mfg_existing = co2_cost_per_ton * CO2_prod_L1
    CO2_Mfg_new = co2_cost_per_ton_New * CO2_prod_new
    CO2_Mfg = CO2_Mfg_existing + CO2_Mfg_new

    # ======================================================
    # 6. CONSTRAINTS
    # ======================================================

    # Demand satisfaction
    if f3:
        model.addConstrs(
            (
                quicksum(f3[d, r, mo] for d in Dcs for mo in ModesL3) >= demand[r]
                for r in Retailers
            ),
            name="Demand",
        )

    # DC balance: inbound from crossdocks + new locs == outbound to retailers
    if f3:
        model.addConstrs(
            (
                quicksum(f2[c, d, mo] for c in Crossdocks for mo in ModesL2) +
                quicksum(f2_new[n, d, mo] for n in New_Locs for mo in ModesL2)
                ==
                quicksum(f3[d, r, mo] for r in Retailers for mo in ModesL3)
                for d in Dcs
            ),
            name="DCBalance",
        )

    # Crossdock balance: inbound from plants == outbound to DCs
    if f1 and f2:
        model.addConstrs(
            (
                quicksum(f1[p, c, mo] for p in Plants for mo in ModesL1)
                ==
                quicksum(f2[c, d, mo] for d in Dcs for mo in ModesL2)
                for c in Crossdocks
            ),
            name="CrossdockBalance",
        )

    # ------------------------------------------------------
    # Transport-mode share enforcement (node-based)
    # ------------------------------------------------------

    # L1 (Plant -> Crossdock): road forbidden (safety net)
    if f1 and "road" in ModesL1:
        model.addConstrs(
            (f1[p, c, "road"] == 0 for p in Plants for c in Crossdocks),
            name="NoRoad_L1",
        )

    # L1 per-plant shares
    if share_L1_by_plant is not None and f1:
        for p in Plants:
            total_p = quicksum(f1[p, c, mo] for c in Crossdocks for mo in ModesL1)
            smap = share_L1_by_plant[p]
            for mo, frac in smap.items():
                if mo in ModesL1:
                    model.addConstr(
                        quicksum(f1[p, c, mo] for c in Crossdocks) == frac * total_p,
                        name=f"ModeShare_L1_{p}_{mo}",
                    )

    # L2 per-origin shares (Crossdocks and NewLocs)
    if share_L2_by_origin is not None:
        if f2:
            for c in Crossdocks:
                total_c = quicksum(f2[c, d, mo] for d in Dcs for mo in ModesL2)
                smap = share_L2_by_origin[c]
                for mo, frac in smap.items():
                    if mo in ModesL2:
                        model.addConstr(
                            quicksum(f2[c, d, mo] for d in Dcs) == frac * total_c,
                            name=f"ModeShare_L2_{c}_{mo}",
                        )
        if f2_new:
            for n in New_Locs:
                total_n = quicksum(f2_new[n, d, mo] for d in Dcs for mo in ModesL2)
                smap = share_L2_by_origin[n]
                for mo, frac in smap.items():
                    if mo in ModesL2:
                        model.addConstr(
                            quicksum(f2_new[n, d, mo] for d in Dcs) == frac * total_n,
                            name=f"ModeShare_L2_{n}_{mo}",
                        )

    # DC capacity
    if f3:
        model.addConstrs(
            (
                quicksum(f3[d, r, mo] for r in Retailers for mo in ModesL3)
                <= dc_capacity[d]
                for d in Dcs
            ),
            name="DCCapacity",
        )

    # New location capacity linking to binary open decision
    if f2_new and f2_2_bin:
        model.addConstrs(
            (
                quicksum(f2_new[n, d, mo] for d in Dcs for mo in ModesL2)
                <= new_loc_capacity[n] * f2_2_bin[n]
                for n in New_Locs
            ),
            name="NewLocCapacity",
        )

    # C02 Enforcement

    model.addConstr(
        Total_CO2 <= CO2_base * (1 - CO_2_percentage),
        name="CO2ReductionTarget"
    )
    if f2_2_bin and len(New_Locs) > 0:
        model.addConstr(quicksum(f2_2_bin[n] for n in New_Locs) == len(New_Locs), name="ForceOpen_SelectedNewLocs")


    # Scenario-specific structural constraints

    # SUEZ CANAL BLOCKADE → block Water on L1
    if suez_canal and f1 and ("Water" in ModesL1):
        model.addConstrs(
            (
                f1[p, c, "Water"] == 0
                for p in Plants for c in Crossdocks
            ),
            name="WaterDamage_f1",
        )

    # VOLCANO: block air on all layers (in addition to mode removal above)
    # If user kept 'air' in some Modes* list, we block via constraints.
    if volcano:
        # L1
        if f1 and "air" in ModesL1:
            model.addConstrs(
                (
                    f1[p, c, "air"] == 0
                    for p in Plants for c in Crossdocks
                ),
                name="Volcano_block_f1",
            )
        # L2 (from crossdocks)
        if f2 and "air" in ModesL2:
            model.addConstrs(
                (
                    f2[c, d, "air"] == 0
                    for c in Crossdocks for d in Dcs
                ),
                name="Volcano_block_f2",
            )
        # L2 (from new locs)
        if f2_new and "air" in ModesL2:
            model.addConstrs(
                (
                    f2_new[n, d, "air"] == 0
                    for n in New_Locs for d in Dcs
                ),
                name="Volcano_block_f2_new",
            )
        # L3
        if f3 and "air" in ModesL3:
            model.addConstrs(
                (
                    f3[d, r, "air"] == 0
                    for d in Dcs for r in Retailers
                ),
                name="Volcano_block_f3",
            )

    # ======================================================
    # 7. OBJECTIVE
    # ======================================================

    model.setObjective(
        Sourcing_L1
        + Handling_L2
        + Handling_L3
        + LastMile_Cost
        + CO2_Mfg
        + Total_Transport
        + Total_InvCost_Model
        + Cost_NewLocs,
        GRB.MINIMIZE,
    )

    # ======================================================
    # 8. SOLVE
    # ======================================================

    model.optimize()

        # ------------------------------
    # FLOW MATRICES (UI için)
    # ------------------------------
    f1_matrix   = print_flows(f1, Plants, Crossdocks, ModesL1, "f1 (Plant → Crossdock)")
    f2_matrix   = print_flows(f2, Crossdocks, Dcs, ModesL2, "f2 (Crossdock → DC)")
    f2_2matrix  = print_flows(f2_new, New_Locs, Dcs, ModesL2, "f2 new (New Locs → DC)")
    f3_matrix   = print_flows(f3, Dcs, Retailers, ModesL3, "f3 (DC → Retailer)")

    # ------------------------------
    # COST / CO2 NUMERICS
    # ------------------------------
    def _safe_val(x):
        try:
            return float(x.getValue())
        except Exception:
            try:
                return float(x)
            except Exception:
                return 0.0

    # Transport totals (MASTER.py’de bunlar var)
    T_L1     = _safe_val(Total_Transport_L1)
    T_L2     = _safe_val(Total_Transport_L2)
    T_L2_new = _safe_val(Total_Transport_L2_new)
    T_L3     = _safe_val(Total_Transport_L3)

    # Inventory (MASTER.py’de InvCost_* var)
    I_L1     = _safe_val(InvCost_L1)
    I_L2     = _safe_val(InvCost_L2)
    I_L2_new = _safe_val(InvCost_L2_new)
    I_L3     = _safe_val(InvCost_L3)

    # Last mile
    LM_cost  = _safe_val(LastMile_Cost)

    # Sourcing & Handling (MASTER.py’de Handling_L2_existing yok)
    S_L1     = _safe_val(Sourcing_L1)
    H_L2     = _safe_val(Handling_L2)
    H_L3     = _safe_val(Handling_L3)

    # New locations: variable + fixed
    FixedCost_NewLocs = _safe_val(Cost_NewLoc_fixed)
    ProdCost_NewLocs  = _safe_val(Cost_NewLoc_var)

    # CO2 parçaları (MASTER.py’de hesaplanıyor)
    E_air        = _safe_val((CO2_tr_L1_by_mode.get("air", 0) if 'CO2_tr_L1_by_mode' in locals() else 0) +
                             (CO2_tr_L2_by_mode.get("air", 0) if 'CO2_tr_L2_by_mode' in locals() else 0) +
                             (CO2_tr_L2_new_by_mode.get("air", 0) if 'CO2_tr_L2_new_by_mode' in locals() else 0) +
                             (CO2_tr_L3_by_mode.get("air", 0) if 'CO2_tr_L3_by_mode' in locals() else 0))

    E_Water        = _safe_val((CO2_tr_L1_by_mode.get("Water", 0) if 'CO2_tr_L1_by_mode' in locals() else 0) +
                             (CO2_tr_L2_by_mode.get("Water", 0) if 'CO2_tr_L2_by_mode' in locals() else 0) +
                             (CO2_tr_L2_new_by_mode.get("Water", 0) if 'CO2_tr_L2_new_by_mode' in locals() else 0) +
                             (CO2_tr_L3_by_mode.get("Water", 0) if 'CO2_tr_L3_by_mode' in locals() else 0))

    E_road       = _safe_val((CO2_tr_L2_by_mode.get("road", 0) if 'CO2_tr_L2_by_mode' in locals() else 0) +
                             (CO2_tr_L2_new_by_mode.get("road", 0) if 'CO2_tr_L2_new_by_mode' in locals() else 0) +
                             (CO2_tr_L3_by_mode.get("road", 0) if 'CO2_tr_L3_by_mode' in locals() else 0))

    E_lastmile   = _safe_val(LastMile_CO2)
    E_production = _safe_val(CO2_prod_L1 + CO2_prod_new)

    CO2_total    = _safe_val(Total_CO2)

    if print_results == "YES":
        print("Transport L1:", T_L1)
        print("Transport L2:", T_L2)
        print("Transport L2 new:", T_L2_new)
        print("Transport L3:", T_L3)

        print("Inventory L1:", I_L1)
        print("Inventory L2:", I_L2)
        print("Inventory L2 new:", I_L2_new)
        print("Inventory L3:", I_L3)

        print("Fixed Last Mile:", LM_cost)

        print(f"Sourcing_L1: {S_L1:,.2f}")
        print(f"Handling_L2_total: {H_L2:,.2f}")
        print(f"Handling_L3: {H_L3:,.2f}")

        print("Fixed new locs:", FixedCost_NewLocs)
        print("Prod new locs:", ProdCost_NewLocs)
        print("CO2 total:", CO2_total)
        print("Total objective:", model.ObjVal)

    results = {
        # --- Flow matrices (UI) ---
        "f1_matrix": f1_matrix,
        "f2_matrix": f2_matrix,
        "f2_2matrix": f2_2matrix,
        "f3_matrix": f3_matrix,

        # --- Transport Costs ---
        "Transport_L1": T_L1,
        "Transport_L2": T_L2,
        "Transport_L2_new": T_L2_new,
        "Transport_L3": T_L3,

        # --- Inventory Costs ---
        "Inventory_L1": I_L1,
        "Inventory_L2": I_L2,
        "Inventory_L2_new": I_L2_new,
        "Inventory_L3": I_L3,

        # --- Last Mile ---
        "Fixed_Last_Mile": LM_cost,

        # --- Sourcing & Handling ---
        "Sourcing_L1": S_L1,
        "Handling_L2_existing": H_L2,   # MASTER.py’de ayrı yok; aynı değeri veriyorum
        "Handling_L2_total": H_L2,
        "Handling_L3": H_L3,

        # --- New Locations & Production ---
        "FixedCost_NewLocs": FixedCost_NewLocs,
        "ProdCost_NewLocs": ProdCost_NewLocs,

        # --- Emission Calculations ---
        "E_air": E_air,
        "E_Water": E_Water,
        "E_road": E_road,
        "E_lastmile": E_lastmile,
        "E_production": E_production,
        "CO2_Total": CO2_total,

        # --- Objective ---
        "Objective_value": model.ObjVal,
        "Status": model.Status,
        "ModeShare_L1_target": None if share_L1_by_plant is None else (share_L1_by_plant[Plants[0]] if len(Plants)>0 else None),
        "ModeShare_L2_target": None if share_L2_by_origin is None else (share_L2_by_origin[list(share_L2_by_origin.keys())[0]] if len(share_L2_by_origin)>0 else None),
        "ModeShare_L1_by_plant": share_L1_by_plant,
        "ModeShare_L2_by_origin": share_L2_by_origin,
    }

    return results, model
