# -*- coding: utf-8 -*-
"""
Streamlit Dashboard – Simplified Supply Chain Model (SC1F)
Author: Arda Aydın
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import re
import sys
from pathlib import Path
import streamlit.components.v1 as components



# ----------------------------------------------------
# GA TRACKING SHOULD BE HERE
# ----------------------------------------------------
GA_MEASUREMENT_ID = "G-3H3B3BNF4Z"

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
# 🌐 CACHED DATA LOADERS 
# ----------------------------------------------------
@st.cache_data(show_spinner="Loading Parquet data...")
def load_parquet_folder(folder: str):
    """Load one Parquet file per sheet into the same shape as read_excel(sheet_name=None)."""
    parquet_dir = Path(folder)
    return {
        p.stem.replace("pct", "%"): pd.read_parquet(p)
        for p in sorted(parquet_dir.glob("*.parquet"))
    }


def format_number(value, x):
    """Format numbers with thousand separators and max two decimals."""
    try:
        return f"{float(value):,.{x}f}"
    except (ValueError, TypeError):
        return value




# ----------------------------------------------------
# ⚠️ BIG WARNING POP-UP (UNSATISFIED DEMAND)
# ----------------------------------------------------
def _safe_float(x, default=0.0):
    """Robust float conversion (handles NaN, strings with comma decimals, and %)."""
    try:
        if x is None:
            return default
        # pandas NaN
        if isinstance(x, float) and pd.isna(x):
            return default
        if isinstance(x, str):
            s = x.strip().replace("%", "")
            s = s.replace(",", ".")
            if s == "":
                return default
            return float(s)
        return float(x)
    except Exception:
        return default


def _safe_bool(x, default=False):
    """Robust bool conversion (handles True/False, 0/1, and common strings)."""
    if isinstance(x, bool):
        return x
    if x is None:
        return default
    if isinstance(x, float) and pd.isna(x):
        return default
    if isinstance(x, (int, float)):
        return bool(x)
    if isinstance(x, str):
        s = x.strip().lower()
        if s in ("true", "t", "yes", "y", "1"):
            return True
        if s in ("false", "f", "no", "n", "0", ""):
            return False
    return default


def _js_escape(s: str) -> str:
    """Escape text for safe insertion into a JS template literal."""
    s = str(s)
    return (
        s.replace("\\", "\\\\")
         .replace("`", "\\`")
         .replace("${", "\\${")
         .replace("\n", "<br>")
    )


def inject_big_warning_popup(title: str, lines):
    """Create a big, screen-blocking warning overlay in the Streamlit parent document."""
    popup_id = "tge_big_warning_overlay"
    title_js = _js_escape(title)
    body_js = _js_escape("<br>".join(lines))

    components.html(
        f"""
<script>
(function() {{
  const doc = window.parent.document;

  // Remove previous overlay (if any) to avoid stacking
  const old = doc.getElementById("{popup_id}");
  if (old) old.remove();

  const overlay = doc.createElement("div");
  overlay.id = "{popup_id}";
  overlay.style.position = "fixed";
  overlay.style.left = "0";
  overlay.style.top = "0";
  overlay.style.width = "100%";
  overlay.style.height = "100%";
  overlay.style.background = "rgba(0,0,0,0.70)";
  overlay.style.zIndex = "999999";
  overlay.style.display = "flex";
  overlay.style.alignItems = "flex-start";
  overlay.style.justifyContent = "center";
  overlay.style.padding = "6vh 16px";

  overlay.innerHTML = `
    <div style="
      width: min(980px, 100%);
      background: #ffffff;
      border-radius: 22px;
      border: 8px solid #b71c1c;
      box-shadow: 0 25px 90px rgba(0,0,0,0.55);
      padding: 28px 28px 22px 28px;
      font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
    ">
      <div style="display:flex; justify-content:space-between; gap:16px; align-items:flex-start;">
        <div>
          <div style="font-size: 32px; font-weight: 900; color:#b71c1c; line-height: 1.1;">
            ⚠️ ${title_js}
          </div>
          <div style="margin-top: 14px; font-size: 18px; color:#111; line-height: 1.55;">
            ${body_js}
          </div>
        </div>
        <button id="{popup_id}_close" style="
          border: 0;
          background: #b71c1c;
          color: #fff;
          font-size: 18px;
          font-weight: 800;
          padding: 10px 14px;
          border-radius: 12px;
          cursor: pointer;
        ">Close ✕</button>
      </div>
      <div style="margin-top: 18px; font-size: 14px; color:#444;">
        Visualizations below still show the closest scenario. This warning appears when the scenario cannot satisfy total demand.
      </div>
    </div>
  `;

  doc.body.appendChild(overlay);

  doc.getElementById("{popup_id}_close").onclick = () => overlay.remove();
  overlay.onclick = (e) => {{ if (e.target === overlay) overlay.remove(); }};
}})();
</script>
""",
        height=0,
    )

def resolve_local_path(*parts: str) -> str:
    """
    Dev ortamında ve PyInstaller içinde çalışan, data dosyası bulucu.
    """
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    candidates = [
        base.joinpath(*parts),                 # _MEIPASS/single_page/...
        base.joinpath("app", *parts),          # _MEIPASS/app/single_page/...  (optimize;app kullandıysan)
        Path(__file__).resolve().parent.joinpath(*parts),
        Path(__file__).resolve().parent.joinpath("single_page", *parts),
        Path.cwd().joinpath(*parts),
        Path.cwd().joinpath("single_page", *parts),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return str(candidates[0])

def run_sc1():
    # # ----------------------------------------------------
    # # CONFIGURATION
    # # ----------------------------------------------------
    # st.set_page_config(
    #     page_title="Service Speed vs. Emission Reductions",
    #     layout="wide",
    #     initial_sidebar_state="expanded"
    # )
    
    st.title("🏭 Scenario 1: Process Optimization")
    
    
    
    LOCAL_PARQUET_DIR = resolve_local_path("parquet", "sc1")

    try:
        parquet_dir = Path(LOCAL_PARQUET_DIR)
        if not parquet_dir.exists():
            st.error(f"❌ Parquet data directory not found: {parquet_dir}")
            st.stop()
        excel_data = load_parquet_folder(str(parquet_dir))
        sheet_names = [s for s in excel_data.keys() if s.startswith("Array_")]
        if not sheet_names:
            st.error("❌ No Array_* sheets found in parquet directory.")
            st.stop()

    except Exception as e:
        st.error(f"❌ Failed to load parquet data: {e}")
        st.stop()
    
    # ----------------------------------------------------
    # SIDEBAR CONTROLS (SC2-style layout)
    # ----------------------------------------------------
    # st.sidebar.header("📦 Demand Level (%)")

    # Extract numeric levels automatically (e.g., Array_90% → 90)
    levels = sorted(
        [int(re.findall(r"\d+", name)[0]) for name in sheet_names],
        reverse=True
    )
    level_labels = [f"{lvl}%" for lvl in levels]

    # Demand-level UI intentionally hidden; always default to the 100% sheet.
    selected_level_label = next((label for label in level_labels if str(label).strip() == "100%"), None)
    if selected_level_label is None:
        selected_level_label = next((label for label in level_labels if "100" in str(label)), None)
    if selected_level_label is None:
        selected_level_label = level_labels[0] if level_labels else "100%"
    selected_level = int(str(selected_level_label).replace("%", "").strip())

    selected_sheet = f"Array_{selected_level}%"

    # ----------------------------------------------------
    # FILTER PARAMETERS (SC2-style layout)
    # ----------------------------------------------------
    st.sidebar.header("🎛️ Filter Parameters")
    SHOW_SERVICE_LEVEL_FILTER = False
    
    
    # Load selected sheet
    df = excel_data[selected_sheet].round(2)
    if isinstance(df, pd.Series):
        df = df.to_frame().T
    elif not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    
    # ----------------------------------------------------
    # OPTIONAL FILTERS
    # ----------------------------------------------------
    with st.sidebar.form("sc1_filter_search_form"):
        if "Product_weight" in df.columns:
            weight_selected = st.selectbox(
                "Product Weight (kg)",
                sorted(df["Product_weight"].unique())
            )
            subset = df[df["Product_weight"] == weight_selected]
        else:
            subset = df.copy()
        
        if "Unit_penaltycost" in subset.columns:
            penalty_selected = st.select_slider(
                "Penalty Cost (€/unit)",
                options=sorted(subset["Unit_penaltycost"].unique()),
                value=subset["Unit_penaltycost"].iloc[0]
            )
            subset = subset[subset["Unit_penaltycost"] == penalty_selected]
    
        # ----------------------------------------------------
        # SERVICE LEVEL FILTER (SC1)
        # ----------------------------------------------------
        service_col = None
        if "Service_Level" in subset.columns:
            service_col = "Service_Level"
        elif "Service Level" in subset.columns:
            service_col = "Service Level"
    
        if SHOW_SERVICE_LEVEL_FILTER and service_col and not subset.empty:
            subset[service_col] = subset[service_col].astype(float)
            selected_service_level = st.slider(
                "Service Level",
                min_value=float(subset[service_col].min()),
                max_value=float(subset[service_col].max()),
                step=0.1,
                value=float(subset[service_col].max()),
            )
            subset = subset[subset[service_col] == selected_service_level]
    
        
        # ----------------------------------------------------
        # DETECT CO₂ REDUCTION COLUMN AUTOMATICALLY
        # ----------------------------------------------------
        possible_co2_cols = [
            c for c in subset.columns
            if "co2" in c.lower() and any(x in c.lower() for x in ["%", "reduction", "percent", "perc"])
        ]
        
        if possible_co2_cols:
            co2_col = possible_co2_cols[0]
        else:
            st.error(
                "❌ Could not find any CO₂-related percentage column. "
                "Make sure one of the columns includes terms like 'CO2', 'Reduction', or '%'."
            )
            st.stop()
        
        # Create slider for CO2 Reduction %
        # Create slider for CO₂ Reduction %
        # ----------------------------------------------------
        # CO₂ REDUCTION SLIDER (0–100% visual, internal 0–1)
        # ----------------------------------------------------
        default_val = float(subset[co2_col].mean()) if co2_col in subset.columns else 0.25
        
        # ✅ Always start from 0% CO₂ reduction
        default_val = 0.0  # (fractional form, 0.0 = 0%)
        
        co2_pct_display = st.slider(
            "Emission Reduction Target (%)",
            min_value=0,
            max_value=100,
            value=int(default_val * 100),  # ✅ default = 0%
            step=1,
            help="Set a Emission Reduction Target between 0–100 %.",
        )
        st.form_submit_button("Search")
    
    # Convert displayed percentage back to 0–1 for internal matching
    co2_pct = co2_pct_display / 100.0
    
    # ----------------------------------------------------
    # FIND CLOSEST SCENARIO (no hard stop)
    # ----------------------------------------------------
    idx = (subset[co2_col] - co2_pct).abs().argmin()
    closest = subset.iloc[idx]

    # If no exact match, inform user but keep going (do NOT stop visuals)
    if (subset[co2_col] - co2_pct).abs().min() >= 1e-6:
        closest_val = _safe_float_local(closest.get(co2_col, co2_pct), co2_pct)
        st.sidebar.warning(
            f"⚠️ No exact match for CO₂e target {co2_pct_display}%. Showing closest scenario at {closest_val*100:.0f}%."
        )

        # ----------------------------------------------------
    # 🚨 DEMAND SATISFACTION CHECK (NO POP-UP)
    #   Note: UNS metrics live in Demand_* sheets (not Array_* sheets).
    # ----------------------------------------------------
    # Initialize to avoid UnboundLocalError in every branch
    used_uns = False
    satisfied_units = None
    satisfied_pct = None
    unmet_units = None
    total_demand_units = 111000.0 * (selected_level / 100.0)

    # Prefer Demand_* sheet for UNS metrics (Array_* does not contain them)
    demand_sheet = f"Demand_{selected_level}%"
    df_demand_uns = excel_data.get(demand_sheet)

    closest_idx = None
    try:
        closest_idx = int(closest.name) if closest.name is not None else None
    except Exception:
        closest_idx = None

    closest_demand_uns = None
    if df_demand_uns is not None and closest_idx is not None and 0 <= closest_idx < len(df_demand_uns):
        closest_demand_uns = df_demand_uns.iloc[closest_idx]

    row_for_uns = closest_demand_uns if closest_demand_uns is not None else closest

    # Robust to leading/trailing spaces in Excel headers
    _canon = lambda s: str(s).strip()
    available_cols = set(_canon(c) for c in row_for_uns.index)
    has_uns_metrics = any(
        col in available_cols
        for col in (
            "Used_UNS_Fallback",
            "Satisfied_Demand_units",
            "Satisfied_Demand_pct",
            "Unmet_Demand_units",
        )
    )

    if has_uns_metrics:
        used_uns = _safe_bool(row_for_uns.get("Used_UNS_Fallback", False), False)
        satisfied_units = _safe_float(row_for_uns.get("Satisfied_Demand_units", None), None)
        satisfied_pct = _safe_float(row_for_uns.get("Satisfied_Demand_pct", None), None)
        unmet_units = _safe_float(row_for_uns.get("Unmet_Demand_units", None), None)

        if satisfied_units is None and satisfied_pct is not None:
            satisfied_units = total_demand_units * max(0.0, min(1.0, satisfied_pct))
        if satisfied_pct is None and satisfied_units is not None and total_demand_units > 0:
            satisfied_pct = satisfied_units / total_demand_units
        if unmet_units is None and satisfied_units is not None:
            unmet_units = max(total_demand_units - satisfied_units, 0.0)
        if satisfied_units is None and unmet_units is not None:
            satisfied_units = max(total_demand_units - unmet_units, 0.0)

        if satisfied_pct is None:
            satisfied_pct = 1.0
        if satisfied_units is None:
            satisfied_units = total_demand_units
        if unmet_units is None:
            unmet_units = max(total_demand_units - satisfied_units, 0.0)

        # Only show a single, clean message (no pop-up)
        if used_uns or unmet_units > 1e-6 or satisfied_pct < 0.999999:
            sat_pct_disp = max(0.0, min(1.0, satisfied_pct)) * 100.0
            st.error(
                f"⚠️ Capacity is insufficient; only {sat_pct_disp:.2f}% satisfied on average. You’re losing market share!"
            )
            """
            st.error(
                f"⚠️ Demand NOT fully satisfied: {satisfied_units:,.0f}/{total_demand_units:,.0f} units "
                f""
            )
            """
    else:
        # Do not block visuals; just inform once
        """st.warning(
            "⚠️ Demand satisfaction metrics are not available in this Excel output for the selected scenario. "
            "Please regenerate/upload results that include UNS metrics. "
            "No demand satisfaction columns were found for the selected scenario."
        )"""

# ----------------------------------------------------
    # KPI SUMMARY
    # ----------------------------------------------------
    CLOSEST_SCENARIO_DETAILS = False  # Set to False to hide the closest scenario details section
    if CLOSEST_SCENARIO_DETAILS:
        st.subheader("📊 Closest Scenario Details")
        
        closest_df = closest.to_frame().T  # transpose for row→column view
        
        # Remove columns starting with 'f'
        cols_to_show = [c for c in closest_df.columns if not c.lower().startswith("f")]
    
        # Display cleaned table
        st.write(closest_df[cols_to_show])
    
    col1, col2, col3, col4 = st.columns(4)
    
    col1.metric(
        "Total Cost (€)",
        f"{(closest['Total Cost'] if 'Total Cost' in closest else closest.get('Objective_value', 0)):,.0f}"
    )
    col2.metric(
        "Total CO₂e (tons)",
        f"{(closest['Total Emissions'] if 'Total Emissions' in closest else closest.get('CO2_Total', 0)):,.2f}"
    )
    
    # ---------- totals with smart fallbacks ----------
    # Inventory
    inv_layer_cols = [c for c in ["Inventory_L1", "Inventory_L2", "Inventory_L3"] if c in closest.index]
    if inv_layer_cols:
        inv_total = float(closest[inv_layer_cols].sum())
    elif "Transit Inventory Cost" in closest.index:
        inv_total = float(closest["Transit Inventory Cost"])
    else:
        inv_total = None
    
    # Transport
    tr_layer_cols = [c for c in ["Transport_L1", "Transport_L2", "Transport_L3"] if c in closest.index]
    if tr_layer_cols:
        tr_total = float(closest[tr_layer_cols].sum()) + (6.25 * float(closest.get("Satisfied_Demand_units", closest.get("DemandFulfillment", 0))))
    elif "Transportation Cost" in closest.index:
        tr_total = float(closest["Transportation Cost"]) + (6.25 * float(closest.get("Satisfied_Demand_units", closest.get("DemandFulfillment", 0))))
    else:
        tr_total = None
    
    col3.metric("Inventory Total (€)", f"{inv_total:,.0f}" if inv_total is not None else "N/A")
    col4.metric("Transport Total (€)", f"{tr_total:,.0f}" if tr_total is not None else "N/A")

    # ----------------------------------------------------
    # 🆕 COST vs EMISSIONS DUAL-AXIS BAR-LINE PLOT (DYNAMIC)
    # ----------------------------------------------------
    st.markdown("## 💶 Emissions vs Total Cost ")
    
    @st.cache_data(show_spinner=False)
    def generate_cost_emission_chart_plotly_dynamic(df_sheet: pd.DataFrame, selected_value: float):
        # Detect column names
        emissions_col = "Total Emissions" if "Total Emissions" in df_sheet.columns else "CO2_Total"
        cost_col = "Total Cost" if "Total Cost" in df_sheet.columns else "Objective_value"
        co2_col = next((c for c in df_sheet.columns if "reduction" in c.lower() or "%" in c.lower()), None)
        

        df_chart = df_sheet[[emissions_col, cost_col, co2_col]].copy().sort_values(by=co2_col)
        df_chart["Emissions (k)"] = df_chart[emissions_col] / 1000
        df_chart["Cost (M)"] = df_chart[cost_col] / 1_000_000
    
        import plotly.graph_objects as go
        fig = go.Figure()
    
        # Grey bars: emissions
        fig.add_trace(go.Bar(
            x=df_chart[co2_col],
            y=df_chart["Emissions (k)"],
            name="Emissions (thousand)",
            marker_color="dimgray",
            opacity=0.9,
            yaxis="y1"
        ))
    
        # Red dotted line: cost
        fig.add_trace(go.Scatter(
            x=df_chart[co2_col],
            y=df_chart["Cost (M)"],
            name="Total Cost (million €)",
            mode="lines+markers",
            line=dict(color="red", width=2, dash="dot"),
            marker=dict(size=6, color="red"),
            yaxis="y2"
        ))
    
        # Highlight the selected scenario
        if selected_value is not None and selected_value in df_chart[co2_col].values:
            highlight_row = df_chart.loc[df_chart[co2_col] == selected_value].iloc[0]
            fig.add_trace(go.Scatter(
                x=[highlight_row[co2_col]],
                y=[highlight_row["Cost (M)"]],
                mode="markers+text",
                marker=dict(size=14, color="red", symbol="circle"),
                text=[f"{highlight_row[co2_col]:.2%}"],
                textposition="top center",
                name="Selected Scenario",
                yaxis="y2"
            ))
    
        # Layout and style
        fig.update_layout(
            template="plotly_white",
            title=dict(text="<b>Cost vs. Emissions</b>", x=0.45, font=dict(color="firebrick", size=20)),
            xaxis=dict(
                title="CO₂e Reduction (%)",
                tickformat=".0%",
                showgrid=False
            ),
            yaxis=dict(title="Emissions (thousand)", side="left", showgrid=False),
            yaxis2=dict(title="Cost (million €)", overlaying="y", side="right", showgrid=False),
            legend=dict(orientation="h", y=-0.25, x=0.3),
            margin=dict(l=40, r=40, t=60, b=60),
            height=450
        )
    
        return fig
    
    fig_cost_emission = generate_cost_emission_chart_plotly_dynamic(df, closest[co2_col])
    st.plotly_chart(fig_cost_emission, use_container_width=True)


    
    # ----------------------------------------------------
    # COST vs EMISSION PLOT
    # ----------------------------------------------------
    st.markdown("## 📈 Emissions vs Cost Elements ")
    
    cost_metric_map = {
        "Total Cost (€)": "Objective_value" if "Objective_value" in df.columns else "Total Cost",
        "Inventory Cost (€)": (
            ["Inventory_L1", "Inventory_L2", "Inventory_L3"]
            if any(c in df.columns for c in ["Inventory_L1", "Inventory_L2", "Inventory_L3"])
            else ["Transit Inventory Cost"]
        ),
        "Transport Cost (€)": (
            ["Transport_L1", "Transport_L2", "Transport_L3"]
            if any(c in df.columns for c in ["Transport_L1", "Transport_L2", "Transport_L3"])
            else ["Transportation Cost"]
        ),
    }
    
    selected_metric_label = st.selectbox(
        "Select Cost Metric to Plot:",
        list(cost_metric_map.keys()),
        index=0
    )
    
    filtered = subset.copy()
    
    # Compute selected cost robustly
    metric_cols = cost_metric_map[selected_metric_label]
    if isinstance(metric_cols, list):
        cols_to_sum = [c for c in metric_cols if c in filtered.columns]
        if cols_to_sum:
            filtered["Selected_Cost"] = filtered[cols_to_sum].sum(axis=1)
            if selected_metric_label.startswith("Transport Cost"):
                filtered["Selected_Cost"] += 6.25 * pd.to_numeric(
                    filtered["Satisfied_Demand_units"] if "Satisfied_Demand_units" in filtered.columns else filtered["DemandFulfillment"],
                    errors="coerce"
                ).fillna(0)
        else:
            st.warning(f"⚠️ Could not find any columns for {selected_metric_label}.")
            st.stop()
    else:
        filtered["Selected_Cost"] = filtered[metric_cols]
    
    x_col = "Total Emissions" if "Total Emissions" in filtered.columns else "CO2_Total"
    filtered["CO2 Reduction % Display"] = pd.to_numeric(filtered[co2_col], errors="coerce") * 100
    
    # --- Build Plotly chart ---
    fig = px.scatter(
        filtered,
        x=x_col,
        y="Selected_Cost",
        color="CO2 Reduction % Display",
        template="plotly_white",
        color_continuous_scale="Viridis",
        labels={"CO2 Reduction % Display": "CO₂e Reduction %"},
        title=f"{selected_metric_label} vs CO₂e Emissions ",
    )
    fig.update_coloraxes(colorbar=dict(ticksuffix="%"))
    
    # Safely find the point for the selected scenario
    if "Selected_Cost" in closest.index:
        closest_y = closest["Selected_Cost"]
    else:
        if isinstance(metric_cols, list):
            cols_to_sum = [c for c in metric_cols if c in closest.index]
            closest_y = closest[cols_to_sum].sum()
            if selected_metric_label.startswith("Transport Cost"):
                closest_y += 6.25 * float(closest.get("Satisfied_Demand_units", closest.get("DemandFulfillment", 0)))
        else:
            closest_y = closest.get(metric_cols, 0)
    
    fig.add_scatter(
        x=[closest[x_col]],
        y=[closest_y],
        mode="markers+text",
        marker=dict(size=14, color="red"),
        text=["Selected Scenario"],
        textposition="top center",
        name="Selected"
    )
    
    
    # --- Display chart ---
    st.plotly_chart(fig, use_container_width=True)
    
    # --- Read the corresponding detailed (Demand_*) sheet row for dependent charts ---
    demand_sheet = f"Demand_{selected_level}%"
    df_demand = excel_data.get(demand_sheet)
    closest_idx = int(closest.name) if closest.name is not None else None
    closest_demand = None
    if df_demand is not None and closest_idx is not None:
        if 0 <= closest_idx < len(df_demand):
            closest_demand = df_demand.iloc[closest_idx]

    # ----------------------------------------------------
    # 💰🌿 COST & EMISSION DISTRIBUTION SECTION
    # ----------------------------------------------------
    st.markdown("## 💰 Cost and 🌿 Emission Distribution")
    
    colB, colC = st.columns(2)
    
    # --- 2️⃣ Cost Distribution ---
    with colB:
        st.subheader("Cost Distribution")
    
        cost_components = {
            "Transportation Cost": closest.get("Transportation Cost", 0) + (6.25 * float(closest.get("Satisfied_Demand_units", closest.get("DemandFulfillment", 0)))),
            "Sourcing/Handling Cost": closest.get("Sourcing/Handling Cost", 0),
            "Carbon Cost in Production": closest.get("CO2 Cost in Production", 0),
            "Inventory Cost": closest.get("Transit Inventory Cost", 0),
        }
    
        df_cost_dist = pd.DataFrame({
            "Category": list(cost_components.keys()),
            "Value": list(cost_components.values())
        })
        df_cost_dist["Value_MEUR"] = pd.to_numeric(df_cost_dist["Value"], errors="coerce") / 1_000_000.0
    
        fig_cost_dist = px.bar(
            df_cost_dist,
            x="Category",
            y="Value_MEUR",
            text="Value_MEUR",
            color="Category",
            color_discrete_sequence=["#A7C7E7", "#B0B0B0", "#F8C471", "#5D6D7E"],
        )
    
        fig_cost_dist.update_traces(
            texttemplate="%{text:.2f} M€",
            textposition="outside"
        )
        fig_cost_dist.update_layout(
            template="plotly_white",
            showlegend=False,
            xaxis_tickangle=-35,
            yaxis_title="Million €",
            height=400,
            yaxis_tickformat=".2f"
        )
    
        st.plotly_chart(fig_cost_dist, use_container_width=True)
    
    # --- 3️⃣ Emission Distribution ---
    with colC:
        st.subheader("Emission Distribution")

        emission_aliases = {
            "Production": ["E_Production", "E(Production)", "E_production"],
            "Last-mile": ["E_Last-mile", "E(Last-mile)", "E_lastmile", "E_last-mile", "E_LastMile", "E(LastMile)"],
            "Air": ["E_Air", "E(Air)", "E_air"],
            "Water": ["E_Water", "E(Water)", "E_water", "E(water)", "E_Sea", "E(Sea)", "E_sea", "E(sea)"],
            "Road": ["E_Road", "E(Road)", "E_road"],
        }

        def _pick_emission(row, keys):
            for k in keys:
                if row is not None and hasattr(row, 'index') and k in row.index:
                    v = row.get(k, 0)
                    try:
                        return float(v)
                    except Exception:
                        try:
                            return float(str(v).replace(',', '.'))
                        except Exception:
                            return 0.0
            return 0.0

        row_for_emissions = closest
        has_any = any(any(k in row_for_emissions.index for k in ks) for ks in emission_aliases.values())
        if (not has_any) and (closest_demand is not None):
            row_for_emissions = closest_demand

        emission_data = {
            name: _pick_emission(row_for_emissions, keys)
            for name, keys in emission_aliases.items()
        }

        emission_data["Total Transport"] = (
            emission_data.get("Air", 0) + emission_data.get("Water", 0) + emission_data.get("Road", 0)
        )

        if sum(emission_data.values()) == 0:
            st.info("No emission data recorded for this scenario.")
        else:
            df_emission_dist = pd.DataFrame({
                "Source": list(emission_data.keys()),
                "Emissions": list(emission_data.values())
            })

            fig_emission_dist = px.bar(
                df_emission_dist,
                x="Source",
                y="Emissions",
                text="Emissions",
                color="Source",
                color_discrete_sequence=[
                    "#1C7C54", "#17A2B8", "#808080", "#FFD700", "#4682B4", "#000000"
                ]
            )

            fig_emission_dist.update_traces(
                texttemplate="%{text:,.2f}",
                textposition="outside"
            )
            fig_emission_dist.update_layout(
                template="plotly_white",
                showlegend=False,
                xaxis_tickangle=-35,
                yaxis_title="Tons of CO₂",
                height=400,
                yaxis_tickformat=","
            )

            st.plotly_chart(fig_emission_dist, use_container_width=True)


    
    # ----------------------------------------------------
    # 🏭 PRODUCTION OUTBOUND PIE CHART (f1 only)
    # ----------------------------------------------------
    st.markdown("## 🏭 Production Sourcing Breakdown")

    # --- Helper: safe float conversion ---
    def _safe_float_local(x):
        try:
            if pd.isna(x):
                return 0.0
            return float(x)
        except Exception:
            try:
                return float(str(x).replace(",", "."))
            except Exception:
                return 0.0

    # --- Total demand reference (scale by demand level) ---
    BASE_MARKET_DEMAND = 111000  # units at 100%
    demand_factor = (
        _safe_float_local(closest_demand.get("Demand_Level"))
        if closest_demand is not None and "Demand_Level" in closest_demand.index
        else (selected_level / 100.0)
    )
    TOTAL_MARKET_DEMAND = BASE_MARKET_DEMAND * demand_factor

    # --- Aggregate production from each plant (prefer summary columns; fallback to detailed f1[*] flows) ---
    prod_sources = {}
    for plant in ["Taiwan", "Shanghai"]:
        summary_col = f"{plant} Sourcing"
        if summary_col in closest.index:
            prod_sources[plant] = _safe_float_local(closest.get(summary_col))
        elif closest_demand is not None:
            f1_cols = [c for c in df_demand.columns if c.startswith(f"f1[{plant},")]
            prod_sources[plant] = sum(_safe_float_local(closest_demand.get(c)) for c in f1_cols)
        else:
            prod_sources[plant] = 0.0
    
    # --- Calculate unmet demand ---
    total_produced = sum(prod_sources.values())
    unmet = max(TOTAL_MARKET_DEMAND - total_produced, 0)
    
    # --- Prepare dataframe ---
    labels = list(prod_sources.keys()) + ["Unmet Demand"]
    values = [prod_sources[k] for k in prod_sources] + [unmet]
    denom = TOTAL_MARKET_DEMAND if TOTAL_MARKET_DEMAND else 1.0
    percentages = [v / denom * 100 for v in values]
    
    df_prod = pd.DataFrame({
        "Source": labels,
        "Produced (units)": values,
        "Share (%)": percentages
    })
    
    # --- Build pie chart (with grey unmet slice) ---
    fig_prod = px.pie(
        df_prod,
        names="Source",
        values="Produced (units)",
        hole=0.3,
        title=f"Production Share by Source",
    )
    
    # --- Color configuration ---
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
        st.markdown("#### 📦 Production Sourcing")
        st.dataframe(
            df_prod.round(2),
            hide_index=True,
            column_config={
                "Produced (units)": st.column_config.NumberColumn(format="%.2f"),
                "Share (%)": st.column_config.NumberColumn(format="%.2f"),
            },
            use_container_width=True,
        )
    
    with colC:
        st.markdown("#### 🌿 CO₂e Factors (kg CO₂e/unit)")
        co2_factors_mfg = pd.DataFrame({
            "From mfg": ["Taiwan", "Shanghai"],
            "CO₂ kg/unit": [6.3, 9.8]
        })
        co2_factors_mfg["CO₂ kg/unit"] = co2_factors_mfg["CO₂ kg/unit"].map(lambda v: f"{v:.2f}")
        st.dataframe(co2_factors_mfg, hide_index=True, use_container_width=True)
    
    
    # ----------------------------------------------------
    # 🚚 CROSSDOCK OUTBOUND PIE CHART (f2 only)
    # ----------------------------------------------------
    st.markdown("## 🚚 Crossdock Outbound Breakdown")

    # --- Crossdocks in SC1F ---
    crossdocks = ["Vienna", "Gdansk", "Paris"]

    # NOTE: Array_* sheets do not contain f2[*] variables. Use the aligned Demand_* sheet for crossdock flows.
    crossdock_flows = {}
    if closest_demand is not None:
        for cd in crossdocks:
            f2_cols = [c for c in df_demand.columns if c.startswith(f"f2[{cd},")]
            crossdock_flows[cd] = sum(_safe_float_local(closest_demand.get(c)) for c in f2_cols)
    else:
        for cd in crossdocks:
            crossdock_flows[cd] = 0.0
    
    # --- Compute total handled shipments (no unmet here) ---
    total_outbound_cd = sum(crossdock_flows.values())
    
    if total_outbound_cd == 0:
        st.info("No crossdock activity recorded for this scenario.")
    else:
        labels_cd = list(crossdock_flows.keys())
        values_cd = [crossdock_flows[k] for k in crossdock_flows]
        percentages_cd = [v / total_outbound_cd * 100 for v in values_cd]
    
        df_crossdock = pd.DataFrame({
            "Crossdock": labels_cd,
            "Shipped (units)": values_cd,
            "Share (%)": percentages_cd
        })
    
        fig_crossdock = px.pie(
            df_crossdock,
            names="Crossdock",
            values="Shipped (units)",
            hole=0.3,
            title=f"Crossdock Outbound Share",
        )
    
        color_map_cd = {name: color for name, color in zip(df_crossdock["Crossdock"], px.colors.qualitative.Pastel)}
    
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
    
        colC, colD = st.columns([2, 1])
        with colC:
            st.plotly_chart(fig_crossdock, use_container_width=True)
        with colD:
            st.dataframe(
                df_crossdock.round(2),
                hide_index=True,
                column_config={
                    "Shipped (units)": st.column_config.NumberColumn(format="%.2f"),
                    "Share (%)": st.column_config.NumberColumn(format="%.2f"),
                },
                use_container_width=True,
            )
    
    
    
    # ----------------------------------------------------
    # 🌍 SUPPLY CHAIN MAP
    # ----------------------------------------------------
    st.markdown("## 🌍 Global Supply Chain Network")
    
    plants = pd.DataFrame({
    "Type": ["Plant", "Plant"],
    "Lat": [31.230416, 23.553100],
    "Lon": [121.473701, 121.021100]
    })

    crossdocks = pd.DataFrame({
        "Type": ["Cross-dock"] * 3,
        "Lat": [48.856610, 54.352100, 48.208500],
        "Lon": [2.352220, 18.646400, 16.372100]
    })

    dcs = pd.DataFrame({
        "Type": ["Distribution Center"] * 4,
        "Lat": [50.040750, 50.629250, 56.946285, 36.168056],
        "Lon": [15.776590, 3.057256, 24.105078, -5.348611]
    })

    retailers = pd.DataFrame({
        "Type": ["Retailer Hub"] * 7,
        "Lat": [50.935173, 51.219890, 50.061430, 54.902720, 59.911491, 53.350140, 59.329440],
        "Lon": [6.953101, 4.403460, 19.936580, 23.909610, 10.757933, -6.266155, 18.068610]
    })

    
    locations = pd.concat([plants, crossdocks, dcs, retailers])
    color_map = {
        "Manufacturers": "#8E24AA",                        # Plant – mor
        "Cross-dock": "#4285F4",                           # Cross-dock – mavi
        "DC": "#000000",                                   # Distribution Center – siyah
        "Retail": "#EA4335",                               # Retailer Hub – kırmızı
    }
    
    fig_map = px.scatter_geo(
        locations,
        lat="Lat",
        lon="Lon",
        color="Type",
        color_discrete_map=color_map,
        projection="natural earth",
        scope="world",
        title="Global Supply Chain Structure",
        template="plotly_white"
    )
    
    for trace in fig_map.data:
        trace.marker.update(size=14, line=dict(width=0.5, color='white'))
    
    fig_map.update_geos(
        showcountries=True,
        countrycolor="lightgray",
        showland=True,
        landcolor="rgb(245,245,245)",
        fitbounds="locations"
    )
    fig_map.update_layout(height=550, margin=dict(l=0, r=0, t=40, b=0))
    st.plotly_chart(fig_map, use_container_width=True)
    
    # ----------------------------------------------------
    # 🚢✈️🚛 FLOW SUMMARY (using LayerX naming)
    # ----------------------------------------------------
    st.markdown("## 🚚 Transport Flows by Mode")

    # --- Helper: read a value from the scenario row using multiple possible column names ---
    def get_value_safe_any(keys):
        for k in keys:
            if k in closest.index:
                try:
                    return float(closest[k])
                except Exception:
                    try:
                        return float(str(closest[k]).replace(",", "."))
                    except Exception:
                        return 0.0
        return 0.0

    # --- Column aliases (do NOT change the data; just read robustly) ---
    # Water may appear as Water/water/Sea/sea depending on the source file.
    L1_WATER = ["Layer1Water", "Layer1water", "Layer1Sea", "Layer1sea"]
    L1_AIR   = ["Layer1Air", "Layer1air"]

    L2_WATER = ["Layer2Water", "Layer2water", "Layer2Sea", "Layer2sea"]
    L2_AIR   = ["Layer2Air", "Layer2air"]
    L2_ROAD  = ["Layer2Road", "Layer2road"]

    L3_WATER = ["Layer3Water", "Layer3water", "Layer3Sea", "Layer3sea"]
    L3_AIR   = ["Layer3Air", "Layer3air"]
    L3_ROAD  = ["Layer3Road", "Layer3road"]

    # --- Layer 1: Manufacturers → Cross-docks (Air/Water only) ---
    st.markdown("### Manufacturers → Cross-docks")
    col1, col2 = st.columns(2)
    l1_water = get_value_safe_any(L1_WATER)
    l1_air = get_value_safe_any(L1_AIR)
    col1.metric("🚢 Water", f"{l1_water:,.0f} units")
    col2.metric("✈️ Air", f"{l1_air:,.0f} units")
    if (l1_water + l1_air) == 0:
        st.info("No transport activity recorded for this layer.")
    st.markdown("---")

    # --- Layer 2: Cross-docks → DCs ---
    st.markdown("### Cross-docks → DCs")
    col1, col2, col3 = st.columns(3)
    l2_water = get_value_safe_any(L2_WATER)
    l2_air = get_value_safe_any(L2_AIR)
    l2_road = get_value_safe_any(L2_ROAD)
    col1.metric("🚢 Water", f"{l2_water:,.0f} units")
    col2.metric("✈️ Air", f"{l2_air:,.0f} units")
    col3.metric("🚛 Road", f"{l2_road:,.0f} units")
    if (l2_water + l2_air + l2_road) == 0:
        st.info("No transport activity recorded for this layer.")
    st.markdown("---")

    # --- Layer 3: DCs → Retailer Hubs ---
    st.markdown("### DCs → Retailer Hub")
    col1, col2, col3 = st.columns(3)
    l3_water = get_value_safe_any(L3_WATER)
    l3_air = get_value_safe_any(L3_AIR)
    l3_road = get_value_safe_any(L3_ROAD)
    col1.metric("🚢 Water", f"{l3_water:,.0f} units")
    col2.metric("✈️ Air", f"{l3_air:,.0f} units")
    col3.metric("🚛 Road", f"{l3_road:,.0f} units")
    if (l3_water + l3_air + l3_road) == 0:
        st.info("No transport activity recorded for this layer.")
    st.markdown("---")
    # ----------------------------------------------------
    # RAW DATA VIEW
    # ----------------------------------------------------
    with st.expander("📄 Show Full Data Table"):
        st.dataframe(df.head(500), use_container_width=True)
