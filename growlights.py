# PURPOSE #
# This function returns a modified weather dataframe with additional columns: 
import matplotlib.pyplot as plt

# -------- Calculation functions -------- #

def LED_usage(weather, shade=0.33, start=5, duration=16, rad_setpoint=300, GH_tempsetpoint=22, DLI_target=30, AL_Intensity = 200, LED_eff = 3.2):
    # Units of standard variable entries
    #     shade (fraction)
    #     start, duration (hour)
    #     rad_setpoint (W/m2)
    #     GH_temp (C)
    #     DLI_target (mol/m2/day)
    #     AL_Intensity (umol/m2/s) -> Real for selected LED fixture
    #     LED_eff (umol/J)
       
    # ------------
    # --- Step 1: Calculate PAR at the canopy level (mol/m2/h)
    # ------------

    #   use the entered shade value to calculate the conversion factor from W/m2 to mol/m2/h
    #      transmissivity = 0.8
    #      percentage of radiation in the PAR range = 0.4
    #      conversion 1W = 4.6 umol
    k = 0.8*(1-shade)*0.5*4.6*3600/1000000

    #      write in the calculated PAR at the canopy level into each row in the new column named 'PAR_Canopy' [mol/m2/h]
    weather["PAR_Canopy"] = k*weather["Isun"].fillna(0) # mol/m2/h

    # ------------
    # --- Step 2: Determine which hours AL will be ON (maximum)
    # ------------

    weather["AL On/Off"]=0
    for index, row in weather.iterrows():

        hour = row["Hour"]
        temp = row["Temp"]
        Isun3 = 0.8*(1-shade)*row["Isun"]

        if (hour >= start and hour < (start+duration+1)) and Isun3 < rad_setpoint and not (temp > GH_tempsetpoint and Isun3 != 0):
            weather.at[index, "AL On/Off"] = 1
        else:
            weather.at[index, "AL On/Off"] = 0

    #   Summarizes the weather data into daily rows including a column which sums the PAR values to obtain the natural DLI
    daily = (
        weather
        .groupby(["Year", "Month", "Day"], as_index=False)
        .agg(
            **{
            "Natural DLI": ("PAR_Canopy", "sum"),
            "Max AL Hours": ("AL On/Off", "sum")
            }
        )
    )

    # ------------
    # --- Step 3: Determine which hours AL will be ON (actual)
    # ------------

    #   Calculate PAR needed (DLI_target - Natural DLI)
    daily["PAR Needed"] = (DLI_target - daily["Natural DLI"]).clip(lower=0) # mol/m2/d

    #   Calculate Actual AL Hours
    hours_needed = daily["PAR Needed"] *1000000 / AL_Intensity / 3600
    daily["Actual AL Hours"] = hours_needed.clip(lower=0, upper=daily["Max AL Hours"]) # h

    #   Calculate DLI contribution from AL
    daily["DLI AL"] = AL_Intensity*3600/1000000*daily["Actual AL Hours"] # mol/m2/d
    daily["DLI Total"] = daily["Natural DLI"] + daily["DLI AL"]

    # ------------
    # --- Step 4: Calculate electricity consumption per day
    # ------------

    #   Divide the remaining PAR needed by the AL Intensity. Then convert from J to kWh
    daily["Elec Cons (kWh/m2)"] = AL_Intensity/LED_eff/1000*daily["Actual AL Hours"]

    # ------------
    # --- Step 5: Calculate heat generated per day
    # ------------

    # ------------
    # --- Step 6: Summarize to a monthly table
    # ------------

    monthly = (
        daily.groupby(["Month"], as_index=False)
        .agg(
            **{
            "DLI Solar": ("Natural DLI", "mean"),
            "DLI AL": ("DLI AL", "mean"),
            "DLI Total Stdev": ("DLI Total", "std"),
            "Elec Cons (kWh/m2)": ("Elec Cons (kWh/m2)", "sum")
            }
        )
    )

    return monthly

def Hybrid_usage(weather, shade=0.33, start=5, duration=16, rad_setpoint=300, day_tempsetpoint=22, night_tempsetpoint = 16, DLI_target=30, AL_Intensity = 200, LED_Intensity = 100, LED_eff = 3.2, HPS_Intensity = 100, HPS_eff = 1.8):
    # Units of standard variable entries
    #     shade (fraction)
    #     start, duration (hour)
    #     rad_setpoint (W/m2)
    #     GH_temp (C)
    #     DLI_target (mol/m2/day)
    #     AL_Intensity (umol/m2/s) -> Desired for crop
    #     LED_eff (umol/J)
   
    # ------------
    # --- Step 1: Calculate PAR at the canopy level (mol/m2/h)
    # ------------

    #   use the entered shade value to calculate the conversion factor from W/m2 to mol/m2/h
    #      transmissivity = 0.8
    #      percentage of radiation in the PAR range = 0.4
    #      conversion 1W = 4.6 umol
    k = 0.8*(1-shade)*0.5*4.6*3600/1000000

    #     write in the calculated PAR at the canopy level into each row in the new column named 'PAR_Canopy' [mol/m2/h]
    weather["PAR_Canopy"] = k*weather["Isun"].fillna(0) # mol/m2/h

    #     aggregate PAR_Canopy into a daily value "Natural DLI"
    weather["Natural DLI"] = (weather.groupby(["Year", "Month", "Day"])["PAR_Canopy"].transform("sum"))

    # ------------
    # --- Step 2: Determine which hours AL will be ON (maximum)
    # ------------

    weather["AL On/Off"]=0
    for index, row in weather.iterrows():

        hour = row["Hour"]
        temp = row["Temp"]
        Isun3 = 0.8*(1-shade)*row["Isun"]

        if (hour >= start and hour < (start+duration+1)) and Isun3 < rad_setpoint and not (temp > day_tempsetpoint and Isun3 != 0):
            weather.at[index, "AL On/Off"] = 1
        else:
            weather.at[index, "AL On/Off"] = 0

    # Calculate daily sums
    weather["Max AL Hours"] = (
        weather.groupby(["Year", "Month", "Day"])["AL On/Off"].transform("sum")
    )

    # ------------
    # --- Step 3: Determine actual daily AL hours needed to reach Target DLI
    # ------------

    #   Calculate PAR needed (DLI_target - Natural DLI)
    weather["PAR Needed"] = (DLI_target - weather["Natural DLI"]) # mol/m2/d

    #   Calculate Actual AL Hours
    hours_needed = weather["PAR Needed"] *1000000 / AL_Intensity / 3600
    weather["Actual AL Hours"] = hours_needed.clip(lower=0, upper=weather["Max AL Hours"]) # h

    # ------------
    # --- DECISION 1: Which lights will turn on at which hours?
    # ------------

    #      First lights can turn on under two conditions:
    #        1) "AL On/Off" == 1
    #        2) Cumulative hours < "Actual AL Hours"

    weather["Light1"] = "None"
    current_key = None
    used_hours = 0       # how many hours Light1 has been ON so far "today"
    for index, row in weather.iterrows():

        key = (row["Year"], row["Month"], row["Day"])
        if key != current_key:
            # new day -> reset the daily counter
            current_key = key
            used_hours = 0

        AL_ok = int(row["AL On/Off"]) == 1          # shows true if AL are allowed to turn on
        max = int(round(row["Actual AL Hours"]))    # max for this day (same each hour)

        if AL_ok and used_hours < max:
            temp = row["Temp"]
            Isun3 = 0.8*(1-shade)*row["Isun"]
    
            if Isun3 == 0:                          # if it is night time, compare to night time temp setpoint
                weather.at[index, "Light1"] = "HPS" if temp < night_tempsetpoint else "LED"
            else:                                   # if it is day time, comapre to day time temp setpoint
                weather.at[index, "Light1"] = "HPS" if temp < day_tempsetpoint else "LED"
            
            used_hours += 1
        else:
            weather.at[index, "Light1"] = "None"

    # ------------
    # --- DECISION 2: Are the other set of lights needed (hourly decision) to reach the desired AL Intensity
    # ------------

    #      Second lights can turn on under three conditions:
    #        1) First set of lights turned on
    #        2) First lights do not reach the AL Intensity goal
    #        3) Outside temperature is lower than GH setpoint temperature (setpoint specific to day or night)

    weather["Light2"] = "None"
    for index, row in weather.iterrows():

        Light1 = row["Light1"]
        temp = row["Temp"]
        Isun3 = 0.8*(1-shade)*row["Isun"]

        if Light1 == "None":
            weather.at[index, "Light2"] = "None"
        elif Light1 == "HPS":
            weather.at[index, "Light2"] = "LED" if HPS_Intensity < AL_Intensity else "None"
        else:
            if Isun3 == 0:
                weather.at[index, "Light2"] = "HPS" if LED_Intensity < AL_Intensity and temp < night_tempsetpoint else "None"
            else:
                weather.at[index, "Light2"] = "HPS" if LED_Intensity < AL_Intensity and temp < day_tempsetpoint else "None"

    # ------------
    # --- Step 4: Calculate PAR and Elec from each light
    # ------------

    weather["Light1 PAR"] = 0
    weather["Light2 PAR"] = 0

    weather["Light1 Elec"] = 0
    weather["Light2 Elec"] = 0

    for index, row in weather.iterrows():

        type1 = row["Light1"]
        type2 = row["Light2"]

        if type1 == "None":
            weather.at[index, "Light1 Elec"] = None
            weather.at[index, "Light1 PAR"] = None
        elif type1 == "LED":
            weather.at[index, "Light1 Elec"] = LED_Intensity/LED_eff/1000 # kWh/m2
            weather.at[index, "Light1 PAR"] = LED_Intensity*3600/1000000 # mol/m2/h
        elif type1 == "HPS":
            weather.at[index, "Light1 Elec"] = HPS_Intensity/HPS_eff/1000 # kWh/m2
            weather.at[index, "Light1 PAR"] = HPS_Intensity*3600/1000000 # mol/m2/h

        if type2 == "None":
            weather.at[index, "Light2 Elec"] = None
            weather.at[index, "Light2 PAR"] = None
        elif type2 == "LED":
            weather.at[index, "Light2 Elec"] = LED_Intensity/LED_eff/1000
            weather.at[index, "Light2 PAR"] = LED_Intensity*3600/1000000 # mol/m2/h
        elif type2 == "HPS":
            weather.at[index, "Light2 Elec"] = HPS_Intensity/HPS_eff/1000
            weather.at[index, "Light2 PAR"] = HPS_Intensity*3600/1000000 # mol/m2/h

    #     Light1 + Light2 (add columns which are the sum of contribution from both sets of lights)
    weather["Hourly Elec"] = weather[["Light1 Elec", "Light2 Elec"]].sum(axis=1, skipna=True)
    weather["AL_PAR_hourly"] = weather[["Light1 PAR", "Light2 PAR"]].sum(axis=1, skipna=True) # mol/m2/h

    #     Aggregate by Month (total electrical for each month & average daily PAR)
    weather["Monthly Elec (kWh/m2)"] = (weather.groupby(["Year", "Month"])["Hourly Elec"].transform("sum"))
    weather["AL_PAR_daily"] = (weather.groupby(["Year", "Month", "Day"])["AL_PAR_hourly"].transform("sum"))
    weather["Month AVG PAR (mol/m2/d)"] = (weather.groupby(["Year", "Month"])["AL_PAR_daily"].transform("mean"))

    weather["DLI Total"] = weather["Natural DLI"] + weather["AL_PAR_daily"]

    # ------------
    # --- Step 5: Calculate heat generated per day
    # ------------

    # ------------
    # --- Step 6: Generate 10-year average monthly table
    # ------------
    monthly = (
        weather.groupby("Month", as_index=False)
        .agg(
            **{
            "DLI Solar": ("Natural DLI", "mean"),
            "DLI AL": ("AL_PAR_daily", "mean"),
            "DLI Total Stdev": ("DLI Total", "std"),
            "Elec Cons (kWh/m2)": ("Monthly Elec (kWh/m2)", "mean")
            }
        )
    )  

    return monthly

# -------- Plotting functions ------- #

def plot_avgDLI(monthly, months, savepath="AverageDLI_hybrid.png"):
    
    fig, ax = plt.subplots()

    # Plot the stack plot
    ax.stackplot(months, monthly["DLI Solar"], monthly["DLI AL"], labels=["DLI Solar", "DLI AL"], colors=["navajowhite", "coral"], alpha=0.7)
    ax.legend(loc="upper left")
    ax.set_xticks([])   # removes ticks and labels
    ax.set_ylabel("Average DLI (mol/m2/d)")

    # Add the table
    table_data = [
        [f"{val:.1f}" for val in monthly["DLI Solar"]],
        [f"{val:.1f}" for val in monthly["DLI AL"]],
    ]

    ax.table = plt.table(cellText=table_data, rowLabels=["DLI Solar", "DLI AL"], colLabels=months, loc="bottom", cellLoc="center")

    if savepath:
        fig.savefig(savepath, dpi=300)
    
    return fig

def barplot_avgDLI(monthly, months, savepath="AverageDLI.png"):
    
    fig, ax = plt.subplots()

    # Plot the stack bar plot
    ax.bar(months, monthly["DLI Solar"], label="DLI Solar", color="navajowhite", alpha=0.7)
    ax.bar(months, monthly["DLI AL"], bottom=monthly["DLI Solar"],
           label="DLI AL", color="coral", alpha=0.7)
    total = monthly["DLI Solar"] + monthly["DLI AL"]
    ax.errorbar(range(len(months)), total, yerr=monthly["DLI Total Stdev"], fmt="none", capsize=5, color="black")
    
    ax.legend(loc="upper left")
    ax.set_xticks([])   # removes ticks and labels
    ax.set_ylabel("Average DLI (mol/m2/d)")

    # Add the table
    table_data = [
        [f"{val:.1f}" for val in monthly["DLI Solar"]],
        [f"{val:.1f}" for val in monthly["DLI AL"]],
    ]

    ax.table = plt.table(cellText=table_data, rowLabels=["DLI Solar", "DLI AL"], colLabels=months, loc="bottom", cellLoc="center")

    if savepath:
        fig.savefig(savepath, dpi=300)

    return fig