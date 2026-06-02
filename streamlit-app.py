# -*- coding: utf-8 -*-
"""
Streamlit Dashboard – Sensitivity and Factory Insights
Author: Arda Aydın 
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import requests
from io import BytesIO
import openpyxl

import streamlit.components.v1 as components
    

# ----------------------------------------------------
# GA TRACKING SHOULD BE HERE
# ----------------------------------------------------
GA_MEASUREMENT_ID = "G-3VLC0TEGGV"

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

    console.log("GA injected into TOP WINDOW → OK");

}})();
</script>
""", height=50)



# ----------------------------------------------------
# CONFIGURATION
# ----------------------------------------------------
st.set_page_config(
    page_title="Optimization Sensitivity Dashboard",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🏭 Local Sourcing for Resilience and Impact")

# ----------------------------------------------------
# 🧭 CACHED DATA LOADERS
# ----------------------------------------------------
@st.cache_data(show_spinner="📡 Reading Excel sheets...")
def get_sheet_names(path: str):
    """Return all sheet names from a local Excel file."""
    try:
        wb = openpyxl.load_workbook(path, read_only=True)
        return wb.sheetnames
    except Exception:
        return []

@st.cache_data(show_spinner="📡 Loading sheet...")
def load_data_from_excel(path: str, sheet: str):
    """Load a specific sheet from a local Excel file."""
    return pd.read_excel(path, sheet_name=sheet)

@st.cache_data(show_spinner="📡 Fetching backup data from GitHub...")
def load_data_from_github(url: str):
    """Fallback GitHub loader (for hosted dashboard)."""
    response = requests.get(url)
    response.raise_for_status()
    return pd.read_excel(BytesIO(response.content), sheet_name="Summary")



def format_number(value):
    """Format numbers with thousand separators and max two decimals."""
    try:
        return f"{float(value):,.2f}"
    except (ValueError, TypeError):
        return value


# ----------------------------------------------------
# 📦 DEMAND FULFILLMENT RATE SELECTION
# ----------------------------------------------------
st.sidebar.header("📦 Demand Fulfillment Rate (%)")

LOCAL_XLSX_PATH = "simulation_results_demand_levelsSC2.xlsx"
available_sheets = get_sheet_names(LOCAL_XLSX_PATH)

# Auto-detect demand-level sheets (contain % or “Demand”)
demand_sheets = [s for s in available_sheets if "%" in s or "Demand" in s]
if not demand_sheets:
    demand_sheets = available_sheets

selected_demand = st.sidebar.selectbox(
    "Demand Fulfillment Rate (%)",
    demand_sheets if demand_sheets else ["Default"],
    index=0,
    help="Select which demand fulfillment rate's results to visualize."
)

# ----------------------------------------------------
# LOAD DATA (local first, then fallback to GitHub)
# ----------------------------------------------------
GITHUB_XLSX_URL = (
    "https://raw.githubusercontent.com/aydınarda/TGE_CASE-web-page/main/"
    "simulation_results_full.xlsx"
)

try:
    if available_sheets:
        df = load_data_from_excel(LOCAL_XLSX_PATH, sheet=selected_demand).round(2)

    else:
        df = load_data_from_github(GITHUB_XLSX_URL).round(2)
        st.info("⚙️ Local file not found — loaded default GitHub data instead.")
except Exception as e:
    st.error(f"❌ Failed to load data: {e}")
    st.stop()
    
df_display = df.applymap(format_number)


# ----------------------------------------------------
# 🔄 PREPROCESSING (unchanged)
# ----------------------------------------------------
@st.cache_data
def preprocess(df: pd.DataFrame):
    """Group the dataframe by Product_weight for faster filtering."""
    if "Product_weight" not in df.columns:
        return {"N/A": df}
    return {w: d for w, d in df.groupby("Product_weight")}

@st.cache_data
def compute_pivot(df: pd.DataFrame):
    """Compute factory openings pivot once for heatmap."""
    if "f2_2" not in df.columns:
        return pd.DataFrame()
    return df.groupby(["CO2_percentage", "Product_weight"])["f2_2"].mean().unstack()

data_by_weight = preprocess(df)

# ----------------------------------------------------
# SIDEBAR FILTERS (simplified)
# ----------------------------------------------------
st.sidebar.header("🎛️ Filter Parameters")

# 🎯 CO₂ reduction slider (0.00–1.00 = 0–100%)
# 🎯 CO₂ reduction slider (0–100% visual, internal 0–1)
default_val = float(df["CO2_percentage"].mean()) if "CO2_percentage" in df.columns else 0.5

# ✅ Always start from 0% CO₂ reduction
default_val = 0.0  # (fractional form, 0.0 = 0%)

co2_pct_display = st.sidebar.slider(
    "CO₂ Reduction Target (%)",
    min_value=0,
    max_value=100,
    value=int(default_val * 100),  # ✅ default = 0%
    step=1,
    help="Set a CO₂ reduction target between 0–100 %.",
)

# Convert displayed percentage back to 0–1 for internal matching
co2_pct = co2_pct_display / 100.0


# 🎯 Carbon price selector (work with either column name)
co2_cost_options = [0, 20, 40, 60, 80, 100]
co2_cost = st.sidebar.select_slider(
    "CO₂ Price in Europe (€ per ton)",
    options=co2_cost_options,
    value=60,
    help="Select the EU carbon price column value."
)

# Decide which column the dataset uses for EU carbon price
price_col = None
if "CO2_CostAtMfg" in df.columns:
    price_col = "CO2_CostAtMfg"
elif "CO2_CostAtEU" in df.columns:
    price_col = "CO2_CostAtEU"

# Apply price filter if we found a price column, otherwise keep all rows
pool = df.copy() if price_col is None else df[df[price_col] == co2_cost]

if pool.empty:
    st.error("This solution is not feasible — even Swiss precision couldn’t optimize it! 🇨🇭")
    st.stop()

# Require an **exact** match for the chosen CO₂ reduction (as requested)
TOL = 1e-9
exact = pool[(pool["CO2_percentage"] - co2_pct).abs() < TOL] if "CO2_percentage" in pool.columns else pd.DataFrame()

if exact.empty:
    # No feasible solution for this exact CO₂ target at this price → show the funny message and stop
    st.error(
        "This solution is not feasible — even Swiss precision couldn’t optimize it! 🇨🇭"
    )
    st.stop()

# Pick the first exact match (you can later add tie-breakers if needed)
closest = exact.iloc[0]

# ----------------------------------------------------
# FILTER SUBSET AND FIND CLOSEST SCENARIO
# ----------------------------------------------------
pool = df[df["CO2_CostAtMfg"] == co2_cost] if "CO2_CostAtMfg" in df.columns else df.copy()

if pool.empty:
    st.warning("⚠️ No scenarios match this CO₂ price — showing all instead.")
    pool = df.copy()

# Find closest feasible scenario to chosen CO₂ reduction
try:
    closest_idx = (pool["CO2_percentage"] - co2_pct).abs().argmin()
    closest = pool.iloc[closest_idx]
except Exception:
    st.error("💥 The optimizer fainted — no matching CO₂ targets exist in this dataset! 🌀")
    st.stop()

# ----------------------------------------------------
# CHECK FOR FEASIBILITY / FUNNY MESSAGE
# ----------------------------------------------------
if pd.isna(closest.get("Objective_value", None)):
    st.error(
        "This solution is not feasible — even Swiss precision couldn’t optimize it! 🇨🇭"
    )
    st.stop()

if closest.get("Status", "") not in ["OPTIMAL", 2]:
    st.warning(
        "🤖 Hmm... looks like this one didn’t converge to perfection. "
        "We’ll show you the closest feasible setup anyway. 💪"
    )


# ----------------------------------------------------
# KPI VIEW
# ----------------------------------------------------
st.subheader("📊 Closest Scenario Details")
# Hide any column starting with 'f' (case-insensitive)
closest_df = closest.to_frame().T  # transpose for row→column view

# Remove columns starting with 'f'
cols_to_show = [c for c in closest_df.columns if not (c.lower().startswith("f") or c.lower().startswith("scenario_id"))]

# Display cleaned table
st.write(closest_df[cols_to_show].applymap(format_number))

col1, col2, col3, col4 = st.columns(4)

col1.metric("Total Cost (€)", f"{closest['Objective_value']:,.2f}")
col2.metric("Total CO₂", f"{closest['CO2_Total']:,.2f}")
col3.metric("Inventory Total (€)", f"{closest[['Inventory_L1','Inventory_L2','Inventory_L3']].sum():,.2f}")
col4.metric("Transport Total (€)", f"{closest[['Transport_L1','Transport_L2','Transport_L3']].sum():,.2f}")

# ----------------------------------------------------
# COST vs EMISSION SENSITIVITY PLOT
# ----------------------------------------------------
st.markdown("## 📈 Cost vs CO₂ Emission Sensitivity")

# Let user choose which cost metric to plot
cost_metric_map = {
    "Total Cost (€)": "Objective_value",
    "Inventory Cost (€)": ["Inventory_L1", "Inventory_L2", "Inventory_L3"],
    "Transport Cost (€)": ["Transport_L1", "Transport_L2", "Transport_L3"],
}

selected_metric_label = st.selectbox(
    "Select Cost Metric to Plot:",
    list(cost_metric_map.keys()),
    index=0,
    help="Choose which cost metric to show on the Y-axis."
)

# Compute total columns if needed
filtered = pool.copy()
if isinstance(cost_metric_map[selected_metric_label], list):
    filtered["Selected_Cost"] = filtered[cost_metric_map[selected_metric_label]].sum(axis=1)
    y_label = selected_metric_label
else:
    filtered["Selected_Cost"] = filtered[cost_metric_map[selected_metric_label]]
    y_label = selected_metric_label
if not filtered.empty:
    # Detect which CO₂ price column exists
    if "CO2_CostAtMfg" in filtered.columns:
        price_col = "CO2_CostAtMfg"
    elif "CO2_CostAtEU" in filtered.columns:
        price_col = "CO2_CostAtEU"
    else:
        price_col = None

    # Build hover columns dynamically
    hover_cols = ["Product_weight", "CO2_percentage"]
    if price_col:
        hover_cols.insert(0, price_col)

    # Create sensitivity scatter plot
    fig_sens = px.scatter(
        filtered,
        x="CO2_Total",
        y="Selected_Cost",
        color="CO2_percentage",
        hover_data=hover_cols,
        title=f"{selected_metric_label} vs Total CO₂ ({price_col or 'CO₂ price'} = {co2_cost} €/ton)",
        labels={
            "CO2_Total": "Total CO₂ Emissions (tons)",
            "Selected_Cost": y_label
        },
        color_continuous_scale="Viridis",
        template="plotly_white"
    )

    # Highlight current scenario
    if isinstance(cost_metric_map[selected_metric_label], list):
        closest_y = closest[cost_metric_map[selected_metric_label]].sum()
    else:
        closest_y = closest[cost_metric_map[selected_metric_label]]

    fig_sens.add_scatter(
        x=[closest["CO2_Total"]],
        y=[closest_y],
        mode="markers+text",
        marker=dict(size=16, color="red"),
        text=["Current Selection"],
        textposition="top center",
        name="Selected Scenario"
    )

    st.plotly_chart(fig_sens, use_container_width=True)
else:
    st.warning("No scenarios found for this exact combination to show sensitivity.")
    
# ----------------------------------------------------
# 🏭 PRODUCTION OUTBOUND PIE CHART (f1 + f2_2)
# ----------------------------------------------------
# --- Display chart, outbound table, and static CO₂ table side by side ---

st.markdown("## 🏭 Production Outbound Breakdown")

# --- total market demand (fixed reference) ---
TOTAL_MARKET_DEMAND = 111000  # units

# --- Gather flow variable columns ---
f1_cols = [c for c in closest.index if c.startswith("f1[")]
f2_2_cols = [c for c in closest.index if c.startswith("f2_2[")]

# --- Calculate production sums ---
prod_sources = {}

# Existing plants (f1)
for plant in ["TW", "SHA"]:
    prod_sources[plant] = sum(
        float(closest[c]) for c in f1_cols if c.startswith(f"f1[{plant},")
    )

# New European factories (f2_2)
new_facilities = ["HUDTG", "CZMCT", "IEILG", "FIMPF", "PLZCA"]
for fac in new_facilities:
    prod_sources[fac] = sum(
        float(closest[c]) for c in f2_2_cols if c.startswith(f"f2_2[{fac},")
    )

# --- Compute totals and unmet demand ---
total_produced = sum(prod_sources.values())
unmet = max(TOTAL_MARKET_DEMAND - total_produced, 0)

# --- Convert to percentages (over full demand) ---
labels = list(prod_sources.keys()) + ["Unmet Demand"]
values = [prod_sources[k] for k in prod_sources] + [unmet]
percentages = [v / TOTAL_MARKET_DEMAND * 100 for v in values]

# --- Build dataframe for display ---
df_prod = pd.DataFrame({
    "Source": labels,
    "Produced (units)": values,
    "Share (%)": percentages
})

# --- Create pie chart ---
fig_prod = px.pie(
    df_prod,
    names="Source",
    values="Produced (units)",
    hole=0.3,
    title=f"Production Share by Source (Demand Level: {closest.get('Demand_Level', 'N/A')*100:.0f}%)",
)

# --- Make 'Unmet Demand' grey ---
color_map_prod = {name: color for name, color in zip(df_prod["Source"], px.colors.qualitative.Set2)}
color_map_prod["Unmet Demand"] = "lightgrey"

fig_prod.update_traces(
    textinfo="label+percent",
    textfont_size=13,
    marker=dict(colors=[color_map_prod.get(s, "#CCCCCC") for s in df_prod["Source"]])
)
fig_prod.update_layout(
    showlegend=True,
    height=400,
    template="plotly_white",
    margin=dict(l=20, r=20, t=40, b=20)
)

# --- Display chart, outbound table, and static CO₂ table side by side ---
colA, colB, colC = st.columns([2, 1, 1])

with colA:
    st.plotly_chart(fig_prod, use_container_width=True)

with colB:
    st.markdown("#### 📦 Production Outbounds")
    st.dataframe(df_prod.round(2), use_container_width=True)

with colC:
    st.markdown("#### 🌿 CO₂ Factors (kg/unit)")
    co2_factors_mfg = pd.DataFrame({
        "From mfg": ["TW", "SHA", "HUDTG", "CZMCT", "IEILG", "FIMPF", "PLZCA"],
        "CO₂ kg/unit": [6.3, 9.8, 3.2, 2.8, 4.6, 5.8, 6.2 ],
    })
    co2_factors_mfg["CO₂ kg/unit"] = co2_factors_mfg["CO₂ kg/unit"].map(lambda v: f"{v:.1f}")
    st.dataframe(co2_factors_mfg, use_container_width=True)


# ----------------------------------------------------
# 🚚 CROSSDOCK OUTBOUND PIE CHART (f2)
# ----------------------------------------------------
st.markdown("## 🚚 Crossdock Outbound Breakdown")

# --- total market demand reference ---
TOTAL_MARKET_DEMAND = 111000  # units

# --- Gather f2 variables (Crossdock → DC) ---
f2_cols = [c for c in df.columns if c.startswith("f2[")]

# --- Define crossdocks used in SC2 ---
crossdocks = ["ATVIE", "PLGDN", "FRCDG"]

# --- Calculate crossdock outbounds ---
crossdock_flows = {}
for cd in crossdocks:
    crossdock_flows[cd] = sum(
        float(closest[c])
        for c in f2_cols
        if c.startswith(f"f2[{cd},")
    )

# --- Compute total shipped (met demand only) ---
total_outbound_cd = sum(crossdock_flows.values())

if total_outbound_cd == 0:
    st.info("No crossdock activity recorded for this scenario.")
else:
    # --- Prepare data for chart ---
    labels_cd = list(crossdock_flows.keys())
    values_cd = [crossdock_flows[k] for k in crossdock_flows]
    percentages_cd = [v / total_outbound_cd * 100 for v in values_cd]

    df_crossdock = pd.DataFrame({
        "Crossdock": labels_cd,
        "Shipped (units)": values_cd,
        "Share (%)": percentages_cd
    })

    # --- Create pie chart (only crossdocks) ---
    fig_crossdock = px.pie(
        df_crossdock,
        names="Crossdock",
        values="Shipped (units)",
        hole=0.3,
        title=f"Crossdock Outbound Share (Demand Level: {closest.get('Demand_Level', 'N/A')*100:.0f}%)",
    )

    # --- Assign color map ---
    color_map_cd = {
        name: color for name, color in zip(
            df_crossdock["Crossdock"],
            px.colors.qualitative.Pastel
        )
    }

    fig_crossdock.update_traces(
        textinfo="label+percent",
        textfont_size=13,
        marker=dict(colors=[color_map_cd.get(s, "#CCCCCC") for s in df_crossdock["Crossdock"]])
    )
    fig_crossdock.update_layout(
        showlegend=True,
        height=400,
        template="plotly_white",
        margin=dict(l=20, r=20, t=40, b=20)
    )

    # --- Display chart, outbound table, and static CO₂ table side by side ---
    colC, colD, colE = st.columns([2, 1, 1])

    with colC:
        st.plotly_chart(fig_crossdock, use_container_width=True)

    with colD:
        st.markdown("#### 🚚 Crossdock Outbounds")
        st.dataframe(df_crossdock.round(2), use_container_width=True)


    
# ----------------------------------------------------
# 🌍 GLOBAL SUPPLY CHAIN MAP
# ----------------------------------------------------
st.markdown("## 🌍 Global Supply Chain Network")

# --- Plants (f1, China region) ---
plants = pd.DataFrame({
    "Type": ["Plant", "Plant"],
    "Lat": [31.23, 22.32],        # Shanghai & Southern China
    "Lon": [121.47, 114.17]
})

# --- Cross-docks (f2) ---
crossdocks = pd.DataFrame({
    "Type": ["Cross-dock"] * 3,
    "Lat": [48.85, 50.11, 37.98],   # France, Germany, Greece
    "Lon": [2.35, 8.68, 23.73]
})

# --- Distribution Centres (DCs) ---
dcs = pd.DataFrame({
    "Type": ["Distribution Centre"] * 4,
    "Lat": [47.50, 48.14, 46.95, 45.46],   # Central Europe
    "Lon": [19.04, 11.58, 7.44, 9.19]
})

# --- Retailer Hubs (f3) ---
retailers = pd.DataFrame({
    "Type": ["Retailer Hub"] * 7,
    "Lat": [55.67, 53.35, 51.50, 49.82, 45.76, 43.30, 40.42],  # North to South
    "Lon": [12.57, -6.26, -0.12, 19.08, 4.83, 5.37, -3.70]
})

# --- New Production Facilities (f2_2) ---
f2_2_cols = [c for c in closest.index if c.startswith("f2_2_bin")]

# Define coordinates (one per possible facility)
facility_coords = {
    "f2_2_bin[HUDTG]": (49.61, 6.13),
    "f2_2_bin[CZMCT]":  (44.83, 20.42),
    "f2_2_bin[IEILG]": (47.09, 16.37),
    "f2_2_bin[FIMPF]": (50.45, 14.50),
    "f2_2_bin[PLZCA]": (42.70, 12.65),
}

active_facilities = []
for col in f2_2_cols:
    try:
        val = float(closest[col])
        if val > 0.5 and col in facility_coords:
            lat, lon = facility_coords[col]
            active_facilities.append((col, lat, lon))
    except Exception:
        continue

if active_facilities:
    new_facilities = pd.DataFrame({
        "Type": "New Production Facility",
        "Lat": [lat for _, lat, _ in active_facilities],
        "Lon": [lon for _, _, lon in active_facilities],
        "Name": [col for col, _, _ in active_facilities]
    })
else:
    new_facilities = pd.DataFrame(columns=["Type", "Lat", "Lon", "Name"])
    
# --- Combine all ---
locations = pd.concat([plants, crossdocks, dcs, retailers, new_facilities])

# --- Define colors & sizes ---
color_map = {
    "Plant": "purple",
    "Cross-dock": "dodgerblue",
    "Distribution Centre": "black",
    "Retailer Hub": "red",
    "New Production Facility": "deepskyblue"
}

size_map = {
    "Plant": 15,
    "Cross-dock": 14,
    "Distribution Centre": 16,
    "Retailer Hub": 20,
    "New Production Facility": 14
}

# --- Create Map ---
fig_map = px.scatter_geo(
    locations,
    lat="Lat",
    lon="Lon",
    color="Type",
    color_discrete_map=color_map,
    hover_name="Type",
    projection="natural earth",
    scope="world",
    title="Global Supply Chain Structure",
    template="plotly_white"
)

# Customize markers
for trace in fig_map.data:
    trace.marker.update(size=size_map[trace.name], opacity=0.9, line=dict(width=0.5, color='white'))

fig_map.update_geos(
    showcountries=True,
    countrycolor="lightgray",
    showland=True,
    landcolor="rgb(245,245,245)",
    fitbounds="locations"
)

fig_map.update_layout(
    height=550,
    margin=dict(l=0, r=0, t=40, b=0)
)

st.plotly_chart(fig_map, use_container_width=True)

# --- Legend ---
st.markdown("""
**Legend:**
- 🏗️ **Cross-dock**  
- 🏬 **Distribution Centre**  
- 🔴 **Retailer Hub**  
- ⚙️ **New Production Facility**  
- 🏭 **Plant** 
""")


# ----------------------------------------------------
# 🚢✈️🚛 FLOW SUMMARY BY MODE PER LAYER (f1, f2, f2_2, f3)
# ----------------------------------------------------
st.markdown("## 🚚 Transport Flows by Mode")

import re

def sum_flows_by_mode(prefix):
    """Sum up air/sea/road units for a given flow prefix like 'f1', 'f2', 'f2_2', or 'f3'."""
    flow_cols = [c for c in df.columns if c.startswith(prefix + "[")]
    totals = {"air": 0.0, "sea": 0.0, "road": 0.0}

    for col in flow_cols:
        # Extract mode from inside brackets, e.g. f2_2[CZMC,DEBER,road]
        match = re.search(r",\s*([a-zA-Z]+)\]$", col)
        if match:
            mode = match.group(1).lower()
            if mode in totals:
                try:
                    totals[mode] += float(closest[col])
                except:
                    pass
    return totals


def display_layer_summary(title, prefix, include_road=True):
    totals = sum_flows_by_mode(prefix)
    st.markdown(f"### {title}")
    cols = st.columns(3 if include_road else 2)
    cols[0].metric("🚢 Sea", f"{totals['sea']:,.0f} units")
    cols[1].metric("✈️ Air", f"{totals['air']:,.0f} units")
    if include_road:
        cols[2].metric("🚛 Road", f"{totals['road']:,.0f} units")

    if sum(totals.values()) == 0:
        st.info("No transport activity recorded for this layer.")
    st.markdown("---")


# Layer summaries
display_layer_summary("Layer 1: Plants → Cross-docks", "f1", include_road=False)
display_layer_summary("Layer 2a: Cross-docks → DCs", "f2", include_road=True)
display_layer_summary("Layer 2b: New Facilities → DCs", "f2_2", include_road=True)
display_layer_summary("Layer 3: DCs → Retailer Hubs", "f3", include_road=True)

# ----------------------------------------------------
# 💰🌿 COST & EMISSION DISTRIBUTION SECTION (FINAL)
# ----------------------------------------------------
st.markdown("## 💰 Cost and 🌿 Emission Distribution")

col1, col2 = st.columns(2)

# --- 💰 Cost Distribution (calculated as before) ---
with col1:
    st.subheader("Cost Distribution")

    # --- Dynamically compute costs from model components ---
    transport_cost = (
        closest.get("Transport_L1", 0)
        + closest.get("Transport_L2", 0)
        + closest.get("Transport_L2_new", 0)
        + closest.get("Transport_L3", 0)
    )

    sourcing_handling_cost = (
        closest.get("Sourcing_L1", 0)
        + closest.get("Handling_L2_total", 0)
        + closest.get("Handling_L3", 0)
    )

    co2_cost_production1 = closest.get("CO2_Manufacturing_State1", 0)
    co2_cost_production2 = closest.get("CO2_Cost_L2_2", 0)
    co2_cost_production = co2_cost_production1 + co2_cost_production2
    
    inventory_cost = (
        closest.get("Inventory_L1", 0)
        + closest.get("Inventory_L2", 0)
        + closest.get("Inventory_L2_new", 0)
        + closest.get("Inventory_L3", 0)
    )

    # Prepare for plot
    cost_parts = {
        "Transportation Cost": transport_cost,
        "Sourcing/Handling Cost": sourcing_handling_cost,
        "CO₂ Cost in Production": co2_cost_production,
        "Inventory Cost": inventory_cost
    }

    df_cost_dist = pd.DataFrame({
        "Category": list(cost_parts.keys()),
        "Value": list(cost_parts.values())
    })

    import plotly.express as px
    fig_cost = px.bar(
        df_cost_dist,
        x="Category",
        y="Value",
        text="Value",
        color="Category",
        color_discrete_sequence=["#A7C7E7", "#B0B0B0", "#F8C471", "#5D6D7E"]
    )

    # ✅ Add commas for thousands separators
    fig_cost.update_traces(
        texttemplate="%{text:,.0f}",  # commas + 0 decimals
        textposition="outside"
    )
    fig_cost.update_layout(
        template="plotly_white",
        showlegend=False,
        xaxis_tickangle=-35,
        yaxis_title="€",
        height=400,
        yaxis_tickformat=","  # add commas to axis
    )

    st.plotly_chart(fig_cost, use_container_width=True)


# --- 🌿 Emission Distribution (from recorded columns) ---
with col2:
    st.subheader("Emission Distribution")

    # Expected emission columns
    emission_cols = ["E_air", "E_sea", "E_road", "E_lastmile", "E_production"]

    # Check if all required emission columns exist
    missing_cols = [c for c in emission_cols if c not in df.columns]
    if missing_cols:
        st.warning(f"⚠️ Missing columns: {', '.join(missing_cols)}")

    # --- Recalculate E_Production using the correct formula ---
    try:
        if all(col in df.columns for col in ["E_air", "E_sea", "E_road", "E_lastmile", "CO2_Total"]):
            corrected_E_prod = (
                float(closest["CO2_Total"])
                - float(closest["E_air"])
                - float(closest["E_sea"])
                - float(closest["E_road"])
                - float(closest["E_lastmile"])
            )

            # ✅ Include Total Transport (sum of Air + Sea + Road)
            total_transport = (
                float(closest["E_air"])
                + float(closest["E_sea"])
                + float(closest["E_road"])
            )

            emission_data = {
                "Production": corrected_E_prod,
                "Last-mile": float(closest["E_lastmile"]),
                "Air": float(closest["E_air"]),
                "Sea": float(closest["E_sea"]),
                "Road": float(closest["E_road"]),
                "Total Transport": total_transport,
            }

        else:
            st.info("⚠️ Could not recalculate E_Production — some columns are missing.")
            emission_data = {}
    except Exception as e:
        st.error(f"Error recalculating emissions: {e}")
        emission_data = {}

    # --- Plot if valid data exist ---
    if not emission_data:
        st.info("No valid emission values found in this scenario.")
    else:
        df_emission = pd.DataFrame({
            "Source": list(emission_data.keys()),
            "Emission (tons)": list(emission_data.values())
        })

        # --- Build Plotly chart ---
        fig_emission = px.bar(
            df_emission,
            x="Source",
            y="Emission (tons)",
            text="Emission (tons)",
            color="Source",
            color_discrete_sequence=[
                "#4B8A08", "#2E8B57", "#808080", "#FFD700", "#90EE90", "#000000"
            ]
        )

        # ✅ Add commas and keep 2 decimals
        fig_emission.update_traces(
            texttemplate="%{text:,.2f}",
            textposition="outside",
            marker_line_color="black",
            marker_line_width=0.5
        )

        fig_emission.update_layout(
            template="plotly_white",
            showlegend=False,
            xaxis_tickangle=-35,
            yaxis_title="Tons of CO₂",
            height=400,
            yaxis_tickformat=","  # comma separators on y-axis
            
        )

        st.plotly_chart(fig_emission, use_container_width=True)



# ----------------------------------------------------
# RAW DATA VIEW
# ----------------------------------------------------
with st.expander("📄 Show Full Summary Data"):
    st.dataframe(df.head(500), use_container_width=True)
