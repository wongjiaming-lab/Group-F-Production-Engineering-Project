import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os

st.set_page_config(page_title="IPR + VLP Operating Point", layout="wide")

st.title("Well Production Performance Analyzer")
st.subheader("Combined IPR and VLP Method 1")

EXCEL_FILE = "VLP Method 1(1).xlsx"
VLP_FLOW_RATES = [50, 100, 200, 600]

@st.cache_data
def load_vlp_data():
    df = pd.read_excel(EXCEL_FILE)
    df.columns = df.columns.str.strip()
    return df

if not os.path.exists(EXCEL_FILE):
    st.error(f"Excel file not found: {EXCEL_FILE}")
    st.stop()

df = load_vlp_data()

required_columns = [
    "Flow Rate (bbl/day)",
    "GLR (Mscf/bbl)",
    "THP (psi)",
    "Tubing Depth (ft)",
    "THP Equivalent Depth (ft)",
    "Pwf equivalent Depth (ft)",
    "Pwf (psi)"
]

missing_columns = [col for col in required_columns if col not in df.columns]
if missing_columns:
    st.error("Missing columns in Excel file:")
    st.write(missing_columns)
    st.stop()

st.sidebar.header("IPR Input Parameters")

pr = st.sidebar.number_input("Reservoir Pressure, Pr (psi)", min_value=0.0, value=3000.0, step=100.0)
q_test = st.sidebar.number_input("Test Flow Rate, q (bbl/day)", min_value=0.0, value=500.0, step=50.0)
pwf_test = st.sidebar.number_input("Test Bottomhole Flowing Pressure, Pwf (psi)", min_value=0.0, value=2000.0, step=100.0)

st.sidebar.header("VLP Method 1 Input Parameters")

glr = st.sidebar.selectbox("Gas-Liquid Ratio, GLR (MSCF/bbl)", sorted(df["GLR (Mscf/bbl)"].dropna().unique()))
thp = st.sidebar.selectbox("Tubing Head Pressure, THP (psi)", sorted(df["THP (psi)"].dropna().unique()))
tubing_depth = st.sidebar.selectbox("Tubing Depth (ft)", sorted(df["Tubing Depth (ft)"].dropna().unique()))

if pwf_test >= pr:
    st.error("For IPR calculation, Pwf must be lower than Pr.")
    st.stop()

if q_test <= 0:
    st.error("Test flow rate must be greater than zero.")
    st.stop()

# -------------------------
# IPR Calculation
# -------------------------
pi = q_test / (pr - pwf_test)
qmax = pi * pr

q_ipr = np.linspace(0, qmax, 500)
pwf_ipr = pr - (q_ipr / pi)

# -------------------------
# VLP Calculation
# -------------------------
vlp_results = []
missing_vlp = []

for q in VLP_FLOW_RATES:
    selected = df[
        (df["Flow Rate (bbl/day)"] == q) &
        (df["GLR (Mscf/bbl)"] == glr) &
        (df["THP (psi)"] == thp) &
        (df["Tubing Depth (ft)"] == tubing_depth)
    ]

    if selected.empty:
        missing_vlp.append(q)
        continue

    row = selected.iloc[0]

    if pd.isna(row["Pwf (psi)"]):
        missing_vlp.append(q)
        continue

    vlp_results.append({
        "Flow Rate, q (bbl/day)": q,
        "THP Equivalent Depth (ft)": row["THP Equivalent Depth (ft)"],
        "Pwf Equivalent Depth (ft)": row["Pwf equivalent Depth (ft)"],
        "Pwf (psi)": row["Pwf (psi)"]
    })

if not vlp_results:
    st.error("No valid VLP data found for the selected GLR, THP, and tubing depth.")
    st.stop()

vlp_df = pd.DataFrame(vlp_results).sort_values("Flow Rate, q (bbl/day)")

if missing_vlp:
    st.warning(f"Missing VLP data for q = {missing_vlp} bbl/day.")

q_vlp = vlp_df["Flow Rate, q (bbl/day)"].values
pwf_vlp = vlp_df["Pwf (psi)"].values

# -------------------------
# Smooth VLP Curve Fitting
# -------------------------
degree = min(3, len(q_vlp) - 1)

if len(q_vlp) < 3:
    st.error("At least 3 valid VLP points are recommended to generate a smooth VLP curve.")
    st.stop()

vlp_coefficients = np.polyfit(q_vlp, pwf_vlp, degree)
vlp_poly = np.poly1d(vlp_coefficients)

q_min = q_vlp.min()
q_max = min(q_vlp.max(), qmax)

q_smooth = np.linspace(q_min, q_max, 1000)
pwf_vlp_smooth = vlp_poly(q_smooth)
pwf_ipr_smooth = pr - (q_smooth / pi)

# -------------------------
# Operating Point Calculation
# -------------------------
def ipr_pressure(q):
    return pr - (q / pi)

def vlp_pressure(q):
    return vlp_poly(q)

def difference(q):
    return ipr_pressure(q) - vlp_pressure(q)

operating_point_found = False
q_op = None
pwf_op = None

diff_values = difference(q_smooth)

for i in range(len(q_smooth) - 1):
    if diff_values[i] == 0 or diff_values[i] * diff_values[i + 1] < 0:
        q_low = q_smooth[i]
        q_high = q_smooth[i + 1]

        for _ in range(50):
            q_mid = (q_low + q_high) / 2

            if difference(q_low) * difference(q_mid) <= 0:
                q_high = q_mid
            else:
                q_low = q_mid

        q_op = (q_low + q_high) / 2
        pwf_op = ipr_pressure(q_op)
        operating_point_found = True
        break

# -------------------------
# Display Results
# -------------------------
st.subheader("IPR Results")

col1, col2 = st.columns(2)
col1.metric("Productivity Index, PI", f"{pi:.4f} bbl/day/psi")
col2.metric("Maximum Flow Rate, qmax", f"{qmax:.2f} bbl/day")

st.subheader("VLP Method 1 Results")
st.dataframe(vlp_df, use_container_width=True)

st.subheader("Combined IPR and VLP Graph")

fig, ax = plt.subplots(figsize=(9, 6))

ax.plot(q_ipr, pwf_ipr, label="IPR Curve - PI Method")
ax.plot(q_smooth, pwf_vlp_smooth, label="Smooth VLP Curve - Method 1")
ax.scatter(q_vlp, pwf_vlp, label="VLP Data Points")

if operating_point_found:
    ax.scatter(q_op, pwf_op, s=120, label="Operating Point")
    ax.annotate(
        f"Operating Point\nq = {q_op:.2f} bbl/day\nPwf = {pwf_op:.2f} psi",
        xy=(q_op, pwf_op),
        xytext=(q_op + 20, pwf_op + 100),
        arrowprops=dict(arrowstyle="->")
    )

ax.set_xlabel("Flow Rate, q (bbl/day)")
ax.set_ylabel("Bottomhole Flowing Pressure, Pwf (psi)")
ax.set_title("Combined IPR and VLP Curve")
ax.grid(True)
ax.legend()

st.pyplot(fig)

if operating_point_found:
    st.success("Operating point found.")

    col3, col4 = st.columns(2)
    col3.metric("Operating Flow Rate", f"{q_op:.2f} bbl/day")
    col4.metric("Operating Pwf", f"{pwf_op:.2f} psi")
else:
    st.warning(
        "No operating point was found within the available VLP flow-rate range. "
        "Try changing IPR input values, GLR, THP, or tubing depth."
    )

st.markdown("### Formula Used")
st.latex(r"PI = \frac{q}{P_r - P_{wf}}")
st.latex(r"q_{max} = PI \times P_r")
st.latex(r"P_{wf} = P_r - \frac{q}{PI}")

st.markdown("### Note")
st.write(
    "The VLP curve is generated using polynomial curve fitting from available VLP data points. "
    "The operating point is calculated numerically by finding the intersection between the IPR curve and the smooth VLP curve."
)