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
import sys
from pathlib import Path
import streamlit.components.v1 as components


# ----------------------------------------------------
# 🚨 BIG WARNING POP-UP (injects into top window)
# ----------------------------------------------------
def _safe_float(x, default=0.0):
    try:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return default
        return float(x)
    except Exception:
        return default

def inject_big_warning_popup(*, title: str, subtitle: str, details_html: str, token: str):
    """
    Creates a full-screen overlay pop-up in the *top* browser window via JS injection.
    The pop-up is dismissible (Close button). We remember dismissal per-token in localStorage.
    """
    # Prevent breaking the <script> string if user-provided text contains quotes/backticks.
    title_js = title.replace("`", " ").replace("\\", "\\\\").replace('"', '\"')
    subtitle_js = subtitle.replace("`", " ").replace("\\", "\\\\").replace('"', '\"')
    token_js = token.replace("`", " ").replace("\\", "\\\\").replace('"', '\"')

    # details_html is HTML; we escape only </script> to be safe.
    details_html_safe = details_html.replace("</script>", "<\\/script>")

    components.html(f"""
<script>
(function() {{
  const overlayId = "tge-demand-warning";
  const dismissKey = "tge:demand_warning:dismissed:" + "{token_js}";
  const topWin = window.parent;
  const doc = topWin.document;

  if (topWin.localStorage && topWin.localStorage.getItem(dismissKey) === "1") {{
    return;
  }}

  // Remove any existing overlay (e.g., from a previous scenario)
  const old = doc.getElementById(overlayId);
  if (old) old.remove();

  const overlay = doc.createElement('div');
  overlay.id = overlayId;
  overlay.style.cssText = [
    "position:fixed",
    "inset:0",
    "background:rgba(0,0,0,0.82)",
    "z-index:999999",
    "display:flex",
    "align-items:center",
    "justify-content:center",
    "padding:24px"
  ].join(";");

  overlay.innerHTML = `
    <div style="
      background:#fff;
      border-radius:28px;
      width:min(980px, 94vw);
      max-height:92vh;
      overflow:auto;
      border:10px solid #ff1f1f;
      box-shadow:0 18px 60px rgba(0,0,0,0.45);
      padding:26px 28px;
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial;
    ">
      <div style="display:flex; gap:16px; align-items:flex-start; justify-content:space-between;">
        <div>
          <div style="font-size:32px; font-weight:900; color:#b00000; line-height:1.1;">
            ${"{title_js}"}
          </div>
          <div style="margin-top:10px; font-size:18px; font-weight:700; color:#111;">
            ${"{subtitle_js}"}
          </div>
        </div>
        <button id="tge-demand-warning-close" style="
          background:#ff1f1f;
          color:#fff;
          border:none;
          border-radius:14px;
          padding:12px 16px;
          font-size:16px;
          font-weight:800;
          cursor:pointer;
          box-shadow:0 6px 18px rgba(255,31,31,0.35);
        ">Close</button>
      </div>

      <div style="margin-top:18px; font-size:16px; color:#111; line-height:1.45;">
        ${"{details_html_safe}"}
      </div>

      <div style="margin-top:18px; padding:14px 16px; border-radius:16px; background:#fff3f3; border:2px solid #ffb3b3;">
        <div style="font-size:14px; font-weight:800; color:#7a0000; margin-bottom:6px;">
          Important
        </div>
        <div style="font-size:14px; color:#333;">
          You can continue exploring the charts below. Results are shown for the closest scenario available in the dataset.
        </div>
      </div>
    </div>
  `;

  doc.body.appendChild(overlay);

  doc.getElementById("tge-demand-warning-close").onclick = () => {{
    try {{
      if (topWin.localStorage) topWin.localStorage.setItem(dismissKey, "1");
    }} catch (e) {{}}
    overlay.remove();
  }};
}})();
</script>
""", height=0)

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

def run_sc2():
    # # ----------------------------------------------------
    # # CONFIGURATION
    # # ----------------------------------------------------
    # st.set_page_config(
    #     page_title="Optimization Sensitivity Dashboard",
    #     layout="wide",
    #     initial_sidebar_state="expanded"
    # )
    
    st.title("🏭 Scenario 2: Local Sourcing for Resilience and Impact")
    
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
        return pd.read_excel(BytesIO(response.content))
    
    
    
    def format_number(value, x):
        """Format numbers with thousand separators and max two decimals."""
        try:
            return f"{float(value):,.{x}f}"
        except (ValueError, TypeError):
            return value
    
    
    # ----------------------------------------------------
    # 📦 DEMAND LEVEL SELECTION
    # ----------------------------------------------------
    # st.sidebar.header("📦 Demand Level (%)")
    
    LOCAL_XLSX_PATH = resolve_local_path("simulation_results_demand_levelsSC2.xlsx")

    available_sheets = get_sheet_names(LOCAL_XLSX_PATH)
    
    # Auto-detect demand-level sheets (contain % or “Demand”)
    demand_sheets = [s for s in available_sheets if "%" in s or "Demand" in s]
    if not demand_sheets:
        demand_sheets = available_sheets
    
    # Demand-level UI intentionally hidden; always default to the 100% sheet.
    selected_demand = next((s for s in demand_sheets if str(s).strip() == "100%"), None)
    if selected_demand is None:
        selected_demand = next((s for s in demand_sheets if "100" in str(s)), None)
    if selected_demand is None:
        selected_demand = demand_sheets[0] if demand_sheets else "Default"
    
    # ----------------------------------------------------
    # LOAD DATA (local first, then fallback to GitHub)
    # ----------------------------------------------------
    GITHUB_XLSX_URL = (
        "https://raw.githubusercontent.com/aydınarda/TGE_CASE-web-page/main/single_page/"
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
        
    if isinstance(df, pd.Series):
        df = df.to_frame().T
    elif not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)

    df_display = df.apply(lambda col: col.map(lambda x: format_number(x, 0)))  # For display purposes only (keep original df for logic)

    def format_demand_level(value, fallback_label: str = ""):
        """Return a human-friendly demand level label (e.g., '95%')."""
        try:
            # Some sheets store demand as a fraction (0–1)
            v = float(value)
            if 0 <= v <= 1:
                return f"{v * 100:.0f}%"
            # Or already percent
            if 1 < v <= 100:
                return f"{v:.0f}%"
        except Exception:
            pass
        return fallback_label or "N/A"

    
    
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
        "Emission Reduction Target (%)",
        min_value=0,
        max_value=100,
        value=int(default_val * 100),  # ✅ default = 0%
        step=1,
        help="Set a Emission Reduction Target between 0–100 %.",
    )
    
    # Convert displayed percentage back to 0–1 for internal matching
    co2_pct = co2_pct_display / 100.0
    
    
    # 🎯 Carbon price selector (work with either column name)
    co2_cost_options = [20, 40, 60, 80, 100, 1000, 10000, 100000]  # €/ton
    co2_cost = st.sidebar.select_slider(
        "Carbon price in Europe (€ per ton)",
        options=co2_cost_options,
        value=60,
        help="Select the EU carbon price column value."
    )

    # 🎛️ Sourcing Cost Surcharge (Asia only) — optional if present in dataset
    # Teaching note UI: We call the Sourcing Cost Multiplier “Sourcing Cost Surcharge”; a sliding bar
    # from 100% to 300%, 50% increments. Internally this maps to a multiplier of 1.0–3.0.
    scm_col = next((c for c in df.columns if "sourcing" in c.lower() and "multiplier" in c.lower()), None)
    if scm_col is not None:
        scm_values = sorted(pd.to_numeric(df[scm_col], errors="coerce").dropna().unique().tolist())
        if scm_values:
            selected_surcharge_pct = st.sidebar.slider(
                "Sourcing Cost Surcharge (%)",
                min_value=100,
                max_value=300,
                value=100,
                step=50,
                help="Applies only to Asia (Taiwan/Shanghai) sourcing costs."
            )
            requested_multiplier = selected_surcharge_pct / 100.0

            # Use exact multiplier if available; otherwise snap to the closest available value in the dataset
            closest_multiplier = min(scm_values, key=lambda x: abs(x - requested_multiplier))
            df_scm = df[df[scm_col] == closest_multiplier].copy()

            if df_scm.empty:
                st.warning("⚠️ No scenarios match this sourcing surcharge — showing all instead.")
            else:
                if abs(closest_multiplier - requested_multiplier) > 1e-9:
                    st.info(
                        f"ℹ️ This dataset doesn't include {selected_surcharge_pct:.0f}% exactly. "
                        f"Showing the closest available surcharge: {closest_multiplier * 100:.0f}%."
                    )
                df = df_scm
                # Re-derive any cached derived views on the filtered dataset
                try:
                    data_by_weight = preprocess(df)  # noqa: F841
                except Exception:
                    pass


    # Decide which column the dataset uses for EU carbon price

    price_col = None
    if "CO2_CostAtMfg" in df.columns:
        price_col = "CO2_CostAtMfg"
    elif "CO2_CostAtEU" in df.columns:
        price_col = "CO2_CostAtEU"
    
    # Apply price filter if we found a price column, otherwise keep all rows
    pool = df.copy() if price_col is None else df[df[price_col] == co2_cost]

    if pool.empty:
        st.warning("⚠️ No scenarios match this CO₂ price — showing all instead.")
        pool = df.copy()

    # NOTE: We do NOT require an exact CO₂ match here.
    # We always snap to the closest available scenario below so the dashboard keeps rendering.

    
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
            "This solution is not feasible- even Swiss precision couldn't optimize it! Please adjust the CO2 target and parameters."
        )
        fig_sens.update_coloraxes(colorbar=dict(ticksuffix="%"))
        st.stop()
    
    if closest.get("Status", "") not in ["OPTIMAL", 2]:
        st.warning(
            "🤖 Hmm... looks like this one didn’t converge to perfection. "
            "We’ll show you the closest feasible setup anyway. 💪"
        )
    
    

    # ----------------------------------------------------
    # 🚨 UNSATISFIED DEMAND CHECK (big pop-up)
    # ----------------------------------------------------
    used_uns = bool(closest.get("Used_UNS_Fallback", False))
    satisfied_pct = _safe_float(closest.get("Satisfied_Demand_pct", 1.0), 1.0)
    satisfied_units = _safe_float(closest.get("Satisfied_Demand_units", None), None)
    unmet_units = _safe_float(closest.get("Unmet_Demand_units", 0.0), 0.0)

    if satisfied_units is None:
        satisfied_units = _safe_float(closest.get("DemandFulfillment", 0.0), 0.0)

    is_unsatisfied = used_uns or (unmet_units > 1e-6) or (satisfied_pct < 0.999999)

    if is_unsatisfied:
        sat_pct_disp = max(0.0, min(1.0, satisfied_pct)) * 100.0
        details = f"""
        <div style="font-size:18px; font-weight:800; margin-bottom:10px;">
          Demand cannot be fully satisfied under the selected scenario.
        </div>
        <ul style="margin:0; padding-left:20px;">
          <li><b>UNS fallback used:</b> {str(used_uns)}</li>
          <li><b>Satisfied demand:</b> {satisfied_units:,.2f} units</li>
          <li><b>Unmet demand:</b> {unmet_units:,.2f} units</li>
          <li><b>Satisfaction:</b> {sat_pct_disp:.2f}%</li>
        </ul>
        <div style="margin-top:14px;">
          <div style="font-size:14px; font-weight:800; color:#333; margin-bottom:6px;">Satisfaction bar</div>
          <div style="width:100%; background:#eee; border-radius:999px; height:18px; overflow:hidden;">
            <div style="width:{sat_pct_disp:.2f}%; height:18px; background:#ff1f1f;"></div>
          </div>
        </div>
        """

        token = f"SC2|{selected_demand}|CO2={int(co2_pct*100)}|price={co2_cost}|SID={closest.get('Scenario_ID','')}"
        inject_big_warning_popup(
            title="⚠️ UNSATISFIED DEMAND",
            subtitle="Some customer demand remains unmet with the selected parameters.",
            details_html=details,
            token=token
        )

        st.error(
            f"⚠️ Capacity is insufficient; only {sat_pct_disp:.2f}% satisfied on average. You’re losing market share!"
        )

    # ----------------------------------------------------
    # KPI VIEW
    # ----------------------------------------------------
    CLOSEST_SCENARIO_DETAILS = False  # Set to False to hide the closest scenario details section
    
    if CLOSEST_SCENARIO_DETAILS:
        st.subheader("📊 Closest Scenario Details")
        # Hide any column starting with 'f' (case-insensitive)
        closest_df = closest.to_frame().T  # transpose for row→column view
        
        # Remove columns starting with 'f'
        cols_to_show = [c for c in closest_df.columns if not (c.lower().startswith("f") or c.lower().startswith("scenario_id"))]
    
        # Display cleaned table
        st.write(closest_df[cols_to_show].apply(lambda col: col.map(lambda x: format_number(x, 0))))
    
    col1, col2, col3, col4 = st.columns(4)
    
    col1.metric("Total Cost (€)", f"{closest['Objective_value']:,.0f}")
    col2.metric("Total CO₂", f"{closest['CO2_Total']:,.2f}")
    col3.metric("Inventory Total (€)", f"{closest[['Inventory_L1','Inventory_L2','Inventory_L3']].sum():,.0f}")
    col4.metric("Transport Total (€)", f"{(closest[['Transport_L1','Transport_L2','Transport_L3']].sum() + closest.get('Transport_L2_new', 0) + (6.25 * float(closest.get('Satisfied_Demand_units', 0)))):,.0f}")


    # ----------------------------------------------------
    # 🆕 COST vs EMISSIONS DUAL-AXIS BAR-LINE PLOT (DYNAMIC)
    # ----------------------------------------------------
    st.markdown("## 💶 Emissions vs Total Cost ")

    @st.cache_data(show_spinner=False)
    def generate_cost_emission_chart_plotly_dynamic(df_sheet: pd.DataFrame, selected_value: float):
        """Dual-axis (bars=emissions, line=cost) over CO₂ target levels, with the current selection highlighted."""

        # Detect column names robustly
        emissions_col = "CO2_Total" if "CO2_Total" in df_sheet.columns else (
            "Total Emissions" if "Total Emissions" in df_sheet.columns else None
        )
        cost_col = "Objective_value" if "Objective_value" in df_sheet.columns else (
            "Total Cost" if "Total Cost" in df_sheet.columns else None
        )

        # CO₂ target column (fraction 0–1 preferred)
        co2_col = None
        if "CO2_percentage" in df_sheet.columns:
            co2_col = "CO2_percentage"
        else:
            # fallback: try to find a CO2-related percentage / reduction column
            for c in df_sheet.columns:
                cl = str(c).lower()
                if "co2" in cl and any(k in cl for k in ["%", "percentage", "reduction", "target"]):
                    co2_col = c
                    break

        if emissions_col is None or cost_col is None or co2_col is None:
            return None

        df_chart = df_sheet[[emissions_col, cost_col, co2_col]].copy()

        # Normalize CO₂ target to fraction (0–1) if dataset stores 0–100
        try:
            co2_max = float(pd.to_numeric(df_chart[co2_col], errors="coerce").max())
        except Exception:
            co2_max = 1.0

        if co2_max is not None and co2_max > 1.5:
            df_chart["_co2_frac"] = pd.to_numeric(df_chart[co2_col], errors="coerce") / 100.0
            selected_x = (selected_value / 100.0) if selected_value is not None else None
        else:
            df_chart["_co2_frac"] = pd.to_numeric(df_chart[co2_col], errors="coerce")
            selected_x = selected_value

        df_chart = df_chart.dropna(subset=["_co2_frac"]).sort_values(by="_co2_frac")

        # Unit scaling for readability
        df_chart["Emissions (k)"] = pd.to_numeric(df_chart[emissions_col], errors="coerce") / 1000.0
        df_chart["Cost (M)"] = pd.to_numeric(df_chart[cost_col], errors="coerce") / 1_000_000.0

        import plotly.graph_objects as go
        fig = go.Figure()

        # Grey bars: emissions
        fig.add_trace(go.Bar(
            x=df_chart["_co2_frac"],
            y=df_chart["Emissions (k)"],
            name="Emissions (thousand)",
            marker_color="dimgray",
            opacity=0.9,
            yaxis="y1",
        ))

        # Red dotted line: cost
        fig.add_trace(go.Scatter(
            x=df_chart["_co2_frac"],
            y=df_chart["Cost (M)"],
            name="Total Cost (million €)",
            mode="lines+markers",
            line=dict(color="red", width=2, dash="dot"),
            marker=dict(size=6, color="red"),
            yaxis="y2",
        ))

        # Highlight the selected scenario (closest x)
        if selected_x is not None and len(df_chart) > 0:
            try:
                hi_idx = (df_chart["_co2_frac"] - float(selected_x)).abs().idxmin()
                highlight_row = df_chart.loc[hi_idx]
                fig.add_trace(go.Scatter(
                    x=[highlight_row["_co2_frac"]],
                    y=[highlight_row["Cost (M)"]],
                    mode="markers+text",
                    marker=dict(size=14, color="red", symbol="circle"),
                    text=[f"{float(highlight_row['_co2_frac']):.2%}"],
                    textposition="top center",
                    name="Selected Scenario",
                    yaxis="y2",
                ))
            except Exception:
                pass

        # Layout and style
        fig.update_layout(
            template="plotly_white",
            title=dict(text="<b>Cost vs. Emissions</b>", x=0.45, font=dict(color="firebrick", size=20)),
            xaxis=dict(
                title="CO₂ Reduction (%)",
                tickformat=".0%",
                showgrid=False,
            ),
            yaxis=dict(title="Emissions (thousand)", side="left", showgrid=False),
            yaxis2=dict(title="Cost (million €)", overlaying="y", side="right", showgrid=False),
            legend=dict(orientation="h", y=-0.25, x=0.3),
            margin=dict(l=40, r=40, t=60, b=60),
            height=450,
        )

        return fig

    fig_cost_emission = generate_cost_emission_chart_plotly_dynamic(pool, float(closest.get("CO2_percentage", 0.0)))
    if fig_cost_emission is not None:
        st.plotly_chart(fig_cost_emission, use_container_width=True)
    else:
        st.warning("⚠️ Could not build the dual-axis Cost vs Emissions chart (missing required columns in this dataset).")
    

    # ----------------------------------------------------
    # COST vs EMISSION SENSITIVITY PLOT
    # ----------------------------------------------------
    st.markdown("## 📈 Emissions vs Cost Elements")
    
    # Let user choose which cost metric to plot
    cost_metric_map = {
        "Total Cost (€)": "Objective_value",
        "Inventory Cost (€)": ["Inventory_L1", "Inventory_L2", "Inventory_L3"],
        "Transport Cost (€)": ["Transport_L1", "Transport_L2", "Transport_L2_new", "Transport_L3"],
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
        if selected_metric_label == "Transport Cost (€)":
            filtered["Selected_Cost"] += 6.25 * pd.to_numeric(filtered["Satisfied_Demand_units"], errors="coerce").fillna(0)
        y_label = selected_metric_label
    else:
        filtered["Selected_Cost"] = filtered[cost_metric_map[selected_metric_label]]
        y_label = selected_metric_label
    if not filtered.empty:
        # Detect which CO₂ price column exists
        filtered["CO2 Reduction % Display"] = pd.to_numeric(filtered["CO2_percentage"], errors="coerce") * 100
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
            color="CO2 Reduction % Display",
            hover_data=hover_cols,
            title=f"{selected_metric_label} vs Total CO₂ ({price_col or 'CO₂ price'} = {co2_cost} €/ton)",
            labels={
                "CO2_Total": "Total CO₂ Emissions (tons)",
                "Selected_Cost": y_label,
                "CO2 Reduction % Display": "CO2 Reduction %"
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
    
    st.markdown("## 🏭 Production Sourcing Breakdown")
    
    # --- total market demand (fixed reference) ---
    TOTAL_MARKET_DEMAND = 111000  # units
    
    # --- Gather flow variable columns ---
    f1_cols = [c for c in closest.index if c.startswith("f1[")]
    f2_2_cols = [c for c in closest.index if c.startswith("f2_2[")]
    
    # --- Calculate production sums ---
    prod_sources = {}
    
    # Existing plants (f1)
    for plant in ["Taiwan", "Shanghai"]:
        prod_sources[plant] = sum(
            float(closest[c]) for c in f1_cols if c.startswith(f"f1[{plant},")
        )
    
    # New European factories (f2_2)
    new_facilities = ["Budapest", "Prague", "Cork", "Helsinki", "Warsaw"]
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
        title=f"Production Share by Source (Demand Level: {format_demand_level(closest.get('Demand_Level', None), selected_demand)})",
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
        st.markdown("#### 📦 Production Sourcing")
        st.dataframe(df_prod.round(2), use_container_width=True)
    
    with colC:
        st.markdown("#### 🌿 CO₂ Factors (kg/unit)")
        co2_factors_mfg = pd.DataFrame({
            "From mfg": ["Taiwan", "Shanghai", "Budapest", "Prague", "Cork", "Helsinki", "Warsaw"],
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
    f2_cols = [c for c in closest.index if c.startswith("f2[")]
    
    # --- Define crossdocks used in SC2 ---
    crossdocks = ["Paris", "Gdansk", "Vienna"]
    
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
            title=f"Crossdock Outbound Share (Demand Level: {format_demand_level(closest.get('Demand_Level', None), selected_demand)})",
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
        "Lat": [50.040750, 50.954468, 56.946285, 36.168056],
        "Lon": [15.776590, 1.862801, 24.105078, -5.348611]
    })

    retailers = pd.DataFrame({
        "Type": ["Retailer Hub"] * 7,
        "Lat": [50.935173, 51.219890, 50.061430, 54.902720, 59.911491, 53.350140, 59.329440],
        "Lon": [6.953101, 4.403460, 19.936580, 23.909610, 10.757933, -6.266155, 18.068610]
    })

    
    # --- New Production Facilities (f2_2) ---
    f2_2_cols = [c for c in closest.index if c.startswith("f2_2_bin")]
    
    # Define coordinates (one per possible facility)
    facility_coords = {
    "f2_2_bin[Budapest]": (47.497913, 19.040236),   # Budapest
    "f2_2_bin[Prague]": (50.088040, 14.420760),   # Prague
    "f2_2_bin[Cork]": (51.898514, -8.475604),   # Cork
    "f2_2_bin[Helsinki]": (60.169520, 24.935450),   # Helsinki
    "f2_2_bin[Warsaw]": (52.229770, 21.011780),   # Warsaw
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
        "Distribution Center": "black",
        "Retailer Hub": "red",
        "New Production Facility": "deepskyblue"
    }
    
    size_map = {
        "Plant": 15,
        "Cross-dock": 14,
        "Distribution Center": 16,
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
    - 🏬 **Distribution Center**  
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
        """Sum up air/water/road units for a given flow prefix like 'f1', 'f2', 'f2_2', or 'f3'."""
        flow_cols = [c for c in closest.index if c.startswith(prefix + "[")]
        totals = {"air": 0.0, "water": 0.0, "road": 0.0}
    
        for col in flow_cols:
            # Extract mode from inside brackets, e.g. f2_2[CZMC,DEBER,road]
            match = re.search(r",\s*([a-zA-Z]+)\]$", col)
            if match:
                mode = match.group(1).lower()
                # Normalize common synonyms so we keep UI naming consistent
                if mode == "sea":
                    mode = "water"
                if mode == "truck":
                    mode = "road"
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
        cols[0].metric("🚢 Water", f"{totals['water']:,.0f} units")
        cols[1].metric("✈️ Air", f"{totals['air']:,.0f} units")
        if include_road:
            cols[2].metric("🚛 Road", f"{totals['road']:,.0f} units")
    
        if sum(totals.values()) == 0:
            st.info("No transport activity recorded for this layer.")
        st.markdown("---")
    
    
    # Layer summaries
    display_layer_summary("Plants → Cross-docks", "f1", include_road=False)
    display_layer_summary("Cross-docks → DCs", "f2", include_road=True)
    display_layer_summary("New Facilities → DCs", "f2_2", include_road=True)
    display_layer_summary("DCs → Retailer Hubs", "f3", include_road=True)
    
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
            + (6.25 * float(closest.get("Satisfied_Demand_units", 0)))
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
            "Carbon Cost in Production": co2_cost_production,
            "Inventory Cost": inventory_cost
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

        def _first_present(series: pd.Series, keys):
            """Return the first available numeric value among candidate column names."""
            for k in keys:
                if k in series.index:
                    try:
                        v = series.get(k)
                        if pd.notna(v):
                            return float(v)
                    except Exception:
                        continue
            return None

        e_air = _first_present(closest, ["E_air", "E_Air"])
        e_water = _first_present(closest, ["E_water", "E_Water", "E_sea", "E_Sea"])
        e_road = _first_present(closest, ["E_road", "E_Road"])
        e_lastmile = _first_present(closest, ["E_lastmile", "E_Lastmile", "E_LastMile"])
        e_total = _first_present(closest, ["CO2_Total", "CO2_total", "CO2TOTAL"])

        missing = []
        if e_air is None: missing.append("E_air")
        if e_water is None: missing.append("E_water / E_sea")
        if e_road is None: missing.append("E_road")
        if e_lastmile is None: missing.append("E_lastmile")
        if e_total is None: missing.append("CO2_Total")

        if missing:
            st.warning("⚠️ Missing emission columns: " + ", ".join(missing))
            st.info("No valid emission values found in this scenario.")
        else:
            # --- Recalculate Production Emissions from totals (keeps dataset untouched) ---
            corrected_E_prod = e_total - e_air - e_water - e_road - e_lastmile
            total_transport = e_air + e_water + e_road

            emission_data = {
                "Production": corrected_E_prod,
                "Last-mile": e_lastmile,
                "Air": e_air,
                "Water": e_water,
                "Road": e_road,
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
                    "#4B8A08", "#2E8B57", "#808080", "#FFD700", "#90EE90", "#000000"
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
# ----------------------------------------------------
    # RAW DATA VIEW
    # ----------------------------------------------------
    with st.expander("📄 Show Full Summary Data"):
        st.dataframe(df.head(500), use_container_width=True)
