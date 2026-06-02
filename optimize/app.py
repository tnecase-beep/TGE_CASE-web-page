import os
import streamlit as st
import gurobipy as gp
import streamlit.components.v1 as components
import plotly.express as px
import pandas as pd



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

    console.log("GA injected into TOP WINDOW → OK");

}})();
</script>
""", height=50)


# ================================================================
# 🧩 Safe Imports
# ================================================================
try:
    from Scenario_Setting_For_SC1F import run_scenario as run_SC1F
    from Scenario_Setting_For_SC2F import run_scenario as run_SC2F
except Exception as e:
    st.error(f"❌ Error importing optimization modules: {e}")

# ================================================================
# 🔐 Load Gurobi WLS credentials (from Streamlit secrets)
# ================================================================
for var in ["GRB_WLSACCESSID", "GRB_WLSSECRET", "GRB_LICENSEID"]:
    if var in st.secrets:
        os.environ[var] = st.secrets[var]

# ================================================================
# 🏷️ Layout
# ================================================================
st.set_page_config(page_title="Global Supply Chain Optimization", layout="centered")
st.title("🌍 Global Supply Chain Optimization (Gurobi)")

# ================================================================
# SESSION MODE TOGGLE
# ================================================================
mode = st.radio("Select mode:", ["Normal Mode", "Session Mode"])

if "session_step" not in st.session_state:
    st.session_state.session_step = 0

# ================================================================
# Scenario event definitions
# ================================================================
EVENTS = {
    "suez_canal": "🚢 Suez Canal is blocked due to a crisis.",
    "oil_crises": "⛽ Global oil prices surged due to a new oil crisis.",
    "volcano": "🌋 Volcano eruption blocks all air transportation.",
    "trade_war": "💼 Trade war increases sourcing tariffs.",
}


st.markdown("Enter any numeric value (≥ 0) for each parameter below, then run the optimization.")


components.html(f"""
<script>
(function() {{

    // If inside Streamlit iframe → inject GA into TOP window instead
    const targetDoc = window.parent.document;

    // Remove existing GA scripts (avoid duplicates)
    const old1 = targetDoc.getElementById("ga-tag");
    const old2 = targetDoc.getElementById("ga-src");
    if (old1) old1.remove();
    if (old2) old2.remove();

    // Create GA script (src)
    const s1 = targetDoc.createElement('script');
    s1.id = "ga-src";
    s1.async = true;
    s1.src = "https://www.googletagmanager.com/gtag/js?id={GA_MEASUREMENT_ID}";
    targetDoc.head.appendChild(s1);

    // Create GA config script
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
""", height=100)


# ================================================================
# 🧩 Model selection
# ================================================================
model_choice = st.selectbox(
    "Select optimization model:",
    ("SC1F – Existing Facilities Only", "SC2F – Allow New Facilities")
)

# ================================================================
# 🧠 Helper function for manual numeric input
# ================================================================
def positive_input(label, default):
    """Takes a text input, validates it as a non-negative float."""
    val_str = st.text_input(label, value=str(default))
    try:
        val = float(val_str)
        if val < 0:
            st.warning(f"{label} must be ≥ 0. Using 0 instead.")
            return 0.0
        return val
    except ValueError:
        st.warning(f"{label} must be numeric. Using default {default}.")
        return default

# ================================================================
# 🎛️ Parameters
# ================================================================
st.subheader("📊 Scenario Parameters")

co2_pct = positive_input("CO₂ Reduction Target (%)", 50.0) / 100.0
product_weight = positive_input("Product Weight (kg)", 2.58)

if "SC1F" in model_choice:
    st.subheader("⚙️ Parameters for SC1F (Existing Facilities)")
    co2_cost_per_ton = positive_input("CO₂ Cost per ton (€)", 37.50)

elif "SC2F" in model_choice:
    st.subheader("⚙️ Parameters for SC2F (Allows New Facilities)")
    co2_cost_per_ton_New = positive_input("CO₂ Cost per ton (New Facilities) (€)", 60.00)



# ================================================================
# SESSION MODE EVENT POPUP LOGIC
# ================================================================
import random

def generate_tariff_rate():
    k = random.uniform(1, 2)   # Float between 1 and 2
    x_pct = ((k - 1) / k) * 100
    return k, x_pct


# ================================================================
# SESSION MODE EVENT POPUP LOGIC (ONE RANDOM EVENT EACH STEP)
# ================================================================
selected_event = None
tariff_rate_random = 1.0
tariff_x_pct = 0.0

if mode == "Session Mode":

    st.subheader("🎮 Scenario-Based Session")

    # Initialize event list only once
    if "remaining_events" not in st.session_state:
        st.session_state.remaining_events = list(EVENTS.keys())

    if st.button("Start / Continue Session"):

        # If finished all events
        if len(st.session_state.remaining_events) == 0:
            st.success("🎉 All scenarios have now been tested! Session complete.")
        else:
            # Choose 1 event at random and remove it
            chosen = random.choice(st.session_state.remaining_events)
            st.session_state.remaining_events.remove(chosen)
            st.session_state.active_event = chosen

            # Special handling for trade war (random tariff_rate)
            if chosen == "trade_war":
                k, x_pct = generate_tariff_rate()
                st.session_state.tariff_rate_random = k
                st.session_state.tariff_x_pct = x_pct

    # Display event (if exists)
    if "active_event" in st.session_state:
        e = st.session_state.active_event
        st.subheader("⚠️ Active Event")
        st.warning(EVENTS[e])

        if e == "trade_war":
            st.info(f"Tariffs are now **{st.session_state.tariff_x_pct:.1f}%** more.")

        st.write("👉 Comment below: What would be the optimal choice?")
        st.text_area("Your comment:")

    # Map event flag
    suez_flag = (st.session_state.get("active_event") == "suez_canal")
    oil_flag = (st.session_state.get("active_event") == "oil_crises")
    volcano_flag = (st.session_state.get("active_event") == "volcano")
    trade_flag = (st.session_state.get("active_event") == "trade_war")
    tariff_rate_used = st.session_state.get("tariff_rate_random", 1.0)

else:
    # Normal mode
    suez_flag = oil_flag = volcano_flag = trade_flag = False
    tariff_rate_used = 1.0



# ================================================================
# ▶️ Run Optimization
# ================================================================


if st.button("Run Optimization"):
    with st.spinner("Running Gurobi optimization... Please wait ⏳"):
        try:
            if "SC1F" in model_choice:
                results, model = run_SC1F(
                    CO_2_percentage=co2_pct,
                    product_weight=product_weight,
                    co2_cost_per_ton=co2_cost_per_ton,
                    print_results="NO",
                    suez_canal=suez_flag,
                    oil_crises=oil_flag,
                    volcano=volcano_flag,
                    trade_war=trade_flag,
                    tariff_rate=tariff_rate_used
                )
            else:
                results, model = run_SC2F(
                    CO_2_percentage=co2_pct,
                    product_weight=product_weight,
                    co2_cost_per_ton_New=co2_cost_per_ton_New,
                    print_results="NO",
                    suez_canal=suez_flag,
                    oil_crises=oil_flag,
                    volcano=volcano_flag,
                    trade_war=trade_flag,
                    tariff_rate=tariff_rate_used
                )


            st.success("Optimization completed successfully ✅")

            # Results
            st.subheader("💰 Objective Value")
            st.metric("Total Cost (€)", f"{results['Objective_value']:,.2f}")

            st.subheader("🌿 CO₂ Emissions Breakdown (tons)")
            st.json({
                "Air": round(results.get("E_air", 0), 2),
                "Sea": round(results.get("E_sea", 0), 2),
                "Road": round(results.get("E_road", 0), 2),
                "Last-mile": round(results.get("E_lastmile", 0), 2),
                "Production": round(results.get("E_production", 0), 2),
                "Total": round(results.get("CO2_Total", 0), 2),
            })
            
                        
            st.markdown("## 🌍 Global Supply Chain Map (with City Labels)")

            # Static locations with city names
            nodes = [
                # Plants
                ("Plant", 31.23, 121.47, "Shanghai"),
                ("Plant", 22.32, 114.17, "Hong Kong"),
            
                # Cross-docks
                ("Cross-dock", 48.85, 2.35, "Paris"),
                ("Cross-dock", 50.11, 8.68, "Frankfurt"),
                ("Cross-dock", 37.98, 23.73, "Athens"),
            
                # Distribution Centres
                ("Distribution Centre", 47.50, 19.04, "Budapest"),
                ("Distribution Centre", 48.14, 11.58, "Munich"),
                ("Distribution Centre", 46.95, 7.44, "Bern"),
                ("Distribution Centre", 45.46, 9.19, "Milan"),
            
                # Retailers
                ("Retailer Hub", 55.67, 12.57, "Copenhagen"),
                ("Retailer Hub", 53.35, -6.26, "Dublin"),
                ("Retailer Hub", 51.50, -0.12, "London"),
                ("Retailer Hub", 49.82, 19.08, "Krakow"),
                ("Retailer Hub", 45.76, 4.83, "Lyon"),
                ("Retailer Hub", 43.30, 5.37, "Marseille"),
                ("Retailer Hub", 40.42, -3.70, "Madrid"),
            ]
            
            # New facilities (only if active)
            facility_coords = {
                "HUDTG": (49.61, 6.13, "Luxembourg"),
                "CZMCT": (44.83, 20.42, "Belgrade"),
                "IEILG": (47.09, 16.37, "Graz"),
                "FIMPF": (50.45, 14.50, "Prague"),
                "PLZCA": (42.70, 12.65, "Viterbo"),
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
            
            # Convert to DataFrame if not empty
            if event_nodes:
                df_events = pd.DataFrame(event_nodes, columns=["Type", "Lat", "Lon", "City"])
                locations = pd.concat([locations, df_events], ignore_index=True)
                
                

            
            # Colors & sizes
            color_map = {
                "Plant": "purple",
                "Cross-dock": "dodgerblue",
                "Distribution Centre": "black",
                "Retailer Hub": "red",
                "New Production Facility": "deepskyblue",
            }
            
            color_map.update({
                    "Event: Suez Canal Blockade": "gold",
                    "Event: Volcano Eruption": "orange",
                    "Event: Oil Crisis": "brown",
                    "Event: Trade War": "green",
                })

            
            size_map = {
                "Plant": 15,
                "Cross-dock": 14,
                "Distribution Centre": 16,
                "Retailer Hub": 20,
                "New Production Facility": 14,
            }
            
            size_map.update({
                "Event: Suez Canal Blockade": 18,
                "Event: Volcano Eruption": 18,
                "Event: Oil Crisis": 18,
                "Event: Trade War": 18,
            })

            
            # Build map
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
            
            # marker style
            for trace in fig_map.data:
                trace.marker.update(
                    size=size_map.get(trace.name, 12),
                    opacity=0.9,
                    line=dict(width=0.5, color='white'),
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


                        
            
            
            # ================================================================
            # 🏭 PRODUCTION OUTBOUND PIE CHART (f1 + f2_2)
            # ================================================================
            st.markdown("## 🏭 Production Outbound Breakdown")
            
            # --- Total market demand reference ---
            TOTAL_MARKET_DEMAND = sum(results.get(k, 0) for k in [
                "Inventory_L1", "Inventory_L2", "Inventory_L2_new", "Inventory_L3"
            ])  # We override below for consistency
            
            # We use the fixed value from Scenario 2 (111k units) for consistency
            TOTAL_MARKET_DEMAND = 111000  
            
            # --- Gather flow variables ---
            f1_vars = [v for v in model.getVars() if v.VarName.startswith("f1[")]
            f2_2_vars = [v for v in model.getVars() if v.VarName.startswith("f2_2[")]
            
            # --- Summation per production source ---
            prod_sources = {}
            
            # Existing plants (f1)
            for plant in ["TW", "SHA"]:
                total = 0
                for var in f1_vars:
                    if var.VarName.startswith(f"f1[{plant},"):
                        total += var.X
                prod_sources[plant] = total
            
            # New European factories (f2_2)
            for fac in ["HUDTG", "CZMCT", "IEILG", "FIMPF", "PLZCA"]:
                total = 0
                for var in f2_2_vars:
                    if var.VarName.startswith(f"f2_2[{fac},"):
                        total += var.X
                prod_sources[fac] = total
            
            # --- Compute totals and unmet demand ---
            total_produced = sum(prod_sources.values())
            unmet = max(TOTAL_MARKET_DEMAND - total_produced, 0)
            
            # --- Convert to percentages ---
            labels = list(prod_sources.keys()) + ["Unmet Demand"]
            values = list(prod_sources.values()) + [unmet]
            
            df_prod = pd.DataFrame({
                "Source": labels,
                "Units Produced": values,
            })
            
            # --- Pie chart ---
            import plotly.express as px
            
            fig_prod = px.pie(
                df_prod,
                names="Source",
                values="Units Produced",
                hole=0.3,
                title="Production Share by Source",
            )
            
            # Colors — make Unmet Demand grey
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
            
            # --- Table version below chart ---
            st.markdown("#### 📦 Production Summary Table")
            st.dataframe(df_prod.round(2), use_container_width=True)

            

            # ================================================================
            # 🚚 CROSS-DOCK OUTBOUND PIE CHART (f2)
            # ================================================================
            st.markdown("## 🚚 Cross-dock Outbound Breakdown")
            
            # --- Total reference demand (same as before) ---
            TOTAL_MARKET_DEMAND = 111000
            
            # Gather f2 flow variables (Cross-dock → DC)
            f2_vars = [v for v in model.getVars() if v.VarName.startswith("f2[")]
            
            # Cross-docks in SC2
            crossdocks = ["ATVIE", "PLGDN", "FRCDG"]
            
            # Sum outbound flows for each cross-dock
            crossdock_flows = {}
            for cd in crossdocks:
                total = 0
                for var in f2_vars:
                    # Format: f2[ATVIE,FR6216,sea]
                    if var.VarName.startswith(f"f2[{cd},"):
                        total += var.X
                crossdock_flows[cd] = total
            
            total_outbound_cd = sum(crossdock_flows.values())
            
            if total_outbound_cd == 0:
                st.info("No cross-dock activity recorded for this scenario.")
            else:
                labels_cd = list(crossdock_flows.keys())
                values_cd = list(crossdock_flows.values())
            
                df_crossdock = pd.DataFrame({
                    "Crossdock": labels_cd,
                    "Shipped (units)": values_cd
                })
                df_crossdock["Share (%)"] = df_crossdock["Shipped (units)"] / df_crossdock["Shipped (units)"].sum() * 100
            
                # Pie chart
                import plotly.express as px
            
                fig_crossdock = px.pie(
                    df_crossdock,
                    names="Crossdock",
                    values="Shipped (units)",
                    hole=0.3,
                    title="Cross-dock Outbound Share",
                )
            
                # Color map
                color_map_cd = {
                    name: col for name, col in zip(
                        df_crossdock["Crossdock"],
                        px.colors.qualitative.Pastel
                    )
                }
            
                fig_crossdock.update_traces(
                    textinfo="label+percent",
                    textfont_size=13,
                    marker=dict(colors=[color_map_cd[s] for s in df_crossdock["Crossdock"]])
                )
                fig_crossdock.update_layout(
                    showlegend=True,
                    height=400,
                    template="plotly_white",
                    margin=dict(l=20, r=20, t=40, b=20)
                )
            
                st.plotly_chart(fig_crossdock, use_container_width=True)
            
                st.markdown("#### 🚚 Cross-dock Outbound Table")
                st.dataframe(df_crossdock.round(2), use_container_width=True)
            
            
            
            
            
            
            
            # ================================================================
            # 🚚 TRANSPORT FLOWS BY MODE (L1, L2, L2_2, L3)
            # ================================================================
            st.markdown("## 🚚 Transport Flows by Mode")
            
            import re
            
            def sum_flows_by_mode(model, prefix):
                """Calculate total air/sea/road flows for variables starting with prefix (f1, f2, f2_2, f3)."""
                totals = {"air": 0.0, "sea": 0.0, "road": 0.0}
            
                for var in model.getVars():
                    vname = var.VarName
                    if vname.startswith(prefix + "["):
                        # extract mode from final argument inside brackets
                        match = re.search(r",\s*([a-zA-Z]+)\]$", vname)
                        if match:
                            mode = match.group(1).lower()
                            if mode in totals:
                                try:
                                    totals[mode] += float(var.X)
                                except:
                                    pass
                return totals
            
            
            def display_layer(title, prefix, include_road=True):
                totals = sum_flows_by_mode(model, prefix)
                st.markdown(f"### {title}")
                cols = st.columns(3 if include_road else 2)
            
                cols[0].metric("🚢 Sea", f"{totals['sea']:,.0f} units")
                cols[1].metric("✈️ Air", f"{totals['air']:,.0f} units")
                if include_road:
                    cols[2].metric("🚛 Road", f"{totals['road']:,.0f} units")
            
                if sum(totals.values()) == 0:
                    st.info("No transport activity recorded for this layer.")
                st.markdown("---")
            
            
            # Display all layers
            display_layer("Layer 1: Plants → Cross-docks", "f1", include_road=False)
            display_layer("Layer 2a: Cross-docks → DCs", "f2", include_road=True)
            display_layer("Layer 2b: New Facilities → DCs", "f2_2", include_road=True)
            display_layer("Layer 3: DCs → Retailer Hubs", "f3", include_road=True)

            
            
            
            # ================================================================
            # 💰 COST DISTRIBUTION BAR CHART
            # ================================================================
            st.markdown("## 💰 Cost and 🌿 Emission Distribution")
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Cost Distribution")
            
                import plotly.express as px
                import pandas as pd
            
                transport_cost = (
                    results.get("Transport_L1", 0)
                    + results.get("Transport_L2", 0)
                    + results.get("Transport_L2_new", 0)
                    + results.get("Transport_L3", 0)
                )
            
                sourcing_handling_cost = (
                    results.get("Sourcing_L1", 0)
                    + results.get("Handling_L2_total", 0)
                    + results.get("Handling_L3", 0)
                )
            
                co2_cost_production = (
                    results.get("CO2_Manufacturing_State1", 0)
                    + results.get("CO2_Cost_L2_2", 0)
                )
            
                inventory_cost = (
                    results.get("Inventory_L1", 0)
                    + results.get("Inventory_L2", 0)
                    + results.get("Inventory_L2_new", 0)
                    + results.get("Inventory_L3", 0)
                )
            
                cost_parts = {
                    "Transportation Cost": transport_cost,
                    "Sourcing/Handling Cost": sourcing_handling_cost,
                    "CO₂ Cost in Production": co2_cost_production,
                    "Inventory Cost": inventory_cost,
                }
            
                df_cost_dist = pd.DataFrame({
                    "Category": list(cost_parts.keys()),
                    "Value": list(cost_parts.values())
                })
            
                fig_cost = px.bar(
                    df_cost_dist,
                    x="Category",
                    y="Value",
                    text="Value",
                    color="Category",
                    color_discrete_sequence=["#A7C7E7", "#B0B0B0", "#F8C471", "#5D6D7E"]
                )
            
                fig_cost.update_traces(
                    texttemplate="%{text:,.0f}",
                    textposition="outside"
                )
                fig_cost.update_layout(
                    template="plotly_white",
                    showlegend=False,
                    xaxis_tickangle=-35,
                    yaxis_title="€",
                    height=400,
                    yaxis_tickformat=","
                )
            
                st.plotly_chart(fig_cost, use_container_width=True)
                
            with col2:
                st.subheader("Emission Distribution")
            
                
                # Extract emission components
                E_air = results.get("E_air", 0)
                E_sea = results.get("E_sea", 0)
                E_road = results.get("E_road", 0)
                E_lastmile = results.get("E_lastmile", 0)
                E_production = results.get("E_production", 0)
            
                total_transport = E_air + E_sea + E_road
            
                emission_data = {
                    "Production": E_production,
                    "Last-mile": E_lastmile,
                    "Air": E_air,
                    "Sea": E_sea,
                    "Road": E_road,
                    "Total Transport": total_transport,
                }
            
                df_emission = pd.DataFrame({
                    "Source": list(emission_data.keys()),
                    "Emission (tons)": list(emission_data.values())
                })
            
                fig_emission = px.bar(
                    df_emission,
                    x="Source",
                    y="Emission (tons)",
                    text="Emission (tons)",
                    color="Source",
                    color_discrete_sequence=[
                        "#4B8A08", "#2E8B57", "#808080",
                        "#FFD700", "#90EE90", "#000000"
                    ]
                )
            
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
                    yaxis_tickformat=","
                )
            
                st.plotly_chart(fig_emission, use_container_width=True)





        except gp.GurobiError as ge:
            st.error(f"Gurobi Error {ge.errno}: {ge.message}")
        except Exception as e:
            st.error(f"❌ This solution was never feasible — even Swiss precision couldn't optimize it! 🇨🇭\n\n{e}")
