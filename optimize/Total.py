# -*- coding: utf-8 -*-
"""
Created on Fri Nov 28 15:50:25 2025

@author: LENOVO
"""

# ================================================================
#  merged_app.py (FINAL)
# ================================================================

import os
import re
import streamlit as st
import sys as _sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(APP_DIR)

# Error reporting – initialise singleton early so st.error is patched
# before any rendering begins. Safe to import even without credentials.
try:
    if ROOT_DIR not in _sys.path:
        _sys.path.append(ROOT_DIR)
    from error_reporting import get_reporter as _get_reporter
    _get_reporter()
except Exception:
    pass

if APP_DIR in _sys.path:
    _sys.path.remove(APP_DIR)
_sys.path.insert(0, APP_DIR)

import pandas as pd
import plotly.express as px
import streamlit.components.v1 as components
import gurobipy as gp
import inspect
import numpy as np
from statistics import NormalDist as _ND; _nd = _ND(); norm = type('norm', (), {'pdf': staticmethod(_nd.pdf), 'ppf': staticmethod(_nd.inv_cdf), 'cdf': staticmethod(_nd.cdf)})()
from datetime import datetime, timezone

# Puzzle submissions -> SharePoint Excel (implemented in post_data.py)
# If post_data.py is missing or not configured, Puzzle Mode still works; only "Submit" will be disabled.
try:
    from post_data import push_puzzle_submission
except Exception:
    push_puzzle_submission = None

# Gamification mode extracted into a separate module (toggleable)
from gamification import render_gamification_mode

from sc1_app import run_sc1
from sc2_app import run_sc2
from Scenario_Setting_For_SC1F import run_scenario as run_SC1F
from Scenario_Setting_For_SC2F import run_scenario as run_SC2F
# MASTER model import (supports mode-share enforcement & parametric versions)

from MASTER import run_scenario_master
from collections import defaultdict


# Toggle Gamification Mode on/off via env var:
#   ENABLE_GAMIFICATION=1 (default) -> shows Gamification Mode
#   ENABLE_GAMIFICATION=0          -> hides Gamification Mode
ENABLE_GAMIFICATION = False

# Code-only toggle for Puzzle Mode scenario events UI.
# False -> hide the entire Scenario events section from the UI and use defaults below.
# True  -> show the Scenario events controls in Puzzle Mode.
SHOW_PUZZLE_SCENARIO_EVENTS_UI = False

# Code-only defaults used whenever the Puzzle Mode Scenario events UI is hidden.
PUZZLE_SCENARIO_EVENT_DEFAULTS = {
    "suez_canal": False,
    "oil_crises": False,
    "volcano": False,
    "trade_war": False,
    "tariff_rate": 1.0,
}

# ================================================================
# PAGE CONFIG (only once!)
# ================================================================
st.set_page_config(
    page_title="Supply Chain Suite",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ================================================================
# SIDEBAR LOGO (add above navigation)
# ================================================================
BASE_DIR = os.path.dirname(__file__)
LOGO_PATH = os.path.join(BASE_DIR, "assets", "logo.png")

if os.path.exists(LOGO_PATH):
    st.sidebar.image(LOGO_PATH, use_container_width=True)
    st.sidebar.markdown("---")  # small separator so menu stays clean
else:
    st.sidebar.warning("Logo not found: assets/logo.png")

# ================================================================
# SIDEBAR NAVIGATION WITH COLLAPSIBLE GROUPS
# ================================================================
st.sidebar.title("📌 Navigation")

# Make the two navigation groups mutually exclusive.
# Otherwise, once a Dashboards page is selected, routing always stops there
# and the user cannot navigate to the Optimization dashboard.
def _on_factory_change():
    st.session_state["optimization_radio"] = None

def _on_optimization_change():
    st.session_state["factory_radio"] = None

# Collapsible "Puzzle" group
optimization_nav_options = ["Puzzle Mode"]
if ENABLE_GAMIFICATION:
    optimization_nav_options.append("Gamification Mode")

with st.sidebar.expander("🧩 Puzzle", expanded=True):
    opt_choice = st.radio(
        "Select Mode:",
        optimization_nav_options,
        index=None,
        key="optimization_radio",
        on_change=_on_optimization_change,
    )

# Collapsible "Dashboards" group
with st.sidebar.expander("🏭 Dashboards", expanded=True):
    factory_choice = st.radio(
        "Select Scenario:",
        [
            "Scenario 1: Process Optimization",
            "Scenario 2: Supply Chain Transformation"
        ],
        index=None,
        key="factory_radio",
        on_change=_on_factory_change,
    )

# ================================================================
# ROUTING LOGIC
# ================================================================
if factory_choice == "Scenario 1: Process Optimization":
    run_sc1()
    st.stop()

elif factory_choice == "Scenario 2: Supply Chain Transformation":
    run_sc2()
    st.stop()

elif opt_choice in optimization_nav_options:
    pass  # Continue into optimization block below

else:
    st.title("Supply Chain Suite")
    st.markdown(
        """
        **Case synopsis :** We study a global supply chain with four layers:  
        **Manufacturers (Taiwan & Shanghai) → Cross-docks ( or European Manufacturers) → Distribution Centers → Retailer Hubs → Local Customers**.

        **Get started:** use the **left Navigation** to open a page.
        - **Puzzle Mode:** configure the network manually.
        - **Dashboards:** inspect the network structure and facilities. -->Dashboards: explore the optimal network structure through different scenarios.
            - **Scenario 1:** Process Optimization within the current network by adjusting the emission reduction target.
            - **Scenario 2:** Supply Chain Transformation with structural changes via alternative EU production. Evaluate the impact of carbon pricing and sourcing cost changes.

        """
    )
    st.stop()

# ================================================================
# OPTIMIZATION DASHBOARD
# ================================================================

# ------------------------------------------------------------
# Header row: title (left) + compact world map with all potential nodes (right)
# (Shown immediately — does NOT require running an optimization.)
hdr_left, hdr_right = st.columns([2.7, 1.3])

with hdr_left:
    st.title("🌍 Global Supply Chain Optimization ")

with hdr_right:
    # Small static map with ALL potential nodes (plants, cross-docks, DCs, retailers, and EU facilities)
    _all_nodes = [
        ("Plant", 31.230416, 121.473701, "Shanghai"),
        ("Plant", 23.553100, 121.021100, "Taiwan"),

        ("Cross-dock", 48.856610, 2.352220, "Paris"),
        ("Cross-dock", 54.352100, 18.646400, "Gdansk"),
        ("Cross-dock", 48.208500, 16.372100, "Vienna"),

        ("DC", 50.040750, 15.776590, "Pardubice"),
        ("DC", 50.954468, 1.862801, "Calais"),
        ("DC", 56.946285, 24.105078, "Riga"),
        ("DC", 36.168056, -5.348611, "Algeciras"),

        ("Retail", 50.935173, 6.953101, "Cologne"),
        ("Retail", 51.219890, 4.403460, "Antwerp"),
        ("Retail", 50.061430, 19.936580, "Krakow"),
        ("Retail", 54.902720, 23.909610, "Kaunas"),
        ("Retail", 59.911491, 10.757933, "Oslo"),
        ("Retail", 53.350140, -6.266155, "Dublin"),
        ("Retail", 59.329440, 18.068610, "Stockholm"),

        ("EU Facility", 47.497913, 19.040236, "Budapest"),
        ("EU Facility", 50.088040, 14.420760, "Prague"),
        ("EU Facility", 51.898514, -8.475604, "Cork"),
        ("EU Facility", 60.169520, 24.935450, "Helsinki"),
        ("EU Facility", 52.229770, 21.011780, "Warsaw"),
    ]

    _df_all = pd.DataFrame(_all_nodes, columns=["Type", "Lat", "Lon", "City"])

    _color_map_small = {
        "Plant": "purple",
        "Cross-dock": "dodgerblue",
        "DC": "black",
        "Retail": "red",
        "EU Facility": "deepskyblue",
    }

    _fig_small = px.scatter_geo(
        _df_all,
        lat="Lat",
        lon="Lon",
        color="Type",
        hover_name="City",
        color_discrete_map=_color_map_small,
        projection="natural earth",
        scope="world",
    )

    # Make it compact and clean (no legend, no toolbar)
    _fig_small.update_traces(marker=dict(size=6, opacity=0.9, line=dict(width=0.4, color="white")))
    _fig_small.update_geos(
        showcountries=False,
        showland=True,
        landcolor="rgb(245,245,245)",
        showocean=True,
        oceancolor="rgb(230,240,255)",
        fitbounds="locations",
    )
    _fig_small.update_layout(
        height=220,
        margin=dict(l=0, r=0, t=0, b=0),
        showlegend=False,
    )

    st.plotly_chart(_fig_small, use_container_width=True, config={"displayModeBar": False})

# ------------------------------------------------------------
# Google Analytics Injection (safe)
# ------------------------------------------------------------
GA_MEASUREMENT_ID = "G-78BY82MRZ3"

components.html(f"""
<script>
(function() {{
    const targetDoc = window.parent.document;

    const old1 = targetDoc.getElementById("ga-tag");
    const old2 = targetDoc.getElementById("ga-src");
    if (old1) old1.remove();
    if (old2) old2.remove();

    const s1 = targetDoc.createElement('script');
    s1.id = "ga-src";
    s1.async = true;
    s1.src = "https://www.googletagmanager.com/gtag/js?id={GA_MEASUREMENT_ID}";
    targetDoc.head.appendChild(s1);

    const s2 = targetDoc.createElement('script');
    s2.id = "ga-tag";
    s2.innerHTML = `
        window.dataLayer = window.dataLayer || [];
        function gtag() {{ dataLayer.push(arguments); }}
        gtag('js', new Date());
        gtag('config', '{GA_MEASUREMENT_ID}', {{
            send_page_view: true
        }});
    `;
    targetDoc.head.appendChild(s2);

    console.log("GA injected successfully");
}})();
</script>
""", height=0)

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def positive_input(label, default):
    """Clean numeric input helper."""
    val_str = st.text_input(label, value=str(default))
    try:
        val = float(val_str)
        return max(val, 0)
    except:
        st.warning(f"{label} must be numeric. Using {default}.")
        return default


def run_filtered(func, kwargs: dict):
    """Call a scenario function with only the kwargs it supports (signature-safe)."""
    sig = inspect.signature(func)
    allowed = set(sig.parameters.keys())
    filtered = {k: v for k, v in kwargs.items() if k in allowed}
    return func(**filtered)


def run_master_filtered(master_kwargs: dict):
    """Backward-compatible alias for MASTER."""
    return run_filtered(run_scenario_master, master_kwargs)

    
# ------------------------------------------------------------
# Helpers (NEW): compute node activity from flows
# ------------------------------------------------------------
EPS = 1e-6

# IMPORTANT: Map displayed City labels -> model facility keys used in variable names
# Adjust these to match YOUR model naming.
CITY_TO_KEYS = {
    # Plants (model keys)
    "Shanghai": ["Shanghai"],
    "Taiwan": ["Taiwan"],  

    # Cross-docks 
    "Paris": ["Paris"],
    "Gdansk": ["Gdansk"],
    "Vienna": ["Vienna"],

    # DCs 
    "Pardubice": ["Pardubice"],
    "Calais": ["Calais"],
    "Riga": ["Riga"],
    "Algeciras": ["Algeciras"],

    # Retailers 
    "Cologne": ["Cologne"],
    "Antwerp": ["Antwerp"],
    "Krakow": ["Krakow"],
    "Kaunas": ["Kaunas"],
    "Oslo": ["Oslo"],
    "Dublin": ["Dublin"],
    "Stockholm": ["Stockholm"],
}

def _parse_inside_brackets(varname: str):
    # "f2[ATVIE,GMZ,air]" -> ["ATVIE","GMZ","air"]
    i = varname.find("[")
    j = varname.rfind("]")
    if i == -1 or j == -1 or j <= i:
        return None
    inside = varname[i+1:j]
    return [x.strip() for x in inside.split(",")]

def compute_key_throughput(model) -> dict:
    """
    Returns dict: facility_key -> total flow touching the node (in+out aggregated)
    Based on f1, f2, f2_2, f3 variable values.
    """
    thr = defaultdict(float)
    for v in model.getVars():
        n = v.VarName

        if n.startswith("f1[") or n.startswith("f2[") or n.startswith("f2_2[") or n.startswith("f3["):
            parts = _parse_inside_brackets(n)
            if not parts or len(parts) < 2:
                continue

            o, d = parts[0], parts[1]
            try:
                x = float(v.X)
            except Exception:
                x = 0.0

            if x > EPS:
                thr[o] += x
                thr[d] += x

    return thr

def city_is_active(city: str, key_thr: dict) -> bool:
    keys = CITY_TO_KEYS.get(city, [])
    return sum(key_thr.get(k, 0.0) for k in keys) > EPS


# ------------------------------------------------------------
# Helpers (NEW): transport flow totals by mode + cost/emission charts
# ------------------------------------------------------------

def _safe_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return float(default)


# Optimization models (SC1F/SC2F/...) encode the maritime mode as "sea" in their
# variable names (e.g. f1[Taiwan,Vienna,sea]), while the UI/results use "Water".
# Map raw model tokens -> canonical display keys so flows aren't silently dropped.
_MODEL_MODE_ALIASES = {"air": "air", "sea": "Water", "water": "Water", "road": "road"}


def sum_flows_by_mode_model(model, prefix: str):
    """Sum air/Water/road units for a given flow prefix like 'f1', 'f2', 'f2_2', or 'f3' from model."""
    totals = {"air": 0.0, "Water": 0.0, "road": 0.0}
    if model is None:
        return totals

    for v in model.getVars():
        n = getattr(v, "VarName", "")
        if not n.startswith(prefix + "["):
            continue
        parts = _parse_inside_brackets(n)
        if not parts or len(parts) < 3:
            continue
        mode = _MODEL_MODE_ALIASES.get(str(parts[-1]).strip().lower())
        if mode in totals:
            totals[mode] += _safe_float(getattr(v, "X", 0.0))

    return totals


def display_layer_summary_model(model, title: str, prefix: str, include_road: bool = True):
    totals = sum_flows_by_mode_model(model, prefix)
    st.markdown(f"### {title}")
    cols = st.columns(3 if include_road else 2)
    cols[0].metric("🚢 Water", f"{totals['Water']:,.0f} units")
    cols[1].metric("✈️ Air", f"{totals['air']:,.0f} units")
    if include_road:
        cols[2].metric("🚛 Road", f"{totals['road']:,.0f} units")

    if sum(totals.values()) <= EPS:
        st.info("No transport activity recorded for this layer.")
    st.markdown("---")


def render_transport_flows_by_mode(model):
    st.markdown("## 🚚 Transport Flows by Mode")
    display_layer_summary_model(model, "Plants → Cross-docks", "f1", include_road=False)
    display_layer_summary_model(model, "Cross-docks → DCs", "f2", include_road=True)
    display_layer_summary_model(model, "Alternative Production Facilities → DCs", "f2_2", include_road=True)
    display_layer_summary_model(model, "DCs → Retailer Hubs", "f3", include_road=True)


def render_cost_emission_distribution(results: dict):
    """Replicates the Scenario 1/Scenario 2-style Cost & Emission Distribution charts for optimization outputs."""
    st.markdown("## 💰 Cost and 🌿 Emission Distribution")

    col1, col2 = st.columns(2)

    # --- Cost Distribution ---
    with col1:
        st.subheader("Cost Distribution")

        transport_cost = (
            _safe_float(results.get("Transport_L1", 0))
            + _safe_float(results.get("Transport_L2", 0))
            + _safe_float(results.get("Transport_L2_new", results.get("Transport_L2_new", 0)))
            + _safe_float(results.get("Transport_L3", 0))
            # Last-mile (6.25 €/unit): SC1F/SC2F report it as "Fixed_Last_Mile",
            # puzzle mode as "LastMile_Cost". sc1/sc2 apps include it in transport too.
            + _safe_float(results.get("Fixed_Last_Mile", results.get("LastMile_Cost", 0)))
        )
        if transport_cost <= 0 and "Transportation Cost" in results:
            transport_cost = _safe_float(results.get("Transportation Cost", 0))

        sourcing_handling_cost = (
            _safe_float(results.get("Sourcing_L1", 0))
            + _safe_float(results.get("Handling_L2_total", 0))
            + _safe_float(results.get("Handling_L3", 0))
        )
        if sourcing_handling_cost <= 0 and "Sourcing/Handling Cost" in results:
            sourcing_handling_cost = _safe_float(results.get("Sourcing/Handling Cost", 0))

        co2_cost_production = (
            _safe_float(results.get("CO2_Manufacturing_State1", 0))
            + _safe_float(results.get("CO2_Cost_L2_2", 0))
        )
        if co2_cost_production <= 0:
            co2_cost_production = _safe_float(results.get("CO2 Cost in Production", results.get("CO2_Cost_in_Production", 0)))

        inventory_cost = (
            _safe_float(results.get("Inventory_L1", 0))
            + _safe_float(results.get("Inventory_L2", 0))
            + _safe_float(results.get("Inventory_L2_new", 0))
            + _safe_float(results.get("Inventory_L3", 0))
        )
        if inventory_cost <= 0 and "Transit Inventory Cost" in results:
            inventory_cost = _safe_float(results.get("Transit Inventory Cost", 0))

        cost_parts = {
            "Transportation Cost": transport_cost,
            "Sourcing/Handling Cost": sourcing_handling_cost,
            "CO₂e Cost in Production": co2_cost_production,
            "Inventory Cost": inventory_cost,
        }

        df_cost_dist = pd.DataFrame({
            "Category": list(cost_parts.keys()),
            "Value": list(cost_parts.values()),
        })
        df_cost_dist["Value_MEUR"] = pd.to_numeric(df_cost_dist["Value"], errors="coerce") / 1_000_000.0

        fig_cost = px.bar(
            df_cost_dist,
            x="Category",
            y="Value_MEUR",
            text="Value_MEUR",
            color="Category",
            color_discrete_sequence=["#A7C7E7", "#B0B0B0", "#F8C471", "#5D6D7E"],
        )

        fig_cost.update_traces(
            texttemplate="%{text:.2f} M€",
            textposition="outside",
        )
        fig_cost.update_layout(
            template="plotly_white",
            showlegend=False,
            xaxis_tickangle=-35,
            yaxis_title="Million €",
            height=400,
            yaxis_tickformat=".2f",
        )

        st.plotly_chart(fig_cost, use_container_width=True)

    # --- Emission Distribution ---
    with col2:
        st.subheader("Emission Distribution")

        e_air = _safe_float(results.get("E_air", results.get("E_Air", 0)))
        # Optimization models report the maritime emission under "E_sea"; puzzle uses "E_Water".
        e_Water = _safe_float(results.get("E_Water", results.get("E_sea", 0)))
        e_road = _safe_float(results.get("E_road", results.get("E_Road", 0)))
        e_last = _safe_float(results.get("E_lastmile", results.get("E_Last-mile", results.get("E_last_mile", 0))))
        e_total = _safe_float(results.get("CO2_Total", results.get("Total Emissions", 0)))

        e_prod = _safe_float(results.get("E_production", results.get("E_Production", 0)))
        if e_prod <= 0 and e_total > 0:
            e_prod = max(e_total - e_air - e_Water - e_road - e_last, 0.0)

        total_transport = e_air + e_Water + e_road

        emission_data = {
            "Production": e_prod,
            "Last-mile": e_last,
            "Air": e_air,
            "Water": e_Water,
            "Road": e_road,
            "Total Transport": total_transport,
        }

        df_emission = pd.DataFrame({
            "Source": list(emission_data.keys()),
            "Emission (tons)": list(emission_data.values()),
        })

        fig_emission = px.bar(
            df_emission,
            x="Source",
            y="Emission (tons)",
            text="Emission (tons)",
            color="Source",
            color_discrete_sequence=["#4B8A08", "#2E8B57", "#808080", "#FFD700", "#90EE90", "#000000"],
        )

        fig_emission.update_traces(
            texttemplate="%{text:,.2f}",
            textposition="outside",
            marker_line_color="black",
            marker_line_width=0.5,
        )

        fig_emission.update_layout(
            template="plotly_white",
            showlegend=False,
            xaxis_tickangle=-35,
            yaxis_title="Tons of CO₂e",
            height=400,
            yaxis_tickformat=",",
        )

        st.plotly_chart(fig_emission, use_container_width=True)


# ------------------------------------------------------------
# Puzzle Mode (NEW): no optimization, user builds a network and we compute cost/CO2 implications
# ------------------------------------------------------------

def _puzzle_defaults():
    """Defaults aligned with MASTER.py (kept local to avoid running optimization)."""
    demand = {
        "Cologne": 17000,
        "Antwerp": 9000,
        "Krakow": 13000,
        "Kaunas": 19000,
        "Oslo": 15000,
        "Dublin": 20000,
        "Stockholm": 18000,
    }

    plants_all = ["Taiwan", "Shanghai"]
    crossdocks_all = ["Vienna", "Gdansk", "Paris"]
    dcs_all = ["Pardubice", "Calais", "Riga", "Algeciras"]
    new_locs_all = ["Budapest", "Prague", "Cork", "Helsinki", "Warsaw"]

    dc_capacity = {"Pardubice": 45000, "Calais": 150000, "Riga": 75000, "Algeciras": 100000}
    handling_dc = {"Pardubice": 4.768269231, "Calais": 5.675923077,
                   "Riga": 4.426038462, "Algeciras": 7.0865}
    handling_crossdock = {"Vienna": 6.533884615, "Gdansk": 4.302269231, "Paris": 5.675923077}

    sourcing_cost = {"Taiwan": 3.343692308, "Shanghai": 3.423384615}
    co2_prod_kg_per_unit = {"Taiwan": 6.3, "Shanghai": 9.8}

    new_loc_capacity = {"Budapest": 37000, "Prague": 35500, "Cork": 46000,
                        "Helsinki": 35000, "Warsaw": 26500}
    new_loc_openingCost = {"Budapest": 2.775e6, "Prague": 2.6625e6, "Cork": 3.45e6,
                           "Helsinki": 2.625e6, "Warsaw": 1.9875e6}
    new_loc_operationCost = {"Budapest": 250000, "Prague": 305000, "Cork": 450000,
                             "Helsinki": 420000, "Warsaw": 412500}
    new_loc_CO2 = {"Budapest": 3.2, "Prague": 2.8, "Cork": 4.6, "Helsinki": 5.8, "Warsaw": 6.2}

    # Transport emission factor (ton CO2 per ton-km)
    co2_emission_factor = {"air": 0.000971, "Water": 0.000027, "road": 0.000076}

    # Per-mode transport cost (€/kg-km)
    tau = {"air": 0.0105, "Water": 0.0013, "road": 0.0054}
    unit_inventory_holdingCost = 0.85
    unit_penaltycost = 1.7

    # Distances (km) — aligned with MASTER defaults
    dist1 = pd.DataFrame(
        [[8997.94617146616, 8558.96520835034, 9812.38584027454],
         [8468.71339377354, 7993.62774285959, 9240.26233801075]],
        index=["Taiwan", "Shanghai"],
        columns=["Vienna", "Gdansk", "Paris"],
    )
    dist2 = pd.DataFrame(
        [[220.423995674989, 1019.43140587827, 1098.71652257982, 1262.62587924823],
         [519.161031102087, 1154.87176862626, 440.338211856603, 1855.94939751482],
         [962.668288266132, 149.819604703365, 1675.455462176, 2091.1437090641]],
        index=["Vienna", "Gdansk", "Paris"],
        columns=["Pardubice", "Calais", "Riga", "Algeciras"],
    )
    dist2_new = pd.DataFrame(
        [[367.762425639798, 1216.10262027458, 1098.57245368619, 1120.13248546123],
         [98.034644813461, 818.765381327031, 987.72775809091, 1529.9990581232],
         [1558.60889112091, 714.077816812742, 1949.83469918776, 2854.35402610261],
         [1265.72892702748, 1758.18103997611, 367.698822815676, 2461.59771450036],
         [437.686419974076, 1271.77800922148, 554.373376462774, 1592.14058614186]],
        index=["Budapest", "Prague", "Cork", "Helsinki", "Warsaw"],
        columns=["Pardubice", "Calais", "Riga", "Algeciras"],
    )
    dist3 = pd.DataFrame(
        [[1184.65051865833, 933.730015948432, 557.144058480586, 769.757089072695, 2147.98445345001, 2315.79621115423, 1590.07662902924],
         [311.994969562194, 172.326685809878, 622.433010022067, 1497.40239816531, 1387.73696467636, 1585.6370207201, 1984.31926933368],
         [1702.34810062205, 1664.62283033352, 942.985120680279, 222.318687415142, 2939.50970842422, 3128.54724287652, 713.715034612432],
         [2452.23922908608, 2048.41487682505, 2022.91355628344, 1874.11994156457, 2774.73634842816, 2848.65086298747, 2806.05576441898]],
        index=["Pardubice", "Calais", "Riga", "Algeciras"],
        columns=list(demand.keys()),
    )

    return {
        "demand": demand,
        "plants_all": plants_all,
        "crossdocks_all": crossdocks_all,
        "dcs_all": dcs_all,
        "new_locs_all": new_locs_all,
        "dc_capacity": dc_capacity,
        "handling_dc": handling_dc,
        "handling_crossdock": handling_crossdock,
        "sourcing_cost": sourcing_cost,
        "co2_prod_kg_per_unit": co2_prod_kg_per_unit,
        "new_loc_capacity": new_loc_capacity,
        "new_loc_openingCost": new_loc_openingCost,
        "new_loc_operationCost": new_loc_operationCost,
        "new_loc_CO2": new_loc_CO2,
        "co2_emission_factor": co2_emission_factor,
        "tau": tau,
        "unit_inventory_holdingCost": unit_inventory_holdingCost,
        "unit_penaltycost": unit_penaltycost,
        "dist1": dist1,
        "dist2": dist2,
        "dist2_new": dist2_new,
        "dist3": dist3,
    }


def _normalize_shares(raw: dict) -> dict:
    """Normalize nonnegative shares. If all zeros, return equal shares."""
    vals = {k: max(float(v), 0.0) for k, v in (raw or {}).items()}
    s = sum(vals.values())
    if s <= 1e-12:
        n = max(len(vals), 1)
        return {k: 1.0 / n for k in vals}
    return {k: v / s for k, v in vals.items()}


def _lt_ss_table(service_level: float, demand: dict, unit_h: float, unit_penaltycost: float):
    """Return the fixed LT/SS table used in SC1F, preserving the existing return shape."""
    modes = ["air", "Water", "road"]

    lt = {
        "air": 0.5,
        "Water": 48.0,
        "road": 10.0,
    }
    ss = {
        "air": 2109.25627631292,
        "Water": 12055.4037653689,
        "road": 5711.89299799521,
    }

    return {"LT (days)": lt, "SS (€/unit)": ss, "h (€/unit)": {m: 0.85 for m in modes}}


def _compute_puzzle_results(cfg: dict, sel: dict, scen: dict) -> tuple[dict, dict]:
    """Return (results, flows) where flows are aggregated per layer/mode for plotting."""

    demand = cfg["demand"]
    total_demand = float(sum(demand.values()))

    plants = list(sel["plants"])
    crossdocks = list(sel["crossdocks"])
    dcs = list(sel["dcs"])
    new_locs = list(sel["new_locs"])

    # Guard only the retailer layer against divide-by-zero (every path ships to DCs).
    # Do NOT re-add deselected plants/cross-docks: a network of only new facilities -> DCs is
    # valid (new facilities ship straight to DCs), and silently restoring nodes the user turned
    # off was surprising. When there are no plants, the L1/crossdock loops simply do nothing.
    if len(dcs) == 0:
        dcs = list(cfg["dcs_all"])

    product_weight_kg = 2.58
    product_weight_ton = product_weight_kg / 1000.0
    lastmile_unit_cost = 6.25
    lastmile_CO2_kg = 2.68

    # Scenario-adjusted parameters
    tau = dict(cfg["tau"])
    sourcing_cost = dict(cfg["sourcing_cost"])

    if scen.get("oil_crises", False):
        for m in tau:
            tau[m] *= 1.3
    if scen.get("trade_war", False):
        tr = float(scen.get("tariff_rate", 1.0))
        for p in sourcing_cost:
            sourcing_cost[p] *= tr

    # Production allocation across production facilities.
    # `total_units` is the produced quantity (may fall below demand -> unmet demand).
    prod_source_units = sel.get("prod_source_units", None)
    prod_source_shares = sel.get("prod_source_shares", None)

    if isinstance(prod_source_units, dict) and len(prod_source_units) > 0:
        # Units-based Puzzle UI: absolute production per facility.
        # New facilities are capacity-capped in the UI; plants are uncapped up to demand.
        active_sources = list(plants) + list(new_locs)
        prod_by_source = {k: max(0.0, float(prod_source_units.get(k, 0.0))) for k in active_sources}
        plant_prod = {p: prod_by_source.get(p, 0.0) for p in plants}
        new_prod = {n: prod_by_source.get(n, 0.0) for n in new_locs}
        total_units = float(sum(prod_by_source.values()))

    elif isinstance(prod_source_shares, dict) and len(prod_source_shares) > 0:
        total_units = total_demand  # legacy share UI always fulfills 100%
        # Old Puzzle UI: user allocates a single share vector across ALL active production sites.
        active_sources = list(plants) + list(new_locs)
        shares = {k: float(prod_source_shares.get(k, 0.0)) for k in active_sources}
        shares = _normalize_shares(shares)

        prod_by_source = {k: total_units * shares.get(k, 0.0) for k in active_sources}
        plant_prod = {p: prod_by_source.get(p, 0.0) for p in plants}
        new_prod = {n: prod_by_source.get(n, 0.0) for n in new_locs}

    else:
        total_units = total_demand  # legacy layer-split UI always fulfills 100%
        # Backward-compatible: old UI (Layer 1 share + separate normalization per layer)
        share_L1_total = float(sel.get("share_L1_total", 1.0))
        share_L1_total = max(0.0, min(1.0, share_L1_total))
        share_L2_total = 1.0 - share_L1_total

        prod_L1_total = total_units * share_L1_total
        prod_L2_total = total_units * share_L2_total

        # Per-site shares
        plant_shares = _normalize_shares(sel.get("plant_shares", {p: 1.0 for p in plants}))
        plant_shares = {p: plant_shares.get(p, 0.0) for p in plants}
        plant_shares = _normalize_shares(plant_shares)

        new_shares = _normalize_shares(sel.get("new_shares", {n: 1.0 for n in new_locs})) if new_locs else {}
        if new_locs:
            new_shares = {n: new_shares.get(n, 0.0) for n in new_locs}
            new_shares = _normalize_shares(new_shares)

        plant_prod = {p: prod_L1_total * plant_shares[p] for p in plants}
        new_prod = {n: (prod_L2_total * new_shares[n] if n in new_shares else 0.0) for n in new_locs}
    # Mode shares (apply scenario blocks)
    l1_mode_share_by_plant = sel.get("l1_mode_share_by_plant", {})
    l2_mode_share_by_origin = sel.get("l2_mode_share_by_origin", {})
    l3_mode_share_by_dc = sel.get("l3_mode_share_by_dc", {})

    def _l1_modes(p):
        Water = float(l1_mode_share_by_plant.get(p, {}).get("Water", 0.5))
        Water = max(0.0, min(1.0, Water))
        air = 1.0 - Water
        if scen.get("suez_canal", False):
            Water = 0.0
            air = 1.0
        if scen.get("volcano", False):
            air = 0.0
            Water = 1.0
        return {"air": air, "Water": Water}

    def _l2_modes(o):
        Water = float(l2_mode_share_by_origin.get(o, {}).get("Water", 0.5))
        Water = max(0.0, min(1.0, Water))
        rem = 1.0 - Water
        air = float(l2_mode_share_by_origin.get(o, {}).get("air", min(0.5, rem)))
        air = max(0.0, min(rem, air))
        road = max(0.0, 1.0 - Water - air)
        if scen.get("volcano", False):
            # remove air; re-normalize Water/road
            air = 0.0
            s2 = Water + road
            if s2 <= 1e-12:
                Water, road = 1.0, 0.0
            else:
                Water, road = Water / s2, road / s2
        return {"air": air, "Water": Water, "road": road}

    def _l3_modes(d):
        Water = float(l3_mode_share_by_dc.get(d, {}).get("Water", 0.5))
        Water = max(0.0, min(1.0, Water))
        rem = 1.0 - Water
        air = float(l3_mode_share_by_dc.get(d, {}).get("air", min(0.25, rem)))
        air = max(0.0, min(rem, air))
        road = max(0.0, 1.0 - Water - air)
        if scen.get("volcano", False):
            air = 0.0
            s2 = Water + road
            if s2 <= 1e-12:
                Water, road = 1.0, 0.0
            else:
                Water, road = Water / s2, road / s2
        return {"air": air, "Water": Water, "road": road}

    # Distances restricted to active nodes
    dist1 = cfg["dist1"].reindex(index=plants, columns=crossdocks)
    dist2 = cfg["dist2"].reindex(index=crossdocks, columns=dcs)
    dist2_new = cfg["dist2_new"].reindex(index=new_locs if new_locs else cfg["new_locs_all"], columns=dcs)
    dist3 = cfg["dist3"].reindex(index=dcs, columns=list(demand.keys()))

    # New loc variable cost
    new_loc_unitCost = {loc: (1.0 / cfg["new_loc_capacity"][loc]) * 90000.0 for loc in cfg["new_loc_capacity"]}

    # Inventory table
    inv_tbl = _lt_ss_table(float(sel.get("service_level", 0.9)), demand, cfg["unit_inventory_holdingCost"], cfg["unit_penaltycost"])
    total_demand_safe = total_demand if total_demand > 0 else 1.0

    # Flows (store per-layer per-mode totals)
    flows = {
        "L1": {"air": 0.0, "Water": 0.0},
        "L2": {"air": 0.0, "Water": 0.0, "road": 0.0},
        "L2_new": {"air": 0.0, "Water": 0.0, "road": 0.0},
        "L3": {"air": 0.0, "Water": 0.0, "road": 0.0},
    }

    # --- Layer 1: Plants -> Crossdocks (equal split over crossdocks)
    transport_L1 = 0.0
    inv_L1 = 0.0
    sourcing_L1 = 0.0
    co2_tr_L1 = {"air": 0.0, "Water": 0.0}
    for p in plants:
        mshare = _l1_modes(p)
        for c in crossdocks:
            base = plant_prod[p] / float(len(crossdocks))
            for mo in ["air", "Water"]:
                q = base * mshare[mo]
                flows["L1"][mo] += q
                d_km = float(dist1.loc[p, c])
                transport_L1 += tau[mo] * d_km * product_weight_kg * q
                inv_L1 += q * (inv_tbl["LT (days)"][mo] * inv_tbl["h (€/unit)"][mo] + inv_tbl["SS (€/unit)"][mo] / total_demand_safe)
                sourcing_L1 += sourcing_cost.get(p, 0.0) * q
                co2_tr_L1[mo] += cfg["co2_emission_factor"][mo] * d_km * product_weight_ton * q

    # --- Layer 2: Crossdocks -> DCs (equal split over DCs)
    transport_L2 = 0.0
    inv_L2 = 0.0
    handling_L2 = 0.0
    co2_tr_L2 = {"air": 0.0, "Water": 0.0, "road": 0.0}

    # Crossdock inflow from L1 is equal split across crossdocks by construction
    total_L1 = sum(plant_prod.values())
    cd_inflow = {c: (total_L1 / float(len(crossdocks))) for c in crossdocks}

    for c in crossdocks:
        mshare = _l2_modes(c)
        for d in dcs:
            base = cd_inflow[c] / float(len(dcs))
            for mo in ["air", "Water", "road"]:
                q = base * mshare[mo]
                flows["L2"][mo] += q
                d_km = float(dist2.loc[c, d])
                transport_L2 += tau[mo] * d_km * product_weight_kg * q
                inv_L2 += q * (inv_tbl["LT (days)"][mo] * inv_tbl["h (€/unit)"][mo] + inv_tbl["SS (€/unit)"][mo] / total_demand_safe)
                handling_L2 += cfg["handling_crossdock"].get(c, 0.0) * q
                co2_tr_L2[mo] += cfg["co2_emission_factor"][mo] * d_km * product_weight_ton * q

    # --- Layer 2 (new): New facilities -> DCs (equal split over DCs)
    transport_L2_new = 0.0
    inv_L2_new = 0.0
    cost_new_var = 0.0
    cost_new_fixed = 0.0
    co2_tr_L2_new = {"air": 0.0, "Water": 0.0, "road": 0.0}

    for n in new_locs:
        # Selecting a new facility means opening it: charge its fixed opening cost even if the
        # user has not (yet) allocated any production units to it.
        cost_new_fixed += cfg["new_loc_openingCost"].get(n, 0.0)
        if new_prod.get(n, 0.0) <= 1e-9:
            continue
        mshare = _l2_modes(n)
        for d in dcs:
            base = new_prod[n] / float(len(dcs))
            for mo in ["air", "Water", "road"]:
                q = base * mshare[mo]
                flows["L2_new"][mo] += q
                d_km = float(dist2_new.loc[n, d])
                transport_L2_new += tau[mo] * d_km * product_weight_kg * q
                inv_L2_new += q * (inv_tbl["LT (days)"][mo] * inv_tbl["h (€/unit)"][mo] + inv_tbl["SS (€/unit)"][mo] / total_demand_safe)
                cost_new_var += new_loc_unitCost.get(n, 0.0) * q
                co2_tr_L2_new[mo] += cfg["co2_emission_factor"][mo] * d_km * product_weight_ton * q

    # --- Layer 3: DCs -> Retailers (each retailer demand split equally over DCs)
    transport_L3 = 0.0
    inv_L3 = 0.0
    handling_L3 = 0.0
    lastmile_cost = 0.0
    co2_tr_L3 = {"air": 0.0, "Water": 0.0, "road": 0.0}

    # Delivered quantity is capped at demand: excess production is not shipped downstream.
    delivered_ratio = min(1.0, total_units / total_demand_safe)
    delivered_units = min(total_units, total_demand)
    for d in dcs:
        mshare = _l3_modes(d)
        for r, dem in demand.items():
            dem_eff = float(dem) * delivered_ratio
            base = dem_eff / float(len(dcs))
            for mo in ["air", "Water", "road"]:
                q = base * mshare[mo]
                flows["L3"][mo] += q
                d_km = float(dist3.loc[d, r])
                transport_L3 += tau[mo] * d_km * product_weight_kg * q
                inv_L3 += q * (inv_tbl["LT (days)"][mo] * inv_tbl["h (€/unit)"][mo] + inv_tbl["SS (€/unit)"][mo] / total_demand_safe)
                handling_L3 += cfg["handling_dc"].get(d, 0.0) * q
                lastmile_cost += lastmile_unit_cost * q
                co2_tr_L3[mo] += cfg["co2_emission_factor"][mo] * d_km * product_weight_ton * q

    # --- Production CO2
    co2_prod_existing_ton = 0.0
    for p in plants:
        co2_prod_existing_ton += (cfg["co2_prod_kg_per_unit"].get(p, 0.0) / 1000.0) * plant_prod[p]

    co2_prod_new_ton = 0.0
    for n in new_locs:
        co2_prod_new_ton += (cfg["new_loc_CO2"].get(n, 0.0) / 1000.0) * new_prod.get(n, 0.0)

    co2_tr_air = co2_tr_L1["air"] + co2_tr_L2["air"] + co2_tr_L2_new["air"] + co2_tr_L3["air"]
    co2_tr_Water = co2_tr_L1["Water"] + co2_tr_L2["Water"] + co2_tr_L2_new["Water"] + co2_tr_L3["Water"]
    co2_tr_road = co2_tr_L2["road"] + co2_tr_L2_new["road"] + co2_tr_L3["road"]

    co2_lastmile_ton = (lastmile_CO2_kg / 1000.0) * delivered_units
    co2_prod_ton = co2_prod_existing_ton + co2_prod_new_ton
    co2_total = co2_prod_ton + co2_tr_air + co2_tr_Water + co2_tr_road + co2_lastmile_ton

    # CO2 cost (manufacturing only, MASTER-style)
    co2_cost_per_ton = float(sel.get("co2_cost_per_ton", 37.5))
    co2_cost_per_ton_new = float(sel.get("co2_cost_per_ton_New", 60.0))
    co2_cost_existing = co2_cost_per_ton * co2_prod_existing_ton
    co2_cost_new = co2_cost_per_ton_new * co2_prod_new_ton

    total_transport = transport_L1 + transport_L2 + transport_L2_new + transport_L3
    total_inventory = inv_L1 + inv_L2 + inv_L2_new + inv_L3
    total_handling = handling_L2 + handling_L3
    total_new_locs = cost_new_var + cost_new_fixed

    objective = (
        sourcing_L1
        + total_handling
        + lastmile_cost
        + (co2_cost_existing + co2_cost_new)
        + total_transport
        + total_inventory
        + total_new_locs
    )

    # Simple checks (capacity) — DCs only handle what is delivered downstream.
    dc_out = delivered_units / float(len(dcs))
    dc_violations = {d: max(0.0, dc_out - float(cfg["dc_capacity"].get(d, 0.0))) for d in dcs}

    results = {
        "Objective_value": objective,
        "Transport_L1": transport_L1,
        "Transport_L2": transport_L2,
        "Transport_L2_new": transport_L2_new,
        "Transport_L3": transport_L3,
        "Sourcing_L1": sourcing_L1,
        "Handling_L2_total": handling_L2,
        "Handling_L3": handling_L3,
        "Inventory_L1": inv_L1,
        "Inventory_L2": inv_L2,
        "Inventory_L2_new": inv_L2_new,
        "Inventory_L3": inv_L3,
        "Transit Inventory Cost": total_inventory,
        "CO2_Manufacturing_State1": co2_cost_existing,
        "CO2_Cost_L2_2": co2_cost_new,
        "E_air": co2_tr_air,
        "E_Water": co2_tr_Water,
        "E_road": co2_tr_road,
        "E_lastmile": co2_lastmile_ton,
        "E_production": co2_prod_ton,
        "CO2_Total": co2_total,
        "LastMile_Cost": lastmile_cost,
        "Cost_NewLocs": total_new_locs,
        "dc_capacity_violations": dc_violations,
    }

    # Extra outputs for visualization parity with optimization mode
    results["puzzle_prod_sources_units"] = {**plant_prod, **new_prod}
    results["puzzle_unmet_demand_units"] = max(total_demand_safe - total_units, 0.0)
    results["puzzle_crossdock_out_units"] = dict(cd_inflow)

    return results, flows


def _render_puzzle_mode():
   
   
    st.subheader("🧩 Puzzle Mode: Build a Network ")
    st.markdown(
        "In this mode, you make the choices (facility selection, sourcing strategy, and transport mode mix). You can then see the cost and emission implications."
    )

    cfg = _puzzle_defaults()

    if SHOW_PUZZLE_SCENARIO_EVENTS_UI:
        st.markdown("#### Scenario events")

        # On/Off switch to show/hide scenario events and to apply them in computations.
        # When OFF, all scenario flags are forced to False (even if previously selected).
        try:
            enable_events = st.toggle("Enable scenario events", value=False, key="pz_enable_events")
        except Exception:
            enable_events = st.checkbox("Enable scenario events", value=False, key="pz_enable_events")

        if enable_events:
            col_ev1, col_ev2 = st.columns(2)
            with col_ev1:
                suez = st.checkbox("Suez Canal Blockade (forces L1 Water=0)", value=False, key="pz_suez")
                oil = st.checkbox("Oil Crisis (transport cost ×1.3)", value=False, key="pz_oil")
            with col_ev2:
                volcano = st.checkbox("Volcanic Eruption (no air)", value=False, key="pz_volcano")
                trade = st.checkbox("Trade War (plant sourcing × tariff)", value=False, key="pz_trade")

            tariff = 1.0
            if trade:
                tariff = st.slider("Tariff multiplier on plant sourcing", 1.0, 2.0, 1.3, 0.05, key="pz_tariff")

            scen = {
                "suez_canal": suez,
                "oil_crises": oil,
                "volcano": volcano,
                "trade_war": trade,
                "tariff_rate": tariff,
            }
        else:
            scen = {
                "suez_canal": False,
                "oil_crises": False,
                "volcano": False,
                "trade_war": False,
                "tariff_rate": 1.0,
            }
    else:
        scen = {
            "suez_canal": bool(PUZZLE_SCENARIO_EVENT_DEFAULTS.get("suez_canal", False)),
            "oil_crises": bool(PUZZLE_SCENARIO_EVENT_DEFAULTS.get("oil_crises", False)),
            "volcano": bool(PUZZLE_SCENARIO_EVENT_DEFAULTS.get("volcano", False)),
            "trade_war": bool(PUZZLE_SCENARIO_EVENT_DEFAULTS.get("trade_war", False)),
            "tariff_rate": float(PUZZLE_SCENARIO_EVENT_DEFAULTS.get("tariff_rate", 1.0)),
        }

    # Node selections
    st.markdown("#### Facility selection")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.caption("Manufacturers")
        plants = [p for p in cfg["plants_all"] if st.checkbox(p, value=True, key=f"pz_pl_{p}")]
    with col2:
        st.caption("Cross-docks")
        crossdocks = [c for c in cfg["crossdocks_all"] if st.checkbox(c, value=True, key=f"pz_cd_{c}")]
    with col3:
        st.caption("Alternative Production Facilities")
        new_locs = [n for n in cfg["new_locs_all"] if st.checkbox(n, value=False, key=f"pz_new_{n}")]
    with col4:
        st.caption("Distribution Centers")
        dcs = [d for d in cfg["dcs_all"] if st.checkbox(d, value=True, key=f"pz_dc_{d}")]
    
    total_demand = int(sum(cfg["demand"].values()))
    st.info(f"Total demand (units): **{total_demand:,}**")


    # ------------------------------------------------------------
    # UI helper: non-editable slider for computed/fixed percentages
    # ------------------------------------------------------------
    def _fixed_slider(label: str, value_pct: int, key: str):
        """Render a disabled slider (if supported) and force its value to follow `value_pct`.

        Streamlit widgets with a `key` keep their state across reruns. For computed values
        (like remainders), we must overwrite `st.session_state[key]` on every rerun, otherwise
        the widget may display a stale cached value.
        """
        value_pct = int(max(0, min(100, value_pct)))
        st.session_state[key] = value_pct
        try:
            st.slider(label, 0, 100, value_pct, 1, key=key, disabled=True)
        except TypeError:
            # Older Streamlit versions may not support `disabled=` on sliders.
            st.markdown(f"{label}: **{value_pct}%** (fixed)")

    st.markdown("#### Production allocation")
    st.caption(
        """ 
        Allocate the total average daily demand (111,000 units) across the selected production facilities. Note that alternative production facilities have production capacity limits and opening costs, whereas the current manufacturers (Taiwan and Shanghai) have sufficient capacity to meet TNE's demand.  
        If the allocated production does not satisfy the total demand, the following warning will appear: **Capacity is insufficient to meet the total demand.**

        """
    )

    # Production sources = Layer 1 plants + selected new production facilities (Layer 2)
    prod_sources = list(plants) + list(new_locs)
    if len(prod_sources) == 0:
        st.warning("⚠️ You should choose at least one production center (plant or new facility) to continue.")
        st.stop()

    if plants and not crossdocks:
        st.warning("⚠️ You should choose at least one cross-dock. Layer 1 plants require a cross-dock to route through.")
        st.stop()

    if not dcs:
        st.warning("⚠️ You should choose at least one distribution center.")
        st.stop()

    PROD_STEP = 100

    new_loc_capacity = cfg["new_loc_capacity"]

    st.caption(
        f"Distribute the total demand of **{int(total_demand):,}** units across the selected "
        "facilities. Each slider can grow into whatever demand budget is still free (and up to "
        "its own capacity), so the total **never exceeds demand** — but adjusting one facility "
        "never resets the others."
    )

    def _units_key(src: str) -> str:
        return f"pz_prod_units_{src}"

    # --- Default pass: every newly selected facility starts at 0. The user opens up exactly the
    # facilities they want and allocates units deliberately; existing allocations are untouched.
    for src in prod_sources:
        k = _units_key(src)
        if k not in st.session_state:
            st.session_state[k] = 0

    # Free budget = demand not yet allocated. Order-independent: each slider may grow by its own
    # value + free budget, so raising a facility only consumes the free budget and never zeroes
    # out the facilities listed after it.
    allocated = sum(int(st.session_state[_units_key(s)]) for s in prod_sources)
    free_budget = max(0, int(total_demand) - allocated)

    prod_units_by_source = {}
    for src in prod_sources:
        is_new = src in new_locs
        facility_cap = int(new_loc_capacity.get(src, 0)) if is_new else int(total_demand)

        k = _units_key(src)
        own = int(st.session_state[k])
        # This slider can reclaim its own value plus any free budget, bounded by its capacity.
        slider_max = int(max(0, min(facility_cap, own + free_budget)))
        st.session_state[k] = int(max(0, min(own, slider_max)))

        label = (
            f"{src} production (units) — capacity {facility_cap:,}"
            if is_new
            else f"{src} production (units)"
        )

        if slider_max < PROD_STEP:
            # No room to move: pin to the current (near-zero) value without a live slider.
            st.markdown(f"{label}: **{int(st.session_state[k]):,}** _(no remaining demand budget)_")
            val = int(st.session_state[k])
        else:
            val = st.slider(label, min_value=0, max_value=slider_max, step=PROD_STEP, key=k)

        prod_units_by_source[src] = int(val)

    total_prod = int(sum(prod_units_by_source.values()))

    # Summary bar + demand-satisfaction message (overproduction is impossible by construction).
    st.caption(f"Total production: **{total_prod:,}** / demand **{int(total_demand):,}** units")
    st.progress(min(max(total_prod / max(total_demand, 1.0), 0.0), 1.0))
    if total_prod >= total_demand:
        st.success("✅ Demand is fully satisfied.")

    # Absolute unit allocation drives the solver-free puzzle computation.
    prod_source_units = dict(prod_units_by_source)
    st.markdown("#### Transport mode shares")
    st.caption("Defaults: L1 Water=50% (air remainder), L2 Water=50% & air=50% (road remainder), L3 Water=50% & air=25% (road remainder). Shares are set in **percent (%).**")

    st.markdown("**Plant → Cross-dock**")
    l1_mode_share_by_plant = {}
    for p in plants:
        Water_pct = st.slider(f"{p} – Water share (L1) (%)", 0, 100, 50, 1, key=f"pz_l1_Water_{p}")

        # Auto remainder (non-editable): Air = 100% - Water
        air_pct = 100 - int(Water_pct)
        _fixed_slider(f"{p} – Air share (L1) (%)", air_pct, key=f"pz_l1_air_fixed_{p}")

        Water = float(Water_pct) / 100.0
        l1_mode_share_by_plant[p] = {"Water": float(Water)}

    st.markdown("**Cross-dock / New → DC**")
    l2_mode_share_by_origin = {}
    for o in list(crossdocks) + list(new_locs):
        with st.expander(f"{o}", expanded=False):
            Water_pct = st.slider("Water share (%)", 0, 100, 50, 1, key=f"pz_l2_Water_{o}")
            rem_pct = 100 - int(Water_pct)

            # Editable within remainder
            if rem_pct <= 0:
                air_pct = 0
                _fixed_slider("Air share (%)", 0, key=f"pz_l2_air_fixed_{o}")
            else:
                air_default_pct = min(50, rem_pct)
                air_pct = st.slider("Air share (%)", 0, int(rem_pct), int(air_default_pct), 1, key=f"pz_l2_air_{o}")

            # Auto remainder (non-editable): Road = 100% - Water - Air
            road_pct = max(0, 100 - int(Water_pct) - int(air_pct))
            _fixed_slider("Road share (%)", int(road_pct), key=f"pz_l2_road_fixed_{o}")

            Water = float(Water_pct) / 100.0
            air = float(air_pct) / 100.0
            l2_mode_share_by_origin[o] = {"Water": float(Water), "air": float(air)}

    st.markdown("**DC → Retailer**")
    l3_mode_share_by_dc = {}
    for d in list(dcs):
        with st.expander(f"{d}", expanded=False):
            Water_pct = st.slider("Water share (%)", 0, 100, 50, 1, key=f"pz_l3_Water_{d}")
            rem_pct = 100 - int(Water_pct)

            # Editable within remainder
            if rem_pct <= 0:
                air_pct = 0
                _fixed_slider("Air share (%)", 0, key=f"pz_l3_air_fixed_{d}")
            else:
                air_default_pct = min(25, rem_pct)
                air_pct = st.slider("Air share (%)", 0, int(rem_pct), int(air_default_pct), 1, key=f"pz_l3_air_{d}")

            # Auto remainder (non-editable): Road = 100% - Water - Air
            road_pct = max(0, 100 - int(Water_pct) - int(air_pct))
            _fixed_slider("Road share (%)", int(road_pct), key=f"pz_l3_road_fixed_{d}")

            Water = float(Water_pct) / 100.0
            air = float(air_pct) / 100.0
            l3_mode_share_by_dc[d] = {"Water": float(Water), "air": float(air)}
    # Prices are fixed to default MASTER values in Puzzle Mode (no user inputs).
    # Demand fulfillment slider was removed; we assume 100% fulfillment in computations.
    sel = {
        "plants": plants,
        "crossdocks": crossdocks,
        "dcs": dcs,
        "new_locs": new_locs,
        "prod_source_units": prod_source_units,
        "l1_mode_share_by_plant": l1_mode_share_by_plant,
        "l2_mode_share_by_origin": l2_mode_share_by_origin,
        "l3_mode_share_by_dc": l3_mode_share_by_dc,
        "service_level": 0.9,
    }

    # Block evaluation unless the full demand is satisfied, so users can't celebrate a "good"
    # score for a configuration that fails to serve the market.
    demand_satisfied = total_prod >= total_demand
    if not demand_satisfied:
        st.info("ℹ️ Satisfy the full demand to unlock the evaluation of your supply chain.")

    if st.button(
        "Evaluate performance of the supply chain configuration",
        key="pz_run",
        disabled=not demand_satisfied,
    ):
        results, flows = _compute_puzzle_results(cfg, sel, scen)

        # Persist the last run so users can submit after exploring the outputs.
        st.session_state["pz_last_results"] = results
        st.session_state["pz_last_flows"] = flows
        st.session_state["pz_last_sel"] = sel
        st.session_state["pz_last_scen"] = scen

        st.success("Computed! ✅")

        # ------------------------------------------------------------
        # Puzzle Mode Base Cases (for trade-off comparison)
        # ------------------------------------------------------------
        # Fixed reference solutions (from the shared screenshots):
        #   - Min Cost base case: (Cost, CO₂)
        #   - Min CO₂ base case: (Cost, CO₂)
        MIN_COST_BASE_CASE_EUR = 12_771_461
        MIN_COST_BASE_CASE_CO2_TON = 1_582.42

        MIN_CO2_BASE_CASE_EUR = 21_089_102
        MIN_CO2_BASE_CASE_CO2_TON = 704.09

        def _pct_change(curr: float, base: float) -> float:
            base = float(base)
            if abs(base) < 1e-12:
                return float("nan")
            return (float(curr) - base) / base * 100.0

        total_cost_val = float(results.get("Objective_value", 0.0))
        total_co2_val = float(results.get("CO2_Total", 0.0))

        # Current selection metrics
        c_cost, c_em = st.columns(2)
        with c_cost:
            st.metric("💰 Total Cost (€)", f"{total_cost_val:,.0f}")
        with c_em:
            st.metric("🌿 Total Emission (tons CO₂)", f"{total_co2_val:,.2f}")

        # Base case values + percent-change comparisons (to show the trade-off)
        st.markdown("#### 🔎 Base case comparison")
        bc1, bc2 = st.columns(2)

        with bc1:
            st.markdown("**Min Cost base case**")
            st.metric(
                "Cost (€)",
                f"{MIN_COST_BASE_CASE_EUR:,.0f}",
                delta=f"Your cost is {_pct_change(total_cost_val, MIN_COST_BASE_CASE_EUR):+,.2f}%.",
                delta_color="inverse",
            )
            st.metric(
                "CO₂e (tons)",
                f"{MIN_COST_BASE_CASE_CO2_TON:,.2f}",
                delta=f"Your CO₂e is {_pct_change(total_co2_val, MIN_COST_BASE_CASE_CO2_TON):+,.2f}%.",
                delta_color="inverse",
            )

        with bc2:
            st.markdown("**Min CO₂e base case**")
            st.metric(
                "Cost (€)",
                f"{MIN_CO2_BASE_CASE_EUR:,.0f}",
                delta=f"Your cost is {_pct_change(total_cost_val, MIN_CO2_BASE_CASE_EUR):+,.2f}%.",
                delta_color="inverse",
            )
            st.metric(
                "CO₂e (tons)",
                f"{MIN_CO2_BASE_CASE_CO2_TON:,.2f}",
                delta=f"Your CO₂e is {_pct_change(total_co2_val, MIN_CO2_BASE_CASE_CO2_TON):+,.2f}%.",
                delta_color="inverse",
            )

        st.subheader("🌿 CO₂e Emissions")
        st.json({k: f"{_safe_float(v):.2f}" for k, v in {
            "Air": results.get("E_air", 0),
            "Water": results.get("E_Water", 0),
            "Road": results.get("E_road", 0),
            "Last-mile": results.get("E_lastmile", 0),
            "Production": results.get("E_production", 0),
            "Total": results.get("CO2_Total", 0),
        }.items()})

        render_cost_emission_distribution(results)



        # ===========================================
        # 🌍 MAP (Puzzle Mode)
        # ===========================================
        st.markdown("## 🌍 Global Supply Chain Network")

        nodes = [
            ("Plant", 31.230416, 121.473701, "Shanghai"),
            ("Plant", 23.553100, 121.021100, "Taiwan"),
            ("Cross-dock", 48.856610, 2.352220, "Paris"),
            ("Cross-dock", 54.352100, 18.646400, "Gdansk"),
            ("Cross-dock", 48.208500, 16.372100, "Vienna"),
            ("DC", 50.040750, 15.776590, "Pardubice"),
            ("DC", 50.954468, 1.862801, "Calais"),
            ("DC", 56.946285, 24.105078, "Riga"),
            ("DC", 36.168056, -5.348611, "Algeciras"),
            ("Retail", 50.935173, 6.953101, "Cologne"),
            ("Retail", 51.219890, 4.403460, "Antwerp"),
            ("Retail", 50.061430, 19.936580, "Krakow"),
            ("Retail", 54.902720, 23.909610, "Kaunas"),
            ("Retail", 59.911491, 10.757933, "Oslo"),
            ("Retail", 53.350140, -6.266155, "Dublin"),
            ("Retail", 59.329440, 18.068610, "Stockholm"),
        ]

        # Filter nodes to selected facilities (Retail always shown)
        selected_cities = set((plants or []) + (crossdocks or []) + (dcs or []))
        base_nodes = [n for n in nodes if (n[3] in selected_cities) or (n[0] == "Retail")]

        # Add selected new facilities (only if produced > 0)
        facility_coords = {
            "Budapest": (47.497913, 19.040236, "Budapest"),
            "Prague": (50.088040, 14.420760, "Prague"),
            "Cork": (51.898514, -8.475604, "Cork"),
            "Helsinki": (60.169520, 24.935450, "Helsinki"),
            "Warsaw": (52.229770, 21.011780, "Warsaw"),
        }

        prod_src = results.get("puzzle_prod_sources_units", {})
        for name, (lat, lon, city) in facility_coords.items():
            if name in (new_locs or []) and float(prod_src.get(name, 0.0)) > 1e-6:
                base_nodes.append(("New Production Facility", lat, lon, city))

        locations = pd.DataFrame(base_nodes, columns=["Type", "Lat", "Lon", "City"])

        # Event overlays
        event_nodes = []
        if scen.get("suez_canal"):
            event_nodes.append(("Event: Suez Canal Blockade", 30.59, 32.27, "Suez Canal Crisis"))
        if scen.get("volcano"):
            event_nodes.append(("Event: Volcano Eruption", 63.63, -19.62, "Volcanic Ash Zone"))
        if scen.get("oil_crises"):
            event_nodes.append(("Event: Oil Crisis", 28.60, 47.80, "Oil Supply Shock"))
        if scen.get("trade_war"):
            event_nodes.append(("Event: Trade War", 55.00, 60.00, "Trade War Impact Zone"))

        if event_nodes:
            df_events = pd.DataFrame(event_nodes, columns=["Type", "Lat", "Lon", "City"])
            locations = pd.concat([locations, df_events], ignore_index=True)

        color_map = {
            "Manufacturers": "#8E24AA",
            "Cross-dock": "#4285F4",
            "DC": "#000000",
            "Retail": "#EA4335",
            "Alternatives production facilities": "#4FC3F7",
            "Event: Suez Canal Blockade": "gold",
            "Event: Volcano Eruption": "orange",
            "Event: Oil Crisis": "brown",
            "Event: Trade War": "green",
        }

        size_map = {
            "Manufacturers": 15,
            "Cross-dock": 14,
            "DC": 16,
            "Retail": 20,
            "Alternatives production facilities": 14,
            "Event: Suez Canal Blockade": 18,
            "Event: Volcano Eruption": 18,
            "Event: Oil Crisis": 18,
            "Event: Trade War": 18,
        }

        fig_map = px.scatter_geo(
            locations,
            lat="Lat",
            lon="Lon",
            color="Type",
            text="City",
            hover_name="City",
            color_discrete_map=color_map,
            projection="natural earth",
            scope="world",
            title="Global Supply Chain Structure",
        )

        for trace in fig_map.data:
            trace.marker.update(
                size=size_map.get(trace.name, 12),
                opacity=0.9,
                line=dict(width=0.5, color="white"),
            )

        fig_map.update_geos(
            showcountries=True,
            countrycolor="lightgray",
            showland=True,
            landcolor="rgb(245,245,245)",
            fitbounds="locations",
        )

        fig_map.update_layout(
            height=600,
            margin=dict(l=0, r=0, t=40, b=0),
        )

        st.plotly_chart(fig_map, use_container_width=True)

        # ===========================================
        # 🏭 Production Sourcing BREAKDOWN (Puzzle)
        # ===========================================
        st.markdown("## 🏭 Production Sourcing Breakdown")

        prod_sources = dict(results.get("puzzle_prod_sources_units", {}))
        unmet_units = float(results.get("puzzle_unmet_demand_units", 0.0))

        labels = list(prod_sources.keys()) + ["Unmet Demand"]
        values = list(prod_sources.values()) + [unmet_units]
        df_prod = pd.DataFrame({"Source": labels, "Units Produced": values})

        fig_prod = px.pie(
            df_prod,
            names="Source",
            values="Units Produced",
            hole=0.3,
            title="Production Share by Source",
        )

        color_map2 = {name: col for name, col in zip(df_prod["Source"], px.colors.qualitative.Set2)}
        color_map2["Unmet Demand"] = "lightgrey"

        fig_prod.update_traces(
            textinfo="label+percent",
            textfont_size=13,
            marker=dict(colors=[color_map2[s] for s in df_prod["Source"]]),
        )

        fig_prod.update_layout(
            showlegend=True,
            height=400,
            template="plotly_white",
            margin=dict(l=20, r=20, t=40, b=20),
        )

        st.plotly_chart(fig_prod, use_container_width=True)
        st.markdown("#### 📦 Production Summary Table")
        st.dataframe(
            df_prod.round(2),
            hide_index=True,
            column_config={
                "Units Produced": st.column_config.NumberColumn(format="%.2f"),
            },
            use_container_width=True,
        )

        # ===========================================
        # 🚚 CROSS-DOCK OUTBOUND BREAKDOWN (Puzzle)
        # ===========================================
        st.markdown("## 🚚 Cross-dock Outbound Breakdown")

        cd_out = results.get("puzzle_crossdock_out_units", {})
        if not cd_out or sum(cd_out.values()) <= 1e-9:
            st.info("No cross-dock activity.")
        else:
            df_crossdock = pd.DataFrame({
                "Crossdock": list(cd_out.keys()),
                "Shipped (units)": list(cd_out.values()),
            })
            df_crossdock["Share (%)"] = df_crossdock["Shipped (units)"] / df_crossdock["Shipped (units)"].sum() * 100

            fig_crossdock = px.pie(
                df_crossdock,
                names="Crossdock",
                values="Shipped (units)",
                hole=0.3,
                title="Cross-dock Outbound Share",
            )

            fig_crossdock.update_layout(
                showlegend=True,
                height=400,
                template="plotly_white",
                margin=dict(l=20, r=20, t=40, b=20),
            )

            st.plotly_chart(fig_crossdock, use_container_width=True)
            st.markdown("#### 🚚 Cross-dock Outbound Table")
            st.dataframe(
                df_crossdock.round(2),
                hide_index=True,
                column_config={
                    "Shipped (units)": st.column_config.NumberColumn(format="%.2f"),
                    "Share (%)": st.column_config.NumberColumn(format="%.2f"),
                },
                use_container_width=True,
            )

        # Capacity sanity check
        viol = results.get("dc_capacity_violations", {})

        # Flow totals by mode
        st.markdown("## 🚚 Transport Flows by Mode")
        cL1, cL2, cL2n, cL3 = st.columns(4)
        with cL1:
            st.caption("Manufacturers -> Cross-docs")
            st.metric("✈️ Air", f"{flows['L1']['air']:,.0f}")
            st.metric("🚢 Water", f"{flows['L1']['Water']:,.0f}")
        with cL2:
            st.caption("Cross-docks ->DCs ")
            st.metric("✈️ Air", f"{flows['L2']['air']:,.0f}")
            st.metric("🚢 Water", f"{flows['L2']['Water']:,.0f}")
            st.metric("🚛 Road", f"{flows['L2']['road']:,.0f}")
        with cL2n:
            st.caption("Alternatives production facilities ->DCs")
            st.metric("✈️ Air", f"{flows['L2_new']['air']:,.0f}")
            st.metric("🚢 Water", f"{flows['L2_new']['Water']:,.0f}")
            st.metric("🚛 Road", f"{flows['L2_new']['road']:,.0f}")
        with cL3:
            st.caption("DCs → Retailer Hub")
            st.metric("✈️ Air", f"{flows['L3']['air']:,.0f}")
            st.metric("🚢 Water", f"{flows['L3']['Water']:,.0f}")
            st.metric("🚛 Road", f"{flows['L3']['road']:,.0f}")

    # ------------------------------------------------------------
    # 📤 Puzzle submission (email + solution details -> SharePoint Excel)
    # ------------------------------------------------------------
    # Code-only toggle: set True to enable the submission UI (kept OFF by default).
    ENABLE_PUZZLE_SUBMISSION = False

    if ENABLE_PUZZLE_SUBMISSION and "pz_last_results" in st.session_state:
        st.markdown("---")
        st.subheader("📤 Submit your solution")
        st.caption(
            "Only **@uzh.ch** email addresses are accepted. If the same email submits multiple times, "
            "we keep only the **lowest-cost** submission in the Excel table (others are removed)."
        )

        if push_puzzle_submission is None:
            st.warning(
                "Submission is currently disabled because **post_data.py** is missing or misconfigured. "
                "Puzzle Mode computations are unaffected."
            )
            return

        with st.form("puzzle_submit_form", clear_on_submit=False):
            email = st.text_input("UZH email (@uzh.ch)", value="", placeholder="name.surname@uzh.ch")
            details = st.text_area(
                "Solution details (how you built the network / your reasoning)",
                value="",
                height=160,
                placeholder="Explain your decisions, constraints you targeted, trade-offs, etc.",
            )
            submitted = st.form_submit_button("Send to Excel")

        if submitted:
            email_clean = (email or "").strip().lower()
            if not re.match(r"^[a-z0-9._%+\-]+@uzh\.ch$", email_clean):
                st.error("Please enter a valid **@uzh.ch** email address.")
                return

            results = st.session_state["pz_last_results"]
            flows = st.session_state.get("pz_last_flows", {})
            sel_last = st.session_state.get("pz_last_sel", {})
            scen_last = st.session_state.get("pz_last_scen", {})

            payload = {
                "email": email_clean,
                "submitted_at_utc": datetime.now(timezone.utc).isoformat(),
                "cost_eur": float(results.get("Objective_value", 0.0)),
                "co2_total_ton": float(results.get("CO2_Total", 0.0)),
                "details": details,
                "selection": sel_last,
                "scenario": scen_last,
                "flows": flows,
                "results": {
                    # keep the payload small-ish; the server can store JSON in a single cell
                    "Objective_value": float(results.get("Objective_value", 0.0)),
                    "CO2_Total": float(results.get("CO2_Total", 0.0)),
                    "E_air": float(results.get("E_air", 0.0)),
                    "E_Water": float(results.get("E_Water", 0.0)),
                    "E_road": float(results.get("E_road", 0.0)),
                    "E_lastmile": float(results.get("E_lastmile", 0.0)),
                    "E_production": float(results.get("E_production", 0.0)),
                },
            }

            try:
                resp = push_puzzle_submission(
                    email=email_clean,
                    cost_eur=float(results.get("Objective_value", 0.0)),
                    co2_total_ton=float(results.get("CO2_Total", 0.0)),
                    details=details,
                    payload=payload,
                )
                kept = None
                if isinstance(resp, dict):
                    kept = resp.get("kept") or resp.get("status")
                st.success("Submitted ✅" + (f" (server: {kept})" if kept else ""))
            except Exception as e:
                st.error(f"Submission failed: {e}")


# ------------------------------------------------------------
# Mode selection is driven by the sidebar navigation
# ------------------------------------------------------------
mode = {
    "Optimization Mode": "Normal Mode",
    "Puzzle Mode": "Puzzle Mode",
    "Gamification Mode": "Gamification Mode",
}.get(opt_choice, "Normal Mode")

# default scenario flags
suez_flag = oil_flag = volcano_flag = trade_flag = False
tariff_rate_used = 1.0

# ------------------------------------------------------------
# PUZZLE MODE (no optimization)
# ------------------------------------------------------------
if mode == "Puzzle Mode":
    _render_puzzle_mode()
    st.stop()

# ------------------------------------------------------------
# GAMIFICATION MODE LOGIC 
# ------------------------------------------------------------
if mode == "Gamification Mode":
    gm_ctx = render_gamification_mode()

    # scenario flags
    suez_flag = gm_ctx["suez_flag"]
    oil_flag = gm_ctx["oil_flag"]
    volcano_flag = gm_ctx["volcano_flag"]
    trade_flag = gm_ctx["trade_flag"]
    tariff_rate_used = gm_ctx["tariff_rate_used"]

    # facility lists
    plants_all = gm_ctx["plants_all"]
    crossdocks_all = gm_ctx["crossdocks_all"]
    dcs_all = gm_ctx["dcs_all"]
    new_locs_all = gm_ctx["new_locs_all"]

    gm_active_plants = gm_ctx["gm_active_plants"]
    gm_active_crossdocks = gm_ctx["gm_active_crossdocks"]
    gm_active_dcs = gm_ctx["gm_active_dcs"]
    gm_active_new_locs = gm_ctx["gm_active_new_locs"]
    gm_newloc_flag_kwargs = gm_ctx["gm_newloc_flag_kwargs"]

    # modes
    gm_modes_L1 = gm_ctx["gm_modes_L1"]
    gm_modes_L2 = gm_ctx["gm_modes_L2"]
    gm_modes_L3 = gm_ctx["gm_modes_L3"]

# For Normal Mode we keep the default flags (all False, tariff 1.0)

# ------------------------------------------------------------
# Parameter Inputs
# ------------------------------------------------------------
st.subheader("📊 Scenario Parameters")

co2_pct = positive_input("Emission Reduction Target %", 50.0) / 100

# In Gamification Mode we always run the parametric MASTER model.
# Model selection has no effect there, so we hide the selector.
MODEL_LABEL_TO_ID = {
    "Scenario 1 – Existing Facilities Only (SC1F)": "SC1F",
    "Scenario 2 – Allow Alternative Production Facilities (SC2F)": "SC2F",
}

if mode == "Gamification Mode":
    model_choice_label = "Scenario 2 – Allow Alternative Production Facilities (SC2F)"
    model_id = "SC2F"
else:
    model_choice_label = st.selectbox(
        "Optimization model:",
        list(MODEL_LABEL_TO_ID.keys()),
    )
    model_id = MODEL_LABEL_TO_ID.get(model_choice_label, "SC2F")
# Base sourcing costs (same as MASTER defaults)
BASE_SOURCING_COST = {"Taiwan": 3.343692308, "Shanghai": 3.423384615}

# Expose sourcing-cost multiplier and EU carbon price only for SC2F in Normal Mode.
# (Gamification Mode keeps MASTER defaults and does not expose these controls.)
if (mode == "Normal Mode") and (model_id == "SC2F"):
    sourcing_cost_multiplier_pct = st.slider(
        "Sourcing Cost Surcharge for Asian facilites (%)",
        min_value=0,
        max_value=200,
        value=0,
        step=50,
        help="Applies only to Asia (Taiwan/Shanghai) sourcing costs. 0% = no surcharge; effective_cost = base_cost × (1 + surcharge% / 100).",
    )
    sourcing_cost_multiplier = float(sourcing_cost_multiplier_pct) / 100.0 + 1.0

    # European carbon price parameter for SC2F (new facilities)
    co2_cost_per_ton_New = st.number_input(
        "European Carbon Price (€/ton CO₂e)",
        min_value=0.0,
        value=60.0,
        step=1.0,
        help="Applies to manufacturing CO₂e cost for NEW (EU) facilities in Scenario 2.",
    )
else:
    sourcing_cost_multiplier = 1.0
    co2_cost_per_ton_New = 60.0

scaled_sourcing_cost = {k: v * float(sourcing_cost_multiplier) for k, v in BASE_SOURCING_COST.items()}

if "service_level" not in st.session_state:
    st.session_state["service_level"] = 0.90


# Only let user edit it in Normal Mode + SC1F (your requirement)
#if (mode == "Normal Mode") and (model_id == "SC1F"):
#    st.session_state["service_level"] = st.slider(
#        "Service Level",
#        min_value=0.50,
#        max_value=0.99,
#        value=float(st.session_state["service_level"]),
#        step=0.01
#    )

# Always use the persisted value everywhere (including MASTER run)
service_level = float(st.session_state["service_level"])


# CO₂ price for existing plants is fixed to default value (not user-editable here)
co2_cost_per_ton = 37.5

# ------------------------------------------------------------
# RUN OPTIMIZATION
# ------------------------------------------------------------
if st.button("Run Optimization"):
    with st.spinner("⚙ Optimizing ..."):
        try:
            # 1) Choose which model to run
            
            if mode == "Gamification Mode":
                # Use the MASTER model (compatible with multiple MASTER variants via kw filtering)
                master_kwargs = dict(
                    active_plants=gm_active_plants,
                    active_crossdocks=gm_active_crossdocks,
                    # All DCs active (UI no longer allows selecting DCs)
                    active_dcs=dcs_all,
                    # Candidate set of new locations (availability controlled via isXXX flags)
                    active_new_locs=new_locs_all,

                    active_modes_L1=gm_modes_L1,
                    active_modes_L2=gm_modes_L2,
                    active_modes_L3=gm_modes_L3,

                    # NEW: enforce transport-mode shares (per-node). None => ignored.
                    mode_share_L1_by_plant=st.session_state.get("gm_mode_share_L1_by_plant", None),
                    mode_share_L2_by_origin=st.session_state.get("gm_mode_share_L2_by_origin", None),

                    # Scenario params
                    CO_2_percentage=co2_pct,
                    co2_cost_per_ton=co2_cost_per_ton,
                    co2_cost_per_ton_New=co2_cost_per_ton_New,
                    suez_canal=suez_flag,
                    oil_crises=oil_flag,
                    volcano=volcano_flag,
                    trade_war=trade_flag,
                    tariff_rate=tariff_rate_used,
                    sourcing_cost=scaled_sourcing_cost,
                    service_level=service_level,
                    print_results="NO",
                )

                # Add per-new-location switches (isHUDTG/isCZMCT/...)
                master_kwargs.update(gm_newloc_flag_kwargs)

                results, model = run_master_filtered(master_kwargs)

                # ------------------------------------------------------------
                # Benchmarking
                # ------------------------------------------------------------
                try:
                    # Always benchmark against Scenario 2 optimal (Allow New Facilities)
                    benchmark_label = "Scenario 2 Optimal (Allow Alternative Production Facilities)"
                
                    # Use the same CO₂ price the user entered
                    # - SC1F seçiliyse: co2_cost_per_ton var
                    # - SC2F seçiliyse: co2_cost_per_ton_New var
                    bench_co2_new      = co2_cost_per_ton_New if model_id == "SC2F" else co2_cost_per_ton
                
                    bench_kwargs = dict(
                        CO_2_percentage=co2_pct,
                        co2_cost_per_ton_New=bench_co2_new,
                        suez_canal=suez_flag,
                        oil_crises=oil_flag,
                        volcano=volcano_flag,
                        trade_war=trade_flag,
                        tariff_rate=tariff_rate_used,
                        sourcing_cost=scaled_sourcing_cost,
                        print_results="NO",
                        service_level=service_level,
                    )

                    benchmark_results, benchmark_model = run_filtered(run_SC2F, bench_kwargs)
                
                except Exception as _bench_e:
                    benchmark_results = None
                    benchmark_model = None
                    benchmark_label = None
                    st.warning(f"Benchmark run failed (showing only gamification results). Reason: {_bench_e}")
                
                
                

            elif model_id == "SC1F":
                # Existing facilities only
                sc1_kwargs = dict(
                    CO_2_percentage=co2_pct,
                    co2_cost_per_ton=co2_cost_per_ton,
                    suez_canal=suez_flag,
                    oil_crises=oil_flag,
                    volcano=volcano_flag,
                    trade_war=trade_flag,
                    tariff_rate=tariff_rate_used,
                    sourcing_cost=scaled_sourcing_cost,
                    print_results="NO",
                    service_level=service_level,
                )
                results, model = run_filtered(run_SC1F, sc1_kwargs)
            else:
                # Allow new EU facilities (SC2F)
                sc2_kwargs = dict(
                    CO_2_percentage=co2_pct,
                    co2_cost_per_ton_New=co2_cost_per_ton_New,
                    suez_canal=suez_flag,
                    oil_crises=oil_flag,
                    volcano=volcano_flag,
                    trade_war=trade_flag,
                    tariff_rate=tariff_rate_used,
                    sourcing_cost=scaled_sourcing_cost,
                    print_results="NO",
                    service_level=service_level,
                )
                results, model = run_filtered(run_SC2F, sc2_kwargs)


            st.success("Optimization complete! ✅" )

            # ===========================================
            # Objective + Emissions
            # ===========================================
            c_cost, c_em = st.columns(2)

            with c_cost:
                st.metric("💰 Total Cost (€)", f"{results['Objective_value']:,.0f}")
            with c_em:
                st.metric("🌿 Total Emission (tons CO₂)", f"{results.get('CO2_Total', 0):,.2f}")

            # ------------------------------------------------------------
            # Show gap vs optimal (only in Gamification Mode)
            # ------------------------------------------------------------
            if mode == "Gamification Mode" and benchmark_results is not None:
                try:
                    stud_obj = float(results.get("Objective_value", 0.0))
                    opt_obj  = float(benchmark_results.get("Objective_value", 0.0))
                    gap = stud_obj - opt_obj
                    gap_pct = (gap / opt_obj * 100.0) if opt_obj != 0 else 0.0
            
                    st.subheader("🏁 Gap vs Optimal")
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Your Objective (€)", f"{stud_obj:,.0f}")
                    c2.metric(benchmark_label or "Optimal Objective (€)", f"{opt_obj:,.0f}")
                    c3.metric("Gap (You − Optimal)", f"{gap:,.0f}", delta=f"{gap_pct:+.0f}%")
            
                    with st.expander("See benchmark breakdown"):
                        st.json({
                            "Benchmark": benchmark_label,
                            "Benchmark Objective": opt_obj,
                            "Your Objective": stud_obj,
                            "Absolute Gap": gap,
                            "Gap (%)": gap_pct,
                        })
                except Exception:
                    pass





            st.subheader("🌿 CO₂e Emissions")
            st.json({k: f"{_safe_float(v):.2f}" for k, v in {
                "Air": results.get("E_air", 0),
                "Water": results.get("E_Water", results.get("E_sea", 0)),
                "Road": results.get("E_road", 0),
                "Last-mile": results.get("E_lastmile", 0),
                "Production": results.get("E_production", 0),
                "Total": results.get("CO2_Total", 0),
            }.items()})

            render_cost_emission_distribution(results)

            # ===========================================
            # 🌍 MAP (no more pd errors!)
            # ===========================================
            st.markdown("## 🌍 Global Supply Chain Network")

            nodes = [
                ("Plant", 31.230416, 121.473701, "Shanghai"),
                ("Plant", 23.553100, 121.021100, "Taiwan"),
                ("Cross-dock", 48.856610, 2.352220, "Paris"),
                ("Cross-dock", 54.352100, 18.646400, "Gdansk"),
                ("Cross-dock", 48.208500, 16.372100, "Vienna"),
                ("DC", 50.040750, 15.776590, "Pardubice"),
                ("DC", 50.629250, 3.057256, "Calais"),
                ("DC", 56.946285, 24.105078, "Riga"),
                ("DC", 36.168056, -5.348611, "Algeciras"),
                ("Retail", 50.935173, 6.953101, "Cologne"),
                ("Retail", 51.219890, 4.403460, "Antwerp"),
                ("Retail", 50.061430, 19.936580, "Krakow"),
                ("Retail", 54.902720, 23.909610, "Kaunas"),
                ("Retail", 59.911491, 10.757933, "Oslo"),
                ("Retail", 53.350140, -6.266155, "Dublin"),
                ("Retail", 59.329440, 18.068610, "Stockholm"),
            ]


            locations = pd.DataFrame(nodes, columns=["Type", "Lat", "Lon", "City"])

            # ================================================================
            # 🌍 FULL GLOBAL MAP (with new facilities + events)
            # ================================================================
            
            # New facilities (only if active)
            facility_coords = {
                "Budapest": (47.497913, 19.040236, "Budapest"),
                "Prague": (50.088040, 14.420760, "Prague"),
                "Cork": (51.898514, -8.475604, "Cork"),
                "Helsinki": (60.169520, 24.935450, "Helsinki"),
                "Warsaw": (52.229770, 21.011780, "Warsaw"),
            }

            
            for name, (lat, lon, city) in facility_coords.items():
                var = model.getVarByName(f"f2_2_bin[{name}]")
                if var is not None and var.X > 0.5:
                    nodes.append(("New Production Facility", lat, lon, city))
            
            # Build DataFrame
            locations = pd.DataFrame(nodes, columns=["Type", "Lat", "Lon", "City"])
            
            # ================================================================
            # Add EVENT MARKERS to the map
            # ================================================================
            event_nodes = []
            
            if suez_flag:
                event_nodes.append(("Event: Suez Canal Blockade", 30.59, 32.27, "Suez Canal Crisis"))
            
            if volcano_flag:
                event_nodes.append(("Event: Volcano Eruption", 63.63, -19.62, "Volcanic Ash Zone"))
            
            if oil_flag:
                event_nodes.append(("Event: Oil Crisis", 28.60, 47.80, "Oil Supply Shock"))
            
            if trade_flag:
                event_nodes.append(("Event: Trade War", 55.00, 60.00, "Trade War Impact Zone"))
            
            if event_nodes:
                df_events = pd.DataFrame(event_nodes, columns=["Type", "Lat", "Lon", "City"])
                locations = pd.concat([locations, df_events], ignore_index=True)
            
            # ================================================================
            # Marker colors & sizes
            # ================================================================
            color_map = {
                "Plant": "purple",
                "Cross-dock": "dodgerblue",
                "DC": "black",
                "Retail": "red",
                "New Production Facility": "deepskyblue",
                "Event: Suez Canal Blockade": "gold",
                "Event: Volcano Eruption": "orange",
                "Event: Oil Crisis": "brown",
                "Event: Trade War": "green",
            }
            
            size_map = {
                "Plant": 15,
                "Cross-dock": 14,
                "DC": 16,
                "Retail": 20,
                "New Production Facility": 14,
                "Event: Suez Canal Blockade": 18,
                "Event: Volcano Eruption": 18,
                "Event: Oil Crisis": 18,
                "Event: Trade War": 18,
            }

            
            # ================================================================
            # Build MAP
            # ================================================================
            fig_map = px.scatter_geo(
                locations,
                lat="Lat",
                lon="Lon",
                color="Type",
                text="City",
                hover_name="City",
                color_discrete_map=color_map,
                projection="natural earth",
                scope="world",
                title="Global Supply Chain Structure",
            )
            
            # compute activity once
            key_thr = compute_key_throughput(model)
            
            for trace in fig_map.data:
                trace.marker.update(
                    size=size_map.get(trace.name, 12),
                    line=dict(width=0.5, color="white"),
                )
            
                if trace.name.startswith("Event:") or trace.name == "New Production Facility":
                    trace.marker.update(opacity=0.9)
                    continue
            
                if hasattr(trace, "text") and trace.text is not None:
                    per_point_opacity = [
                        0.9 if city_is_active(city, key_thr) else 0.25
                        for city in trace.text
                    ]
                    trace.marker.update(opacity=per_point_opacity)
                else:
                    trace.marker.update(opacity=0.9)

            
                # Events and New Production Facility -> always bright (unchanged behaviour)
                if trace.name.startswith("Event:") or trace.name == "New Production Facility":
                    trace.marker.update(opacity=0.9)
                    continue
            
                # For other facility types: per-point opacity based on City activity
                # px.scatter_geo puts city labels into trace.text
                if hasattr(trace, "text") and trace.text is not None:
                    per_point_opacity = [
                        0.9 if city_is_active(city, key_thr) else 0.25
                        for city in trace.text
                    ]
                    trace.marker.update(opacity=per_point_opacity)
                else:
                    trace.marker.update(opacity=0.9)

            
            fig_map.update_geos(
                showcountries=True,
                countrycolor="lightgray",
                showland=True,
                landcolor="rgb(245,245,245)",
                fitbounds="locations",
            )
            
            fig_map.update_layout(
                height=600,
                margin=dict(l=0, r=0, t=40, b=0),
            )
            
            st.plotly_chart(fig_map, use_container_width=True)
            
            
            
            # ================================================================
            # 🏭 Production Sourcing PIE CHART
            # ================================================================
            st.markdown("## 🏭 Production Sourcing Breakdown")
            
            TOTAL_MARKET_DEMAND = 111000
            
            f1_vars = [v for v in model.getVars() if v.VarName.startswith("f1[")]
            f2_2_vars = [v for v in model.getVars() if v.VarName.startswith("f2_2[")]
            
            prod_sources = {}
            
            # Existing plants
            for plant in ["Taiwan", "Shanghai"]:
                total = sum(v.X for v in f1_vars if v.VarName.startswith(f"f1[{plant},"))
                prod_sources[plant] = total
            
            # New EU facilities
            for fac in ["Budapest", "Prague", "Cork", "Helsinki", "Warsaw"]:
                total = sum(v.X for v in f2_2_vars if v.VarName.startswith(f"f2_2[{fac},"))
                prod_sources[fac] = total
            
            total_produced = sum(prod_sources.values())
            unmet = max(TOTAL_MARKET_DEMAND - total_produced, 0)
            
            labels = list(prod_sources.keys()) + ["Unmet Demand"]
            values = list(prod_sources.values()) + [unmet]
            
            df_prod = pd.DataFrame({"Source": labels, "Units Produced": values})
            
            fig_prod = px.pie(
                df_prod,
                names="Source",
                values="Units Produced",
                hole=0.3,
                title="Production Share by Source",
            )
            
            color_map = {name: col for name, col in zip(df_prod["Source"], px.colors.qualitative.Set2)}
            color_map["Unmet Demand"] = "lightgrey"
            
            fig_prod.update_traces(
                textinfo="label+percent",
                textfont_size=13,
                marker=dict(colors=[color_map[s] for s in df_prod["Source"]])
            )
            
            fig_prod.update_layout(
                showlegend=True,
                height=400,
                template="plotly_white",
                margin=dict(l=20, r=20, t=40, b=20)
            )
            
            st.plotly_chart(fig_prod, use_container_width=True)
            st.markdown("#### 📦 Production Summary Table")
            st.dataframe(df_prod.round(2), use_container_width=True)
            
            
            
            # ================================================================
            # 🚚 CROSS-DOCK OUTBOUND PIE CHART
            # ================================================================
            st.markdown("## 🚚 Cross-dock Outbound Breakdown")
            
            f2_vars = [v for v in model.getVars() if v.VarName.startswith("f2[")]
            
            crossdocks = ["Vienna", "Gdansk", "Paris"]
            crossdock_flows = {}
            
            for cd in crossdocks:
                total = sum(v.X for v in f2_vars if v.VarName.startswith(f"f2[{cd},"))
                crossdock_flows[cd] = total
            
            if sum(crossdock_flows.values()) == 0:
                st.info("No cross-dock activity.")
            else:
                df_crossdock = pd.DataFrame({
                    "Crossdock": list(crossdock_flows.keys()),
                    "Shipped (units)": list(crossdock_flows.values()),
                })
                df_crossdock["Share (%)"] = df_crossdock["Shipped (units)"] / df_crossdock["Shipped (units)"].sum() * 100
            
                fig_crossdock = px.pie(
                    df_crossdock,
                    names="Crossdock",
                    values="Shipped (units)",
                    hole=0.3,
                    title="Cross-dock Outbound Share"
                )
            
                fig_crossdock.update_layout(
                    showlegend=True,
                    height=400,
                    template="plotly_white",
                    margin=dict(l=20, r=20, t=40, b=20),
                )
            
                st.plotly_chart(fig_crossdock, use_container_width=True)
            
                st.markdown("#### 🚚 Cross-dock Outbound Table")
                st.dataframe(df_crossdock.round(2), use_container_width=True)


            # ================================================================
            # 🚚 Transport Flows by Mode (match SC1/SC2 apps)
            # ================================================================
            render_transport_flows_by_mode(model)

        except Exception as e:
            # --------------------------------------------------
            # PRIMARY MODEL FAILED
            # --------------------------------------------------
            st.error(f"❌ Primary optimization failed: {e}")

            # In Gamification Mode we DO NOT run SC1F/SC2F_uns,
            # because they ignore the student's facility/mode choices.
            if mode == "Gamification Mode":
                st.warning(
                    "Fallback models are only defined for Scenario 1/Scenario 2. "
                    "In Gamification Mode, please adjust your facility / mode "
                    "selection or relax the CO₂e target and try again."
                )

            else:
                st.warning("⚠ Running fallback model to compute maximum satisfiable demand...")

                try:
                    # --------------------------------------------------
                    # CHOOSE CORRECT FALLBACK MODEL
                    # --------------------------------------------------
                    if model_id == "SC2F":
                        from Scenario_Setting_For_SC2F_uns import run_scenario as run_Uns
                        results_uns, model_uns = run_Uns(
                            CO_2_percentage=co2_pct,
                            co2_cost_per_ton_New=co2_cost_per_ton_New,
                            suez_canal=suez_flag,
                            oil_crises=oil_flag,
                            volcano=volcano_flag,
                            trade_war=trade_flag,
                            tariff_rate=tariff_rate_used,
                            print_results="NO",
                        )
                    else:
                        from Scenario_Setting_For_SC1F_uns import run_scenario as run_Uns
                        results_uns, model_uns = run_Uns(
                            CO_2_percentage=co2_pct,
                            co2_cost_per_ton=co2_cost_per_ton,
                            suez_canal=suez_flag,
                            oil_crises=oil_flag,
                            volcano=volcano_flag,
                            trade_war=trade_flag,
                            tariff_rate=tariff_rate_used,
                            print_results="NO",
                        )

                    # --------------------------------------------------
                    # SUCCESS DISPLAY (FALLBACK MODEL)
                    # --------------------------------------------------
                    st.success("Fallback optimization successful! ✅")

                    # ===================================================
                    # 📦 MAXIMUM SATISFIABLE DEMAND
                    # ===================================================
                    st.markdown("## 📦 Maximum Satisfiable Demand ")

                    st.metric(
                        "Satisfied Demand (%)",
                        f"{results_uns['Satisfied_Demand_pct'] * 100:.2f}%"
                    )

                    st.metric(
                        "Satisfied Demand (Units)",
                        f"{results_uns['Satisfied_Demand_units']:,.0f}"
                    )

                    # ===================================================
                    # 💰 OBJECTIVE
                    # ===================================================
                    st.markdown("## 💰 Objective Value ")
                    st.metric(
                        "Objective (€)",
                        f"{results_uns['Objective_value']:,.0f}"
                    )

                    render_cost_emission_distribution(results_uns)

                    # ===================================================
                    # 🌍 MAP
                    # ===================================================
                    st.markdown("## 🌍 Global Supply Chain Network ")

                    nodes = [
                    ("Plant", 31.230416, 121.473701, "Shanghai"),
                    ("Plant", 23.553100, 121.021100, "Taiwan"),
                    ("Cross-dock", 48.856610, 2.352220, "Paris"),
                    ("Cross-dock", 54.352100, 18.646400, "Gdansk"),
                    ("Cross-dock", 48.208500, 16.372100, "Vienna"),
                    ("DC", 50.040750, 15.776590, "Pardubice"),
                    ("DC", 50.629250, 3.057256, "Calais"),
                    ("DC", 56.946285, 24.105078, "Riga"),
                    ("DC", 36.168056, -5.348611, "Algeciras"),
                    ("Retail", 50.935173, 6.953101, "Cologne"),
                    ("Retail", 51.219890, 4.403460, "Antwerp"),
                    ("Retail", 50.061430, 19.936580, "Krakow"),
                    ("Retail", 54.902720, 23.909610, "Kaunas"),
                    ("Retail", 59.911491, 10.757933, "Oslo"),
                    ("Retail", 53.350140, -6.266155, "Dublin"),
                    ("Retail", 59.329440, 18.068610, "Stockholm"),
                    ]

                    # Add new facilities from fallback model
                    facility_coords = {
                        "Budapest": (47.497913, 19.040236, "Budapest"),
                        "Prague": (50.088040, 14.420760, "Prague"),
                        "Cork": (51.898514, -8.475604, "Cork"),
                        "Helsinki": (60.169520, 24.935450, "Helsinki"),
                        "Warsaw": (52.229770, 21.011780, "Warsaw"),
                    }

                    for name, (lat, lon, city) in facility_coords.items():
                        var = model_uns.getVarByName(f"f2_2_bin[{name}]")
                        if var is not None and var.X > 0.5:
                            nodes.append(("New Production Facility", lat, lon, city))

                    locations = pd.DataFrame(nodes, columns=["Type", "Lat", "Lon", "City"])

                    # Event overlays
                    event_nodes = []
                    if suez_flag:
                        event_nodes.append(
                            ("Event: Suez Canal Blockade", 30.59, 32.27, "Suez Canal Crisis")
                        )
                    if volcano_flag:
                        event_nodes.append(
                            ("Event: Volcano Eruption", 63.63, -19.62, "Volcanic Ash Zone")
                        )
                    if oil_flag:
                        event_nodes.append(
                            ("Event: Oil Crisis", 28.60, 47.80, "Oil Supply Shock")
                        )
                    if trade_flag:
                        event_nodes.append(
                            ("Event: Trade War", 55.00, 60.00, "Trade War Impact Zone")
                        )

                    if event_nodes:
                        df_events = pd.DataFrame(event_nodes, columns=["Type", "Lat", "Lon", "City"])
                        locations = pd.concat([locations, df_events], ignore_index=True)

                    color_map = {
                        "Plant": "purple",
                        "Cross-dock": "dodgerblue",
                        "DC": "black",
                        "Retail": "red",
                        "New Production Facility": "deepskyblue",
                        "Event: Suez Canal Blockade": "gold",
                        "Event: Volcano Eruption": "orange",
                        "Event: Oil Crisis": "brown",
                        "Event: Trade War": "green",
                    }

                    size_map = {
                        "Plant": 15,
                        "Cross-dock": 14,
                        "DC": 16,
                        "Retail": 20,
                        "New Production Facility": 14,
                        "Event: Suez Canal Blockade": 18,
                        "Event: Volcano Eruption": 18,
                        "Event: Oil Crisis": 18,
                        "Event: Trade War": 18,
                    }

                    fig_map = px.scatter_geo(
                        locations,
                        lat="Lat",
                        lon="Lon",
                        color="Type",
                        text="City",
                        hover_name="City",
                        color_discrete_map=color_map,
                        projection="natural earth",
                        scope="world",
                        title="Global Supply Chain Structure ",
                    )

                    for trace in fig_map.data:
                        trace.marker.update(
                            size=size_map.get(trace.name, 12),
                            opacity=0.9,
                            line=dict(width=0.5, color="white"),
                        )

                    fig_map.update_geos(
                        showcountries=True,
                        countrycolor="lightgray",
                        showland=True,
                        landcolor="rgb(245,245,245)",
                        fitbounds="locations",
                    )

                    fig_map.update_layout(
                        height=600,
                        margin=dict(l=0, r=0, t=40, b=0),
                    )

                    st.plotly_chart(fig_map, use_container_width=True)

                    # ===================================================
                    # 🏭 Production Sourcing PIE CHART
                    # ===================================================
                    st.markdown("## 🏭 Production Sourcing Breakdown ")

                    f1_vars = [v for v in model_uns.getVars() if v.VarName.startswith("f1[")]
                    f2_2_vars = [v for v in model_uns.getVars() if v.VarName.startswith("f2_2[")]

                    prod_sources = {}

                    # Existing plants
                    for plant in ["Taiwan", "Shanghai"]:
                        total = sum(v.X for v in f1_vars if v.VarName.startswith(f"f1[{plant},"))
                        prod_sources[plant] = total

                    # New EU facilities
                    for fac in ["Budapest", "Prague", "Cork", "Helsinki", "Warsaw"]:
                        total = sum(v.X for v in f2_2_vars if v.VarName.startswith(f"f2_2[{fac},"))
                        prod_sources[fac] = total

                    TOTAL_MARKET_DEMAND = 111000
                    total_produced = sum(prod_sources.values())
                    unmet = max(TOTAL_MARKET_DEMAND - total_produced, 0)

                    labels = list(prod_sources.keys()) + ["Unmet Demand"]
                    values = list(prod_sources.values()) + [unmet]

                    df_prod = pd.DataFrame({"Source": labels, "Units Produced": values})

                    fig_prod = px.pie(
                        df_prod,
                        names="Source",
                        values="Units Produced",
                        hole=0.3,
                        title="Production Share by Source ",
                    )

                    fig_prod.update_traces(
                        textinfo="label+percent",
                        textfont_size=13,
                    )

                    st.plotly_chart(fig_prod, use_container_width=True)
                    st.dataframe(df_prod.round(2), use_container_width=True)

                    # ===================================================
                    # 🚚 CROSS-DOCK OUTBOUND PIE CHART
                    # ===================================================
                    st.markdown("## 🚚 Cross-dock Outbound Breakdown ")

                    f2_vars = [v for v in model_uns.getVars() if v.VarName.startswith("f2[")]

                    crossdocks = ["Vienna", "Gdansk", "Paris"]
                    crossdock_flows = {}

                    for cd in crossdocks:
                        total = sum(v.X for v in f2_vars if v.VarName.startswith(f"f2[{cd},"))
                        crossdock_flows[cd] = total

                    if sum(crossdock_flows.values()) == 0:
                        st.info("No cross-dock activity.")
                    else:
                        df_crossdock = pd.DataFrame({
                            "Crossdock": list(crossdock_flows.keys()),
                            "Shipped (units)": list(crossdock_flows.values()),
                        })
                        df_crossdock["Share (%)"] = (
                            df_crossdock["Shipped (units)"] /
                            df_crossdock["Shipped (units)"].sum()
                        ) * 100

                        fig_crossdock = px.pie(
                            df_crossdock,
                            names="Crossdock",
                            values="Shipped (units)",
                            hole=0.3,
                            title="Cross-dock Outbound Share ",
                        )

                        st.plotly_chart(fig_crossdock, use_container_width=True)
                        st.dataframe(df_crossdock.round(2), use_container_width=True)

                    # ================================================================
                    # 🚚 Transport Flows by Mode (match SC1/SC2 apps)
                    # ================================================================
                    render_transport_flows_by_mode(model_uns)

                except Exception as e2:
                    st.error(f"❌ Fallback model also failed: {e2}")
