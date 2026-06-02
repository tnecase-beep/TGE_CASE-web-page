import pandas as pd
from gurobipy import quicksum

def print_flows(f_dict, from_nodes, to_nodes, modes, name):
    """
    Prints aggregated flows (sum across modes) as a matrix DataFrame.
    Also prints per-mode breakdown if needed.
    """
    print(f"\n=== {name}: Total flow (summed over modes) ===")
    df_total = pd.DataFrame(0.0, index=from_nodes, columns=to_nodes)

    for i in from_nodes:
        for j in to_nodes:
            df_total.loc[i, j] = sum(f_dict[i, j, m].X for m in modes)

    print(df_total.round(2))
    return df_total


# ---- 1️⃣ f1: Plant → Crossdock ----
#
# ---- 2️⃣ f2: Crossdock → DC ----
#
# ---- 3️⃣ f3: DC → Retailer ----
#
# Optional: If you also want to see which mode each leg used (non-zero flows)
def print_mode_breakdown(f_dict, from_nodes, to_nodes, modes, name):
    print(f"\n=== {name}: Mode breakdown (nonzero flows) ===")
    for i in from_nodes:
        for j in to_nodes:
            for m in modes:
                val = f_dict[i, j, m].X
                if abs(val) > 1e-6:
                    print(f"{name}: {i} → {j} via {m} = {val:.2f}")

# Uncomment if you want detailed mode info:
#print_mode_breakdown(f1, Plants, Crossdocks, Modes, "f1")
#print_mode_breakdown(f2, Crossdocks, Dcs, Modes, "f2")
#print_mode_breakdown(f3, Dcs, Retailers, Modes, "f3")

def compute_transport_cost(model, f_vars, dist_df, tau_table, product_weight, layer_name, 
                           Origins, Destinations, Modes):
    """
    Returns a dictionary of transportation cost expressions by mode 
    and the total cost expression for the given layer.

    Parameters
    ----------
    model : gurobipy.Model
        The Gurobi model instance.
    f_vars : dict
        Flow variables indexed as f_vars[o, d, mo].
    dist_df : pandas.DataFrame
        Distance matrix with dist_df.loc[o, d] = km distance.
    tau_table : pandas.DataFrame
        Table including τ (€/kg·km) column with index = transportation modes.
    product_weight : float
        Product weight in kg.
    layer_name : str
        Label for the layer (e.g., "L1", "L2", "L3").
    Origins : list
        Origin set (e.g., Plants).
    Destinations : list
        Destination set (e.g., Crossdocks).
    Modes : list
        Transportation modes (e.g., ["air","sea","road"]).

    Returns
    -------
    (dict, gurobipy.LinExpr)
        Dictionary of costs by mode and total cost expression.
    """

    tau = tau_table["τ (€/kg·km)"].to_dict()
    Transport_L = {}

    for mo in Modes:
        Transport_L[mo] = quicksum(
            tau[mo] * dist_df.loc[o, d] * product_weight * f_vars[o, d, mo]
            for o in Origins for d in Destinations
        )

    Total_Transport_L = quicksum(Transport_L[mo] for mo in Modes)
    model.update()  # ensure variables are recognized by Gurobi

    print(f"{layer_name} transport cost expressions added.")
    return Transport_L, Total_Transport_L


def compute_inventory_cost(model, f_vars, table_df, Origins, Destinations, Modes, layer_name):
    """
    Computes inventory cost for a given layer and each transport mode:
    SUM(f[i,j,mo] * (SS + h*LT))
    """

    # Extract values from table
    SS = table_df["SS (€/unit)"].to_dict()
    h  = table_df["h (€/unit)"].to_dict()
    LT = table_df["LT (days)"].to_dict()

    # Inventory cost per mode
    InvCost = {}
    for mo in Modes:
        InvCost[mo] = quicksum(
            f_vars[i, j, mo] * (SS[mo] + h[mo] * LT[mo])
            for i in Origins for j in Destinations
        )

    # Total inventory cost for this layer
    Total_InvCost = quicksum(InvCost[mo] for mo in Modes)
    model.update()

    print(f"{layer_name} inventory cost expressions added.")
    return InvCost, Total_InvCost

