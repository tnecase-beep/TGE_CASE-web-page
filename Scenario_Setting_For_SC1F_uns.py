# -*- coding: utf-8 -*-
"""
Created on Tue Oct 14 10:37:00 2025

@author: LENOVO
"""

from gurobipy import Model, GRB, quicksum
import pandas as pd
import numpy as np
from statistics import NormalDist as _ND; _nd = _ND(); norm = type('norm', (), {'pdf': staticmethod(_nd.pdf), 'ppf': staticmethod(_nd.inv_cdf), 'cdf': staticmethod(_nd.cdf)})()
from helpers import print_flows, print_mode_breakdown, compute_inventory_cost, compute_transport_cost
import time



GA_MEASUREMENT_ID = "G-3H3B3BNF4Z"







def run_scenario(
    dc_capacity=None,
    demand=None,
    handling_dc=None,
    handling_crossdock=None,
    sourcing_cost=None,
    co2_prod_kg_per_unit=None,
    product_weight=2.58,
    co2_cost_per_ton=37.50,
    co2_cost_per_ton_New=60.00,
    CO2_base=1582.42366689614,
    new_loc_capacity=None,
    new_loc_openingCost=None,
    new_loc_operationCost=None,
    new_loc_CO2=None,
    co2_emission_factor=None,
    data=None,
    lastmile_unit_cost=6.25,
    lastmile_CO2_kg= 2.68,
    CO_2_max=None,
    CO_2_percentage=0.5,
    unit_penaltycost = 1.7,
    print_results = "YES",
    unit_inventory_holdingCost=0.85,
    suez_canal = False,
    oil_crises = False,
    volcano = False,
    trade_war = False,
    tariff_rate=1,
    service_level = 0.9
):
    # =====================================================
    # DEFAULT DATA (filled from original SC2)
    # =====================================================
    if demand is None:
        demand = {
            "Cologne": 17000, "Antwerp": 9000, "Krakow": 13000,
            "Kaunas": 19000, "Oslo": 15000, "Dublin": 20000, "Stockholm": 18000
        }
    
    if dc_capacity is None:
        dc_capacity = {"Pardubice": 45000, "Calais": 150000, "Riga": 75000, "Algeciras": 100000}
    
    if handling_dc is None:
        handling_dc = {"Pardubice": 4.768269231, "Calais": 5.675923077, "Riga": 4.426038462, "Algeciras": 7.0865}
    
    if handling_crossdock is None:
        handling_crossdock = {"Vienna": 6.533884615, "Gdansk": 4.302269231, "Paris": 5.675923077}
    
    if sourcing_cost is None:
        sourcing_cost = {"Taiwan": 3.343692308, "Shanghai": 3.423384615}
    
    if co2_prod_kg_per_unit is None:
        co2_prod_kg_per_unit = {"Taiwan": 6.3, "Shanghai": 9.8}
    
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
            "Helsinki": 420000, "Warsaw": 412500
        }
    
    if new_loc_CO2 is None:
        new_loc_CO2 = {
            "Budapest": 3.2, "Prague": 2.8, "Cork": 4.6,
            "Helsinki": 5.8, "Warsaw": 6.2
        }
    
    if co2_emission_factor is None:
        co2_emission_factor = {"air": 0.000971, "Water": 0.000027, "road": 0.000076}
    
    service_level = {'air': service_level, 'Water': service_level, 'road': service_level}
    average_distance = 9600
    speed = {'air': 800, 'Water': 10, 'road': 40}
    std_demand = np.std(list(demand.values()))

    if data is None:
        data = {
            "transportation": ["air", "Water", "road"],
            "t (€/kg-km)": [0.0105, 0.0013, 0.0054],
        }
    
    # h (€/unit)
    data["h (€/unit)"] = [0.85, 0.85, 0.85]
    
    # LT (days)
    data["LT (days)"] = [0.5, 48, 10]    
    # Z-scores and Densities
    z_values = [norm.ppf(α) for α in service_level.values()]
    phi_values = [norm.pdf(z) for z in z_values]
    
    data["Z-score Φ^-1(α)"] = z_values
    data["Density φ(Φ^-1(α))"] = phi_values
    
    # SS (€/unit) = √(LT + 1) * σ * (p + h) * φ(z)
    data["SS (€/unit)"] = [2109.25627631292, 12055.4037653689, 5711.89299799521]    
    
    
    Modes = ["air", "Water", "road"]
    ModesL1 = ["air", "Water"]
    Plants = ["Taiwan", "Shanghai"]
    Crossdocks = ["Vienna", "Gdansk", "Paris"]
    New_Locs = ["Budapest", "Prague", "Cork", "Helsinki", "Warsaw"]
    Dcs = ["Pardubice", "Calais", "Riga", "Algeciras"]
    Retailers = list(demand.keys())
    product_weight_ton = product_weight / 1000.0
    
    df = pd.DataFrame(data).set_index("transportation")
    
    
    tau = df["t (€/kg-km)"].to_dict()


    new_loc_totalCost = {
        loc: new_loc_openingCost[loc] + new_loc_operationCost[loc]
        for loc in new_loc_openingCost
    }
    
    new_loc_unitCost = {loc: (1 / cap) * 90000 for loc, cap in new_loc_capacity.items()}
    
    print(df)
    print(df["LT (days)"])
    print(df["SS (€/unit)"])

    # -----------------------------
    # DISTANCES (in km)
    # -----------------------------
    dist1 = pd.DataFrame(
        [[8997.94617146616, 8558.96520835034, 9812.38584027454],
         [8468.71339377354, 7993.62774285959, 9240.26233801075]],
        index=["Taiwan","Shanghai"],
        columns=["Vienna","Gdansk","Paris"]
    )
    
    dist2 = pd.DataFrame(
        [[220.423995674989, 1019.43140587827, 1098.71652257982, 1262.62587924823],
         [519.161031102087, 1154.87176862626, 440.338211856603, 1855.94939751482],
         [962.668288266132, 149.819604703365, 1675.455462176, 2091.1437090641]],
        index=["Vienna","Gdansk","Paris"],
        columns=["Pardubice","Calais","Riga","Algeciras"]
    )
    
    dist2_2 = pd.DataFrame([[367.762425639798, 1216.10262027458, 1098.57245368619, 1120.13248546123],
                            [98.034644813461, 818.765381327031, 987.72775809091, 1529.9990581232],
                            [1558.60889112091, 714.077816812742, 1949.83469918776, 2854.35402610261],
                            [1265.72892702748, 1758.18103997611, 367.698822815676, 2461.59771450036],
                            [437.686419974076, 1271.77800922148, 554.373376462774, 1592.14058614186]],
                           index=["Budapest", "Prague", "Cork", "Helsinki", "Warsaw"],
                           columns = ["Pardubice","Calais","Riga","Algeciras"]
                           )
    
    dist3 = pd.DataFrame(
        [[1184.65051865833, 933.730015948432, 557.144058480586, 769.757089072695, 2147.98445345001, 2315.79621115423, 1590.07662902924],
         [311.994969562194, 172.326685809878, 622.433010022067, 1497.40239816531, 1387.73696467636, 1585.6370207201, 1984.31926933368],
         [1702.34810062205, 1664.62283033352, 942.985120680279, 222.318687415142, 2939.50970842422, 3128.54724287652, 713.715034612432],
         [2452.23922908608, 2048.41487682505, 2022.91355628344, 1874.11994156457, 2774.73634842816, 2848.65086298747, 2806.05576441898]],
        index=["Pardubice","Calais","Riga","Algeciras"],
        columns=["Cologne","Antwerp","Krakow","Kaunas","Oslo","Dublin","Stockholm"]
    )
    
    # -----------------------------
    # MODEL
    # -----------------------------
    
    model = Model("SC2 Model")

    # Flow variables

    f1 = model.addVars(((p, c, mo) for p in Plants for c in Crossdocks for mo in ModesL1),
                       lb=0, name="f1")  # Plant → Crossdock

    f2 = model.addVars(((c, d, mo) for c in Crossdocks for d in Dcs for mo in Modes),
                       lb=0, name="f2")  # Crossdock → DC



    f3 = model.addVars(((d, r, mo) for d in Dcs for r in Retailers for mo in Modes),
                       lb=0, name="f3")  # DC → Retailer
    
    
    # Slack variables for unmet demand at each retailer
    v = model.addVars(Retailers, name="v", lb=0)
    # -----------------------------
    # CO2_Calculations
    # -----------------------------
    
    # Transport CO2
    CO2_tr_L1 = quicksum(
        co2_emission_factor[mo] * dist1.loc[p, c] * product_weight_ton * f1[p, c, mo]
        for p in Plants for c in Crossdocks for mo in ModesL1
    )

    CO2_tr_L2 = quicksum(
        co2_emission_factor[mo] * dist2.loc[c, d] * product_weight_ton * f2[c, d, mo]
        for c in Crossdocks for d in Dcs for mo in Modes
    )
    
    CO2_tr_L3 = quicksum(
        co2_emission_factor[mo] * dist3.loc[d, r] * product_weight_ton * f3[d, r, mo]
        for d in Dcs for r in Retailers for mo in Modes
    )

    # Production CO2
    CO2_prod_L1 = quicksum(
        co2_prod_kg_per_unit[p] * quicksum(f1[p, c, mo] for c in Crossdocks for mo in ModesL1)
        for p in Plants
    ) / 1000.0   # kg -> tons

    LastMile_CO2 = (lastmile_CO2_kg/1000)* quicksum(
        f3[d, r, mo] for d in Dcs for r in Retailers for mo in Modes
    )
    
    # Total = production (L1 + L2_2) + transport (L1 + L2 + L3)
    Total_CO2 = CO2_prod_L1 + CO2_tr_L1 + CO2_tr_L2 + CO2_tr_L3 + LastMile_CO2 
    
    #Emission to get
    # ---------- CO2 breakdown by transport mode ----------
    # L1 (only air & Water)
    CO2_tr_L1_air = quicksum(
        co2_emission_factor["air"] * dist1.loc[p, c] * product_weight_ton * f1[p, c, "air"]
        for p in Plants for c in Crossdocks
    )
    CO2_tr_L1_Water = quicksum(
        co2_emission_factor["Water"] * dist1.loc[p, c] * product_weight_ton * f1[p, c, "Water"]
        for p in Plants for c in Crossdocks
    )
    
    # L2
    CO2_tr_L2_air  = quicksum(co2_emission_factor["air"]  * dist2.loc[c, d] * product_weight_ton * f2[c, d, "air"]
                              for c in Crossdocks for d in Dcs)
    CO2_tr_L2_Water  = quicksum(co2_emission_factor["Water"]  * dist2.loc[c, d] * product_weight_ton * f2[c, d, "Water"]
                              for c in Crossdocks for d in Dcs)
    CO2_tr_L2_road = quicksum(co2_emission_factor["road"] * dist2.loc[c, d] * product_weight_ton * f2[c, d, "road"]
                              for c in Crossdocks for d in Dcs)
    
    # L3
    CO2_tr_L3_air  = quicksum(co2_emission_factor["air"]  * dist3.loc[d, r] * product_weight_ton * f3[d, r, "air"]
                              for d in Dcs for r in Retailers)
    CO2_tr_L3_Water  = quicksum(co2_emission_factor["Water"]  * dist3.loc[d, r] * product_weight_ton * f3[d, r, "Water"]
                              for d in Dcs for r in Retailers)
    CO2_tr_L3_road = quicksum(co2_emission_factor["road"] * dist3.loc[d, r] * product_weight_ton * f3[d, r, "road"]
                              for d in Dcs for r in Retailers)

    
    # -----------------------------
    # COST CALCULATIONS
    # -----------------------------
    # Transport cost
    # -----------------------------
    Transport_L1 = {}
    for mo in ModesL1:
        Transport_L1[mo] = quicksum(
            tau[mo] * dist1.loc[p, c] * product_weight * f1[p, c, mo]
            for p in Plants for c in Crossdocks
        )

    Total_Transport_L1 = quicksum(Transport_L1[mo] for mo in ModesL1)

    Transport_L2 = {}

    for mo in Modes: 
        Transport_L2[mo]= quicksum(
            tau[mo]* dist2.loc[c,d]* product_weight* f2[c, d, mo]
            for c in Crossdocks for d in Dcs
            )



    Total_Transport_L2 = quicksum(Transport_L2[mo] for mo in Modes)

    Transport_L3 = {}

    for mo in Modes:
        Transport_L3[mo] = quicksum(
           tau[mo]* dist3.loc[d,r]* product_weight* f3[d,r,mo]
           for d in Dcs for r in Retailers
           )

    Total_Transport_L3 = quicksum(Transport_L3[mo] for mo in Modes)

    Total_Transport = Total_Transport_L1 + Total_Transport_L2 + Total_Transport_L3

    # ================= INVENTORY COST DEFINITIONS =================
    # Layer 1
    InvCost_L1 = {}
    for mo in ModesL1:
        InvCost_L1[mo] = (
            quicksum(
                f1[p, c, mo] * df.loc[mo, "LT (days)"] * df.loc[mo, "h (€/unit)"]
                for p in Plants for c in Crossdocks
            )
            + quicksum(
                f1[p, c, mo] * df.loc[mo, "SS (€/unit)"] / sum(demand.values())
                for p in Plants for c in Crossdocks
            )
        )
    
    Total_InvCost_L1 = quicksum(InvCost_L1[mo] for mo in ModesL1)

    # Layer 2
    InvCost_L2 = {}
    for mo in Modes:
        InvCost_L2[mo] = (
            quicksum(
                f2[c, d, mo] * df.loc[mo, "LT (days)"] * df.loc[mo, "h (€/unit)"]
                for c in Crossdocks for d in Dcs
            )
            + quicksum(
                f2[c, d, mo] * df.loc[mo, "SS (€/unit)"] / sum(demand.values())
                for c in Crossdocks for d in Dcs
            )
        )
    
    Total_InvCost_L2 = quicksum(InvCost_L2[mo] for mo in Modes)
    
    
    Whole_L2 = Total_InvCost_L2 
    
    # Layer 3
    InvCost_L3 = {}
    for mo in Modes:
        InvCost_L3[mo] = (
            quicksum(
                f3[d, r, mo] * df.loc[mo, "LT (days)"] * df.loc[mo, "h (€/unit)"]
                for d in Dcs for r in Retailers
            )
            + quicksum(
                f3[d, r, mo] * df.loc[mo, "SS (€/unit)"] / sum(demand.values())
                for d in Dcs for r in Retailers
            )
        )
    
    Total_InvCost_L3 = quicksum(InvCost_L3[mo] for mo in Modes)
    
    # Combine
    Total_InvCost_Model = Total_InvCost_L1 + Whole_L2 + Total_InvCost_L3



    ######################## Sourcing & handling ##############################3
    Sourcing_L1 = quicksum(sourcing_cost[p] * quicksum(f1[p, c, mo] for c in Crossdocks for mo in ModesL1) for p in Plants)

    # Existing 
    Handling_L2_existing = quicksum(
        handling_crossdock[c] * quicksum(f2[c, d, mo] for d in Dcs for mo in Modes)
        for c in Crossdocks
    )

    Handling_L2 = Handling_L2_existing 

    Handling_L3 = quicksum(handling_dc[d] * quicksum(f3[d, r, mo] for r in Retailers for mo in Modes) for d in Dcs)

    ############################# CO2 Costs ##############################3

    # CO2 manufacturing (€/kg * kg_CO2_per_unit * units)
    CO2_Mfg = co2_cost_per_ton/1000 * quicksum(
        co2_prod_kg_per_unit[p] * quicksum(f1[p, c, mo] for c in Crossdocks for mo in ModesL1)
        for p in Plants
    )



    # Last-mile cost (per unit delivered)
    LastMile_Cost = (lastmile_unit_cost) * quicksum(
        f3[d, r, mo] for d in Dcs for r in Retailers for mo in Modes
    )

    ########################################
    # -----------------------------
    # CONSTRAINTS
    # -----------------------------
    ########################################

    # Demand satisfaction
    model.addConstrs(
        (quicksum(f3[d, r, mo] for d in Dcs for mo in Modes) +v[r] >= demand[r]
         for r in Retailers),
        name="Demand"
    )

    # DC balance
    model.addConstrs(
        (
            quicksum(f2[c, d, mo] for c in Crossdocks for mo in Modes)
            == quicksum(f3[d, r, mo] for r in Retailers for mo in Modes)
            for d in Dcs
        ),
        name="DCBalance"
    )


    # Crossdock balance
    model.addConstrs(
        (quicksum(f1[p, c, mo] for p in Plants for mo in ModesL1) ==
         (quicksum(f2[c, d, mo] for d in Dcs for mo in Modes) )
         for c in Crossdocks),
        name="CrossdockBalance"
    )

    #capacity link big M
    # DC capacity
    model.addConstrs(
        (quicksum(f3[d, r, mo] for r in Retailers for mo in Modes) <= dc_capacity[d]
         for d in Dcs),
        name="DCCapacity"
    )

    # C02 Enforcement

    model.addConstr(
        Total_CO2 <= CO2_base * (1 - CO_2_percentage),
        name="CO2ReductionTarget"
    )
    
    
    # -----------------------------
    # SCENARIO SETTINGS FOR SC1F
    # -----------------------------
    
    # SUEZ CANAL BLOCKADE
    if suez_canal == True:
           model.addConstrs(
        (f1[p, c, mo] == 0
         for p in Plants
         for c in Crossdocks
         for mo in Modes
         if mo == "Water"),
        name="WaterDamage_f1"
    )
           
        # Rerouting can be applied
    
    
    # A new oil crises
    if oil_crises == True:
        Total_Transport = Total_Transport*1.3
        LastMile_Cost = LastMile_Cost * 1.3
        
    

    # Volcano eruption blocks all AIR transportation


    if volcano:
        
        if "air" in Modes:
            Modes.remove("air")
        if "air" in ModesL1:
            ModesL1.remove("air")
        
    if trade_war:
            
        Sourcing_L1 = Sourcing_L1*tariff_rate

    
    
    
    M = 1e8
    
    # -----------------------------
    # OBJECTIVE
    # -----------------------------
    model.setObjective( Sourcing_L1 + Handling_L2 + Handling_L3 + LastMile_Cost + CO2_Mfg + Total_Transport+ Total_InvCost_Model + M * quicksum(v[r] for r in Retailers),
        GRB.MINIMIZE
    )


    # -----------------------------
    # SOLVE
    # -----------------------------
    model.optimize()
    
    # -----------------------------
    # OUTPUT
    # -----------------------------
    
    f1_matrix = print_flows(f1, Plants, Crossdocks, ModesL1, "f1 (Plant → Crossdock)")
    f2_matrix = print_flows(f2, Crossdocks, Dcs, Modes, "f2 (Crossdock → DC)")
    f3_matrix = print_flows(f3, Dcs, Retailers, Modes, "f3 (DC → Retailer)")

    
    if print_results == "YES":
        print("Transport L1:", sum(Transport_L1[mo].getValue() for mo in ModesL1))
        print("Transport L2:", sum(Transport_L2[mo].getValue() for mo in Modes))
        print("Transport L3:", sum(Transport_L3[mo].getValue() for mo in Modes))

        print("Inventory L1:", Total_InvCost_L1.getValue())
        print("Inventory L2:", Total_InvCost_L2.getValue())
        print("Inventory L3:", Total_InvCost_L3.getValue())
        
        print("Fixed Last Mile:", LastMile_Cost.getValue())
        
        print("CO2 Manufacturing at State 1:", CO2_Mfg.getValue())
        
        print(f"Sourcing_L1: {Sourcing_L1.getValue():,.2f}")
        print(f"Handling_L2_existing: {Handling_L2_existing.getValue():,.2f}")
        print(f"Handling_L2 (total): {Handling_L2.getValue():,.2f}")
        print(f"Handling_L3: {Handling_L3.getValue():,.2f}")
        

        print("CO2 total:", Total_CO2.getValue())

        print("Total objective:", model.ObjVal)   
        
    E_air         = (CO2_tr_L1_air + CO2_tr_L2_air + CO2_tr_L3_air).getValue()
    E_Water         = (CO2_tr_L1_Water + CO2_tr_L2_Water + CO2_tr_L3_Water).getValue()
    E_road        = (CO2_tr_L2_road + CO2_tr_L3_road).getValue()   # no road on L1
    E_lastmile    = LastMile_CO2.getValue()
    E_production  = CO2_prod_L1.getValue()
        
    
    U = sum(v[r].X for r in Retailers)         # unmet demand
    D_tot = sum(demand[r] for r in Retailers)  # total original demand

    satisfied_units = D_tot - U
    satisfied_pct   = satisfied_units / D_tot
    
    results = {
    # --- Transport Costs ---
    "Transport_L1": sum(Transport_L1[mo].getValue() for mo in ModesL1),
    "Transport_L2": sum(Transport_L2[mo].getValue() for mo in Modes),
    "Transport_L3": sum(Transport_L3[mo].getValue() for mo in Modes),

    # --- Inventory Costs ---
    "Inventory_L1": Total_InvCost_L1.getValue(),
    "Inventory_L2": Total_InvCost_L2.getValue(),
    "Inventory_L3": Total_InvCost_L3.getValue(),

    # --- Last Mile & CO2 ---
    "Fixed_Last_Mile": LastMile_Cost.getValue(),
    "CO2_Manufacturing_State1": CO2_Mfg.getValue(),
    "CO2_Total": Total_CO2.getValue(),

    # --- Sourcing & Handling ---
    "Sourcing_L1": Sourcing_L1.getValue(),
    "Handling_L2_existing": Handling_L2_existing.getValue(),
    "Handling_L2_total": Handling_L2.getValue(),
    "Handling_L3": Handling_L3.getValue(),
    
    # --- Emission Calculations ---
    "E_air": E_air,
    "E_Water": E_Water,
    "E_road": E_road,
    "E_lastmile": E_lastmile,
    "E_production": E_production,

    
    
    # --- Objective ---
    "Objective_value": model.ObjVal - M * U,
    "Satisfied_Demand_pct":   satisfied_pct,
    "Satisfied_Demand_units": satisfied_units
    }

    return results, model


def extract_var_values(model):

    var_data = []
    for v in model.getVars():
        var_data.append({
            "VarName": v.VarName,
            "Value": v.X
        })
    return pd.DataFrame(var_data)

def simulate_scenarios_full():
    # --- Demand scaling levels ---
    demand_levels = [1.00, 0.95, 0.90, 0.85, 0.80, 0.75]

    # --- Base demand (for scaling) ---
    base_demand = {
        "Cologne": 17000, "Antwerp": 9000, "Krakow": 13000,
        "Kaunas": 19000, "Oslo": 15000, "Dublin": 20000, "Stockholm": 18000
    }

    # Prepare Excel writer for multiple sheets
    writer = pd.ExcelWriter("simulation_results_demand_levels.xlsx", engine="openpyxl")

    for level in demand_levels:
        print(f"\n🚀 Running scenarios for {int(level*100)}% demand...\n")

        scaled_demand = {k: v * level for k, v in base_demand.items()}
        results_summary = []
        json_dict = {}

        co2_values = [1 * i / 100 for i in range(0, 100)]
        product_weights = [2.58]
        CO_2_CostsAtMfg = [37.50]
        unit_penaltycost = [1.7]
        
        scenario_counter = 0

        for co2_pct in co2_values:
            for w in product_weights:
                for co2_cost in CO_2_CostsAtMfg:
                    for penaltycost in unit_penaltycost:
                        start = time.time()

                        try:
                            results, model = run_scenario(
                                demand=scaled_demand,
                                CO_2_percentage=co2_pct,
                                product_weight=w,
                                co2_cost_per_ton=co2_cost,
                                unit_penaltycost=penaltycost,
                                print_results="NO"
                            )

                            # Check feasibility before using results
                            if model.Status != GRB.OPTIMAL:
                                print(f"⚠️ Infeasible or non-optimal solution at {int(level*100)}% demand, CO2={co2_pct:.2f}")
                                continue

                        except Exception as e:
                            print(f"❌ Error at {int(level*100)}% demand, CO2={co2_pct:.2f}: {e}")
                            continue

                        runtime = time.time() - start
                        scenario_counter += 1

                        flat_vars = {v.VarName: v.X for v in model.getVars()}

                        run_record = {
                            "Scenario_ID": scenario_counter,
                            "CO2_percentage": co2_pct,
                            "Product_weight": w,
                            "CO2_CostAtMfg": co2_cost,
                            "Unit_penaltycost": penaltycost,
                            "Runtime_sec": round(runtime, 2),
                            "Demand_Level": level,
                            **results,
                            **flat_vars
                        }

                        results_summary.append(run_record)
                        key = (round(co2_pct, 3), round(w, 3), round(co2_cost, 3), round(penaltycost, 3), round(level, 3))
                        json_dict[str(key)] = run_record

                        print(f"✅ Done: Demand={int(level*100)}%, CO2={co2_pct:.2f}, Obj={results.get('Objective_value', 0):.2f}")

        if not results_summary:
            print(f"⚠️ No feasible results found for {int(level*100)}% demand. Skipping sheet.")
            continue

        # --- Convert to DataFrame for Excel ---
        df_summary = pd.DataFrame(results_summary)

        # --- Save one sheet per demand level ---
        sheet_name = f"Demand_{int(level*100)}%"
        df_summary.to_excel(writer, sheet_name=sheet_name, index=False)

        # --- Array-style simplified summary ---
        # --- Reformatted array-style summary (new format) ---
        # --- Reformatted array-style summary (NEW, using emission components) ---
        formatted_summary = []
        for record in results_summary:
            formatted_row = [
                record.get("CO2_percentage", 0),                 # CO2 Reduction %
                record.get("CO2_Total", 0),                      # Total Emissions (tons)
                record.get("E_air", 0),                          # E(Air)
                record.get("E_Water", 0),                          # E(Water)
                record.get("E_road", 0),                         # E(Road)
                record.get("E_lastmile", 0),                     # E(Last-mile)
                record.get("E_production", 0),                   # E(Production)
                record.get("Objective_value", 0),                # Total Cost
                record.get("Transport_L1", 0)
                + record.get("Transport_L2", 0)
                + record.get("Transport_L3", 0),                 # Transportation Cost
                record.get("Sourcing_L1", 0)
                + record.get("Handling_L2_total", 0)
                + record.get("Handling_L3", 0),                  # Sourcing/Handling Cost
                record.get("CO2_Manufacturing_State1", 0),       # CO2 Cost in Production (€, not tons)
                record.get("Inventory_L1", 0)
                + record.get("Inventory_L2", 0)
                + record.get("Inventory_L3", 0),                 # Transit Inventory Cost
                record.get("f1[Taiwan,Vienna,air]", 0)
                + record.get("f1[Taiwan,Gdansk,air]", 0)
                + record.get("f1[Taiwan,Paris,air]", 0)
                +record.get("f1[Taiwan,Vienna,Water]", 0)
                + record.get("f1[Taiwan,Gdansk,Water]", 0)
                + record.get("f1[Taiwan,Paris,Water]", 0),             # Taiwan Outbound
                record.get("f1[Shanghai,Vienna,air]", 0)
                + record.get("f1[Shanghai,Gdansk,air]", 0)
                + record.get("f1[Shanghai,Paris,air]", 0)
                +record.get("f1[Shanghai,Vienna,Water]", 0)
                + record.get("f1[Shanghai,Gdansk,Water]", 0)
                + record.get("f1[Shanghai,Paris,Water]", 0),            # SHA Outbound
                
                sum(v for k, v in record.items() if "f1" in k and "air"  in k),  # Layer1Air (units)
                sum(v for k, v in record.items() if "f1" in k and "Water"  in k),  # Layer1Water
                sum(v for k, v in record.items() if "f2" in k and "air"  in k),  # Layer2Air
                sum(v for k, v in record.items() if "f2" in k and "Water"  in k),  # Layer2Water
                sum(v for k, v in record.items() if "f2" in k and "road" in k),  # Layer2Road
                sum(v for k, v in record.items() if "f3" in k and "air"  in k),  # Layer3Air
                sum(v for k, v in record.items() if "f3" in k and "Water"  in k),  # Layer3Water
                sum(v for k, v in record.items() if "f3" in k and "road" in k),  # Layer3Road
                sum(v for k, v in record.items() if "f3" in k)                   # DemandFulfillment
            ]
            formatted_summary.append(formatted_row)

        headers = [
            "CO2 Reduction %", "Total Emissions", "E(Air)", "E(Water)", "E(Road)",
            "E(Last-mile)", "E(Production)", "Total Cost", "Transportation Cost",
            "Sourcing/Handling Cost", "CO2 Cost in Production",
            "Transit Inventory Cost", "TW Outbound", "SHA Outbound",
            "Layer1Air", "Layer1Water", "Layer2Air", "Layer2Water", "Layer2Road",
            "Layer3Air", "Layer3Water", "Layer3Road", "DemandFulfillment"
        ]

        df_array = pd.DataFrame(formatted_summary, columns=headers)
        df_array.to_excel(writer, sheet_name=f"Array_{int(level*100)}%", index=False)

        print(f"✅ Sheets added: '{sheet_name}' and 'Array_{int(level*100)}%'")

    writer.close()
    print("\n🎯 All demand-level simulations completed!")

if __name__ == "__main__":
    simulate_scenarios_full()
