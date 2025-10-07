import io
import pandas as pd
import streamlit as st
from growlights import *

months = "Jan", "Feb", "Mar", "Apr", "May", "June", "July", "Aug", "Sept", "Oct", "Nov", "Dec"

# ---------- Help Functions ---------- #

def clear_results():
    for k in ("results", "error"):
        st.session_state.pop(k, None)

def format_climatedata(raw_data):

    required = [
        "Local Time",
        "Temperature (C)",
        "Solar Radiation (W/m²)"
    ]

    missing = [c for c in required if c not in raw_data.columns]
    if missing:
        raise KeyError(f"Missing required columns: {missing}")
    
    dt = pd.to_datetime(raw_data["Local Time"], errors="coerce", utc=False)
    if dt.isna().any():
        raise ValueError("Some 'Local Time' values could not be parsed as datetimes.")
    
    clean_data = pd.DataFrame({
        "Year": dt.dt.year.astype("int16"),
        "Month": dt.dt.month.astype("int8"),
        "Day": dt.dt.day.astype("int8"),
        "Hour": dt.dt.hour.astype("int8"),
        "Temp": pd.to_numeric(raw_data["Temperature (C)"], errors="coerce"),
        "Isun": pd.to_numeric(raw_data["Solar Radiation (W/m²)"], errors="coerce")
    })

    if clean_data[["Year", "Month", "Day", "Hour"]].isna().any().any():
        raise ValueError("Year/Month/Day/Hour could not be derived from 'Local Time'.")

    return clean_data

# ---------- Main Page ---------- #

st.title("Grow Lights - Average DLI")

system = st.radio("Choose system", ["LED", "Hybrid"], index=0, key="system", on_change=lambda: st.session_state.pop("results", None))

with st.form("controls", clear_on_submit=False):
    uploaded = st.file_uploader("Upload weather Excel from ksgclimatedata.streamlit.app", type=["xlsx"])

    # Take common specifications
    st.header("Common parameters")
    shade = st.number_input("Shade (fraction)", min_value=0.0, max_value=1.0, value=0.33, step=0.01)
    start = st.number_input("AL window start hour", min_value=0, max_value=23, value=5, step=1)
    duration = st.number_input("AL window duration (h)", min_value=1, max_value=24, value=16, step=1)
    rad_setpoint = st.number_input("Radiation setpoint (W/m²)", min_value=0, value=300, step=10)
    DLI_target = st.number_input("Target DLI (mol/m²/day)", min_value=0.0, value=30.0, step=0.5)

    # Take system specification
    if system == "LED":
        st.header("LED-only parameters")
        GH_tempsetpoint = st.number_input("GH temperature setpoint (°C)", min_value=-30.0, max_value=60.0, value=22.0, step=0.5)
        AL_Intensity = st.number_input("AL intensity (µmol/m²/s)", min_value=0.0, value=200.0, step=10.0)
        LED_eff = st.number_input("LED efficacy (µmol/J)", min_value=0.01, value=3.2, step=0.1)
    else:
        st.header("Hybrid parameters")
        day_tempsetpoint = st.number_input("Day temp setpoint (°C)", min_value=-30.0, max_value=60.0, value=22.0, step=0.5)
        night_tempsetpoint = st.number_input("Night temp setpoint (°C)", min_value=-30.0, max_value=60.0, value=16.0, step=0.5)
        AL_Intensity = st.number_input("Target AL intensity (µmol/m²/s)", min_value=0.0, value=200.0, step=10.0)
        LED_Intensity = st.number_input("LED fixture intensity (µmol/m²/s)", min_value=0.0, value=100.0, step=10.0)
        LED_eff = st.number_input("LED efficacy (µmol/J)", min_value=0.01, value=3.2, step=0.1)
        HPS_Intensity = st.number_input("HPS fixture intensity (µmol/m²/s)", min_value=0.0, value=100.0, step=10.0)
        HPS_eff = st.number_input("HPS efficacy (µmol/J)", min_value=0.01, value=1.8, step=0.1)

    run = st.form_submit_button("Calculate")

# ---------- Run Calculations ---------- #
if run:
    try:
        if uploaded is not None:
            # --- Convert weather data to panda table
            raw = pd.read_excel(uploaded, header=0)
            weather = format_climatedata(raw)

            if isinstance(weather, pd.DataFrame) and not weather.empty:
                st.success("✅ Uploaded Excel File")
            else:
                st.warning("Error")
        else:
            st.warning("Please fill all required fields")
            st.stop()

        if system == "LED":
            # Calculator monthly averages and generate the figure
            monthly = LED_usage(weather,
                shade=shade, start=start, duration=duration,
                rad_setpoint=rad_setpoint, GH_tempsetpoint=GH_tempsetpoint,
                DLI_target=DLI_target, AL_Intensity=AL_Intensity, LED_eff=LED_eff
            )
            fig1 = plot_avgDLI(monthly, months)
            fig2 = barplot_avgDLI(monthly, months)

        else:
            # Calculator monthly averages and generate the figure
            monthly = Hybrid_usage(weather,
                shade=shade, start=start, duration=duration,
                rad_setpoint=rad_setpoint,
                day_tempsetpoint=day_tempsetpoint, night_tempsetpoint=night_tempsetpoint,
                DLI_target=DLI_target, AL_Intensity=AL_Intensity,
                LED_Intensity=LED_Intensity, LED_eff=LED_eff,
                HPS_Intensity=HPS_Intensity, HPS_eff=HPS_eff
            )
            fig1 = plot_avgDLI(monthly, months)
            fig2 = barplot_avgDLI(monthly, months)            

        # Save the results in the session state (so download button does not clear output)
        st.session_state["results"] = {"system": system, "monthly": monthly, "fig1": fig1, "fig2": fig2}

    except Exception as e:
        st.error(f"Something went wrong: {e}")

# ---------- Display Output ---------- #

if "error" in st.session_state:
    st.error(f"Something went wrong: {st.session_state['error']}")

if "results" in st.session_state:
    res = st.session_state["results"]

    # --- Plot figure 1
    st.pyplot(res["fig1"], width='stretch')
  
    buf1 = io.BytesIO()  # creates a virtual container to hold binary data
    res["fig1"].savefig(buf1, format="png", dpi=300, bbox_inches="tight")  # save the figure data into the binary container
    st.download_button(
        "Download chart (PNG)",
        data=buf1.getvalue(),
        file_name="AverageDLI.png",
        mime = "image/png",
        key="png"
    )

    # --- Plot figure 2
    st.pyplot(res["fig2"], width='stretch')

    buf2 = io.BytesIO()  # creates a virtual container to hold binary data
    res["fig2"].savefig(buf2, format="png", dpi=300, bbox_inches="tight")  # save the figure data into the binary container
    st.download_button(
        "Download chart (PNG)",
        data=buf2.getvalue(),
        file_name="AverageDLI_barplot.png",
        mime = "image/png",
        key="bar"
    )

    # --- Display data table
    st.dataframe(
        res["monthly"].style.format({
            "DLI Solar": "{:.1f}",
            "DLI AL": "{:.1f}",
            "Elec Cons (kWh/m2)": "{:.2f}"
        }),
        width="stretch"
    )

    st.download_button(
    "Download monthly averages (CSV)",
    data=res["monthly"].to_csv(index=False).encode("utf-8"),
    file_name=("Monthly_DLI.csv"),
    mime="text/csv",
    key="csv"
    )

# ---------- Manual Reset  ---------- #

if st.button("Reset", type="secondary"):
    clear_results()
    st.rerun()
