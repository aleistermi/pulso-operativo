"""Streamlit analytics dashboard for BambooHR timesheet data."""

import io
import os
import json

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

LOGO_PATH = os.path.join(os.path.dirname(__file__), "logos_entropia")
st.set_page_config(page_title="Pulso Operativo", page_icon=os.path.join(LOGO_PATH, "Flor-negra (2).ico"), layout="wide")

# ── Theme / palette ──
SLATE = "#334155"
STONE = "#78716c"
ACCENT = "#1e293b"
BAR_COLOR = "#475569"
BAR_HIGHLIGHT = "#0f172a"
MUTED = "#94a3b8"
BG_CHART = "rgba(0,0,0,0)"
PALETTE = [
    "#2d6a8f", "#b5651d", "#5a8a5a", "#8b5e83", "#c4a35a",
    "#3d8b8b", "#a05050", "#6878a0", "#7a9a3a", "#9b7050",
    "#4a7a7a", "#a08060", "#6a5a8a", "#8a6a5a", "#5a7a9a",
    "#8a4a4a", "#4a8a6a", "#8a8a4a", "#6a4a6a", "#5a6a4a",
]

PLOTLY_LAYOUT = dict(
    paper_bgcolor=BG_CHART,
    plot_bgcolor=BG_CHART,
    font=dict(family="Inter, system-ui, sans-serif", color=SLATE, size=13),
    title_font=dict(size=16, color=ACCENT),
    margin=dict(l=20, r=60, t=50, b=20),
    hovermode="x unified",
)

# ── Custom CSS ──
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    .stApp { font-family: 'Inter', system-ui, sans-serif; }
    [data-testid="stMetric"] {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 16px 20px;
    }
    [data-testid="stMetricLabel"] { font-size: 0.8rem; color: #64748b; font-weight: 500; }
    [data-testid="stMetricValue"] { font-size: 1.6rem; color: #0f172a; font-weight: 700; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        background: #f1f5f9;
        border-radius: 8px;
        padding: 8px 20px;
        font-weight: 500;
        color: #475569;
    }
    .stTabs [aria-selected="true"] {
        background: #0f172a !important;
        color: white !important;
    }
    .stDivider { margin: 0.5rem 0; }
    h1, h2, h3 { color: #0f172a; font-weight: 700; }
    [data-testid="stSidebar"] { padding-top: 1rem; }
    .logo-container { padding: 0 1rem 1rem 1rem; border-bottom: 1px solid #e2e8f0; margin-bottom: 1rem; }
</style>
""", unsafe_allow_html=True)


# ── Load & enrich data ──
@st.cache_data
def load_data():
    csv_path = os.path.join(DATA_DIR, "timesheet_entries.csv")
    emp_path = os.path.join(DATA_DIR, "employees.json")
    if not os.path.exists(csv_path):
        return pd.DataFrame(), {}

    df = pd.read_csv(csv_path)
    df["date"] = pd.to_datetime(df["date"])
    df["week"] = df["date"].dt.isocalendar().week.astype(int)
    df["week_start"] = df["date"].dt.to_period("W").apply(lambda p: p.start_time)
    df["weekday"] = df["date"].dt.day_name()
    df["is_weekday"] = df["date"].dt.dayofweek < 5
    df["project"] = df["projectInfo.project.name"].fillna("Sin proyecto")

    dept_map = {}
    if os.path.exists(emp_path):
        with open(emp_path) as f:
            employees = json.load(f)
        dept_map = {str(e["id"]): e.get("department") or "Sin departamento" for e in employees}

    df["department"] = df["employeeId"].astype(str).map(dept_map).fillna("Sin departamento")

    # Descontar 1 hr de comida en entries de 6+ hrs
    df["hours_raw"] = df["hours"]
    df["hours"] = df["hours"].apply(lambda h: max(h - 1, 0) if h >= 6 else h)

    # Salary & hourly cost
    sal_path = os.path.join(DATA_DIR, "salaries.json")
    hourly_map = {}
    if os.path.exists(sal_path):
        with open(sal_path) as f:
            salaries = json.load(f)
        for e in salaries:
            rate_str = (e.get("payRate") or "").strip()
            try:
                num = rate_str.replace(",", "").split()[0]
                rate = float(num)
            except (ValueError, IndexError):
                rate = 0
            if rate > 0:
                hourly_map[str(e["id"])] = rate / 173.33

    df["hourly_rate"] = df["employeeId"].astype(str).map(hourly_map).fillna(0)
    df["cost"] = df["hours"] * df["hourly_rate"]

    return df, dept_map


# No toolbar on any chart
PLOTLY_CONFIG = {"displayModeBar": False}


df_raw, dept_map = load_data()

EXCLUDED_PEOPLE = {
    "Andrés Ponce de León Rosas", "Max Lugo Delgadillo", "Aleister Montfort Ibieta",
}
df_raw = df_raw[~df_raw["employeeName"].isin(EXCLUDED_PEOPLE)]

if df_raw.empty:
    st.warning("No hay datos. Corre `python fetch_timesheets.py` primero.")
    st.stop()


# ══════════════════════════════════════════════
# HEADER + FILTERS
# ══════════════════════════════════════════════
import base64

def get_logo_b64(filename):
    path = os.path.join(LOGO_PATH, filename)
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

logo_b64 = get_logo_b64("entropia negro (7).png")
st.markdown(
    f'<div style="margin-bottom:6px;">'
    f'<img src="data:image/png;base64,{logo_b64}" height="22" style="opacity:0.85;">'
    f'</div>'
    f'<div style="font-size:1.35rem;font-weight:700;color:#0f172a;letter-spacing:-0.02em;margin-bottom:2px;">'
    f'Pulso Operativo</div>',
    unsafe_allow_html=True,
)

f1, f2, f3, f4 = st.columns([2, 2, 2, 2])

with f1:
    min_date = df_raw["date"].min().date()
    max_date = df_raw["date"].max().date()
    date_range = st.date_input("Periodo", value=(min_date, max_date), min_value=min_date, max_value=max_date)

with f2:
    all_depts = sorted(df_raw["department"].unique())
    selected_dept = st.selectbox("Departamento", ["Todos"] + all_depts)

with f3:
    all_projects = sorted(df_raw["project"].unique())
    selected_project = st.selectbox("Proyecto", ["Todos"] + all_projects)

with f4:
    all_employees = sorted(df_raw["employeeName"].dropna().unique())
    selected_employee = st.selectbox("Persona", ["Todos"] + all_employees)

# Apply filters
df = df_raw.copy()
if len(date_range) == 2:
    df = df[(df["date"].dt.date >= date_range[0]) & (df["date"].dt.date <= date_range[1])]
if selected_dept != "Todos":
    df = df[df["department"] == selected_dept]
if selected_project != "Todos":
    df = df[df["project"] == selected_project]
if selected_employee != "Todos":
    df = df[df["employeeName"] == selected_employee]

# Weekday-only view for charts
df_wd = df[df["is_weekday"]]

st.divider()

# ══════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════
tab_overview, tab_person, tab_project, tab_dept, tab_costs, tab_report = st.tabs(
    ["Overview", "Por Persona", "Por Proyecto", "Por Departamento", "Costos", "Reporte"]
)


# ──────────────────────────────────────────────
# TAB 1: OVERVIEW
# ──────────────────────────────────────────────
with tab_overview:
    # KPIs
    k1, k2, k3, k4 = st.columns(4)
    total_hours = df_wd["hours"].sum()
    n_employees = df_wd["employeeName"].nunique()
    n_projects = df_wd[df_wd["project"] != "Sin proyecto"]["project"].nunique()
    avg_per_emp = df_wd.groupby("employeeName")["hours"].sum().mean() if n_employees > 0 else 0

    k1.metric("Horas totales", f"{total_hours:,.0f}")
    k2.metric("Personas activas", n_employees)
    k3.metric("Proyectos", n_projects)
    k4.metric("Promedio hrs / persona", f"{avg_per_emp:,.1f}")

    st.markdown("")

    # ── Week-over-week comparison (main chart) ──
    weekly_totals = df_wd.groupby("week_start").agg(
        hours=("hours", "sum"),
        people=("employeeName", "nunique"),
    ).reset_index().sort_values("week_start")
    weekly_totals["week_label"] = weekly_totals["week_start"].dt.strftime("%d %b")
    weekly_totals["avg_per_person"] = weekly_totals["hours"] / weekly_totals["people"]

    if len(weekly_totals) >= 2:
        prev = weekly_totals.iloc[-2]["hours"]
        curr = weekly_totals.iloc[-1]["hours"]
        delta_pct = ((curr - prev) / prev * 100) if prev > 0 else 0
        delta_label = f"{delta_pct:+.1f}% vs semana anterior"
    else:
        delta_label = ""

    fig_weeks = go.Figure()
    fig_weeks.add_trace(go.Bar(
        x=weekly_totals["week_label"],
        y=weekly_totals["hours"],
        marker_color=BAR_COLOR,
        text=weekly_totals["hours"].apply(lambda x: f"{x:,.0f}"),
        textposition="outside",
        textfont=dict(size=12, color=SLATE),
        cliponaxis=False,
        hovertemplate="<b>%{x}</b><br>Horas: %{y:,.1f}<extra></extra>",
    ))
    fig_weeks.update_layout(
        **PLOTLY_LAYOUT,
        title=f"Horas por semana  <span style='font-size:12px;color:{MUTED}'>{delta_label}</span>",
        xaxis_title="", yaxis_title="Horas",
        showlegend=False,
    )
    st.plotly_chart(fig_weeks, use_container_width=True, config=PLOTLY_CONFIG)

    # ── Two columns: Top N people + Projects bar ──
    c1, c2 = st.columns(2)

    with c1:
        n_top = st.slider("Top personas", min_value=5, max_value=min(40, n_employees), value=min(10, n_employees), key="top_n")
        by_emp = df_wd.groupby("employeeName")["hours"].sum().sort_values(ascending=True).tail(n_top).reset_index()

        fig_emp = go.Figure(go.Bar(
            x=by_emp["hours"],
            y=by_emp["employeeName"],
            orientation="h",
            marker_color=BAR_COLOR,
            text=by_emp["hours"].apply(lambda x: f"{x:,.1f}"),
            textposition="outside",
            textfont=dict(size=11),
            cliponaxis=False,
        ))
        fig_emp.update_layout(
            **PLOTLY_LAYOUT,
            title=f"Top {n_top} personas por horas",
            yaxis_title="", xaxis_title="Horas",
            height=max(350, n_top * 32),
        )
        st.plotly_chart(fig_emp, use_container_width=True, config=PLOTLY_CONFIG)

    with c2:
        by_proj = df_wd[df_wd["project"] != "Sin proyecto"].groupby("project")["hours"].sum().sort_values(ascending=True).reset_index()

        fig_proj = go.Figure(go.Bar(
            x=by_proj["hours"],
            y=by_proj["project"],
            orientation="h",
            marker_color=BAR_COLOR,
            text=by_proj["hours"].apply(lambda x: f"{x:,.1f}"),
            textposition="outside",
            textfont=dict(size=11),
            cliponaxis=False,
        ))
        fig_proj.update_layout(
            **PLOTLY_LAYOUT,
            title="Horas por proyecto",
            yaxis_title="", xaxis_title="Horas",
            height=max(350, len(by_proj) * 32),
        )
        st.plotly_chart(fig_proj, use_container_width=True, config=PLOTLY_CONFIG)

    # ── Daily hours (weekdays only), tucked below ──
    with st.expander("Detalle diario (L-V)"):
        daily = df_wd.groupby("date")["hours"].sum().reset_index()
        fig_daily = go.Figure(go.Bar(
            x=daily["date"], y=daily["hours"],
            marker_color=BAR_COLOR,
        ))
        fig_daily.update_layout(
            **PLOTLY_LAYOUT,
            title="Horas por dia (solo entre semana)",
            xaxis_title="", yaxis_title="Horas",
        )
        st.plotly_chart(fig_daily, use_container_width=True, config=PLOTLY_CONFIG)

    # ── Overtime: +40 hrs/semana ──
    weekly_per_person = df_wd.groupby(["employeeName", "week_start"])["hours"].sum().reset_index()
    overtime = weekly_per_person[weekly_per_person["hours"] > 40].copy()

    if not overtime.empty:
        overtime = overtime.sort_values("hours", ascending=False)
        overtime["week_label"] = overtime["week_start"].dt.strftime("%d %b")

        st.markdown("")
        st.markdown(f"#### Overtime: +40 hrs/semana  <span style='font-size:13px;color:{MUTED}'>{len(overtime)} instancias, {overtime['employeeName'].nunique()} personas</span>", unsafe_allow_html=True)

        # Bar: who has the most overtime instances
        ot_count = overtime.groupby("employeeName").agg(
            instancias=("hours", "count"),
            max_hrs=("hours", "max"),
            avg_hrs=("hours", "mean"),
        ).sort_values("avg_hrs", ascending=True).reset_index()

        ot_count["base"] = 40.0
        ot_count["excess"] = ot_count["avg_hrs"] - 40.0

        fig_ot = go.Figure()
        fig_ot.add_trace(go.Bar(
            x=ot_count["base"],
            y=ot_count["employeeName"],
            orientation="h",
            marker_color=BAR_COLOR,
            name="Base (40 hrs)",
            showlegend=False,
        ))
        fig_ot.add_trace(go.Bar(
            x=ot_count["excess"],
            y=ot_count["employeeName"],
            orientation="h",
            marker_color="#b91c1c",
            name="Exceso",
            text=ot_count.apply(lambda r: f"{r['avg_hrs']:.0f} hrs ({int(r['instancias'])}x)", axis=1),
            textposition="outside",
            textfont=dict(size=11),
            cliponaxis=False,
        ))
        fig_ot.update_layout(
            **PLOTLY_LAYOUT,
            title="Promedio semanal de quienes exceden 40 hrs",
            yaxis_title="", xaxis_title="Horas promedio/semana",
            height=max(300, len(ot_count) * 30),
            barmode="stack",
            showlegend=False,
        )
        fig_ot.add_vline(x=40, line_dash="dot", line_color="#b91c1c", annotation_text="40 hrs", annotation_position="top", annotation_font_color="#b91c1c")
        st.plotly_chart(fig_ot, use_container_width=True, config=PLOTLY_CONFIG)

        with st.expander("Detalle overtime"):
            ot_display = overtime[["employeeName", "week_label", "hours"]].rename(
                columns={"employeeName": "Persona", "week_label": "Semana", "hours": "Horas"}
            )
            st.dataframe(ot_display, use_container_width=True, hide_index=True)


# ──────────────────────────────────────────────
# TAB 2: POR PERSONA
# ──────────────────────────────────────────────
with tab_person:
    person = st.selectbox("Selecciona una persona", sorted(df["employeeName"].dropna().unique()), key="person_select")
    df_person = df_wd[df_wd["employeeName"] == person]

    if df_person.empty:
        st.info("No hay datos para esta persona en el periodo seleccionado.")
    else:
        dept = df_person["department"].iloc[0]
        total_p = df_person["hours"].sum()
        days_active = df_person["date"].nunique()
        avg_daily = total_p / days_active if days_active > 0 else 0

        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Departamento", dept)
        p2.metric("Horas totales", f"{total_p:,.1f}")
        p3.metric("Dias activos", days_active)
        p4.metric("Promedio diario", f"{avg_daily:,.1f} hrs")

        st.markdown("")

        # Weekly breakdown
        weekly = df_person.groupby("week_start")["hours"].sum().reset_index().sort_values("week_start")
        weekly["week_label"] = weekly["week_start"].dt.strftime("%d %b")

        fig_weekly = go.Figure(go.Bar(
            x=weekly["week_label"], y=weekly["hours"],
            marker_color=BAR_COLOR,
            text=weekly["hours"].apply(lambda x: f"{x:,.1f}"),
            textposition="outside",
            textfont=dict(size=12),
            cliponaxis=False,
        ))
        fig_weekly.update_layout(
            **PLOTLY_LAYOUT,
            title=f"Semanas de {person}",
            xaxis_title="Semana (inicio)", yaxis_title="Horas",
        )
        st.plotly_chart(fig_weekly, use_container_width=True, config=PLOTLY_CONFIG)

        pc1, pc2 = st.columns(2)

        with pc1:
            # Weekday pattern
            weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
            wd = df_person.groupby("weekday")["hours"].sum().reindex(weekday_order, fill_value=0).reset_index()
            wd.columns = ["weekday", "hours"]
            fig_wd = go.Figure(go.Bar(
                x=wd["weekday"], y=wd["hours"],
                marker_color=BAR_COLOR,
                text=wd["hours"].apply(lambda x: f"{x:,.1f}"),
                textposition="outside",
                cliponaxis=False,
            ))
            fig_wd.update_layout(**PLOTLY_LAYOUT, title="Horas por dia de la semana", xaxis_title="", yaxis_title="Horas")
            st.plotly_chart(fig_wd, use_container_width=True, config=PLOTLY_CONFIG)

        with pc2:
            # Projects bar (not pie)
            proj_person = df_person[df_person["project"] != "Sin proyecto"].groupby("project")["hours"].sum().sort_values(ascending=True).reset_index()
            if not proj_person.empty:
                fig_pp = go.Figure(go.Bar(
                    x=proj_person["hours"], y=proj_person["project"],
                    orientation="h",
                    marker_color=BAR_COLOR,
                    text=proj_person["hours"].apply(lambda x: f"{x:,.1f}"),
                    textposition="outside",
                    cliponaxis=False,
                ))
                fig_pp.update_layout(**PLOTLY_LAYOUT, title="Proyectos", yaxis_title="", xaxis_title="Horas")
                st.plotly_chart(fig_pp, use_container_width=True, config=PLOTLY_CONFIG)
            else:
                st.info("No hay proyectos asignados.")

        with st.expander("Detalle diario"):
            detail = df_person[["date", "hours", "project", "start", "end", "note"]].sort_values("date", ascending=False).copy()
            detail["date"] = detail["date"].dt.strftime("%Y-%m-%d")
            st.dataframe(detail, use_container_width=True, hide_index=True)


# ──────────────────────────────────────────────
# TAB 3: POR PROYECTO
# ──────────────────────────────────────────────
with tab_project:
    projects_with_data = sorted(df_wd[df_wd["project"] != "Sin proyecto"]["project"].unique())
    if not projects_with_data:
        st.info("No hay proyectos con horas registradas en este periodo.")
    else:
        project = st.selectbox("Selecciona un proyecto", projects_with_data, key="project_select")
        df_proj = df_wd[df_wd["project"] == project]

        total_proj = df_proj["hours"].sum()
        n_contributors = df_proj["employeeName"].nunique()
        proj_days = df_proj["date"].nunique()

        pr1, pr2, pr3 = st.columns(3)
        pr1.metric("Horas totales", f"{total_proj:,.1f}")
        pr2.metric("Contribuidores", n_contributors)
        pr3.metric("Dias con actividad", proj_days)

        st.markdown("")

        # Stacked weekly contribution
        proj_weekly = df_proj.groupby(["week_start", "employeeName"])["hours"].sum().reset_index()
        proj_weekly["week_label"] = proj_weekly["week_start"].dt.strftime("%d %b")
        proj_weekly = proj_weekly.sort_values("week_start")

        fig_proj_stack = px.bar(
            proj_weekly, x="week_label", y="hours", color="employeeName",
            title=f"Contribucion semanal",
            color_discrete_sequence=PALETTE,
            barmode="stack",
        )
        fig_proj_stack.update_layout(
            **PLOTLY_LAYOUT, xaxis_title="Semana", yaxis_title="Horas", legend_title="",
            legend=dict(orientation="h", yanchor="top", y=-0.25, xanchor="left", x=0, font_size=11),
            bargap=0.5 if len(proj_weekly["week_label"].unique()) <= 2 else 0.2,
        )
        st.plotly_chart(fig_proj_stack, use_container_width=True, config=PLOTLY_CONFIG)

        # Hours per contributor (horizontal bar)
        by_contrib = df_proj.groupby("employeeName")["hours"].sum().sort_values(ascending=True).reset_index()
        fig_contrib = go.Figure(go.Bar(
            x=by_contrib["hours"], y=by_contrib["employeeName"],
            orientation="h",
            marker_color=BAR_COLOR,
            text=by_contrib["hours"].apply(lambda x: f"{x:,.1f}"),
            textposition="outside",
            cliponaxis=False,
        ))
        fig_contrib.update_layout(
            **PLOTLY_LAYOUT,
            title="Horas por persona",
            yaxis_title="", xaxis_title="Horas",
            height=max(300, len(by_contrib) * 35),
        )
        st.plotly_chart(fig_contrib, use_container_width=True, config=PLOTLY_CONFIG)

        with st.expander("Detalle diario"):
            detail_proj = df_proj[["date", "employeeName", "hours", "start", "end", "note"]].sort_values("date", ascending=False).copy()
            detail_proj["date"] = detail_proj["date"].dt.strftime("%Y-%m-%d")
            st.dataframe(detail_proj, use_container_width=True, hide_index=True)


# ──────────────────────────────────────────────
# TAB 4: POR DEPARTAMENTO
# ──────────────────────────────────────────────
with tab_dept:
    dept_sel = st.selectbox("Selecciona un departamento", sorted(df["department"].unique()), key="dept_select")
    df_dept = df_wd[df_wd["department"] == dept_sel]

    if df_dept.empty:
        st.info("No hay datos para este departamento en el periodo seleccionado.")
    else:
        total_d = df_dept["hours"].sum()
        n_emp_d = df_dept["employeeName"].nunique()
        n_proj_d = df_dept[df_dept["project"] != "Sin proyecto"]["project"].nunique()

        d1, d2, d3 = st.columns(3)
        d1.metric("Horas totales", f"{total_d:,.1f}")
        d2.metric("Personas", n_emp_d)
        d3.metric("Proyectos", n_proj_d)

        st.markdown("")

        # Weekly stacked by employee
        dept_weekly = df_dept.groupby(["week_start", "employeeName"])["hours"].sum().reset_index()
        dept_weekly["week_label"] = dept_weekly["week_start"].dt.strftime("%d %b")
        dept_weekly = dept_weekly.sort_values("week_start")

        fig_dept_stack = px.bar(
            dept_weekly, x="week_label", y="hours", color="employeeName",
            title=f"Horas semanales del equipo",
            color_discrete_sequence=PALETTE,
            barmode="stack",
        )
        fig_dept_stack.update_layout(
            **PLOTLY_LAYOUT, xaxis_title="Semana", yaxis_title="Horas", legend_title="",
            legend=dict(orientation="h", yanchor="top", y=-0.25, xanchor="left", x=0, font_size=11),
            bargap=0.5 if len(dept_weekly["week_label"].unique()) <= 2 else 0.2,
        )
        st.plotly_chart(fig_dept_stack, use_container_width=True, config=PLOTLY_CONFIG)

        dc1, dc2 = st.columns(2)

        with dc1:
            dept_by_emp = df_dept.groupby("employeeName")["hours"].sum().sort_values(ascending=True).reset_index()
            fig_de = go.Figure(go.Bar(
                x=dept_by_emp["hours"], y=dept_by_emp["employeeName"],
                orientation="h",
                marker_color=BAR_COLOR,
                text=dept_by_emp["hours"].apply(lambda x: f"{x:,.1f}"),
                textposition="outside",
                cliponaxis=False,
            ))
            fig_de.update_layout(**PLOTLY_LAYOUT, title="Horas por persona", yaxis_title="", xaxis_title="Horas",
                                 height=max(300, len(dept_by_emp) * 35))
            st.plotly_chart(fig_de, use_container_width=True, config=PLOTLY_CONFIG)

        with dc2:
            dept_by_proj = df_dept[df_dept["project"] != "Sin proyecto"].groupby("project")["hours"].sum().sort_values(ascending=True).reset_index()
            if not dept_by_proj.empty:
                fig_dp = go.Figure(go.Bar(
                    x=dept_by_proj["hours"], y=dept_by_proj["project"],
                    orientation="h",
                    marker_color=BAR_COLOR,
                    text=dept_by_proj["hours"].apply(lambda x: f"{x:,.1f}"),
                    textposition="outside",
                    cliponaxis=False,
                ))
                fig_dp.update_layout(**PLOTLY_LAYOUT, title="Proyectos del departamento", yaxis_title="", xaxis_title="Horas",
                                     height=max(300, len(dept_by_proj) * 35))
                st.plotly_chart(fig_dp, use_container_width=True, config=PLOTLY_CONFIG)
            else:
                st.info("No hay proyectos asignados.")

        # Heatmap
        weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        heat_data = df_dept.groupby(["employeeName", "weekday"])["hours"].sum().reset_index()
        heat_data["weekday"] = pd.Categorical(heat_data["weekday"], categories=weekday_order, ordered=True)
        heat_pivot = heat_data.pivot_table(index="employeeName", columns="weekday", values="hours", fill_value=0)
        heat_pivot = heat_pivot.reindex(columns=weekday_order, fill_value=0)

        if not heat_pivot.empty:
            fig_heat = px.imshow(
                heat_pivot, aspect="auto",
                color_continuous_scale=["#e2e8f0", "#1e40af", "#0f172a"],
                title="Heatmap: Persona x Dia",
                text_auto=".1f",
            )
            fig_heat.update_layout(
                **PLOTLY_LAYOUT, xaxis_title="", yaxis_title="",
                height=max(300, len(heat_pivot) * 35),
            )
            st.plotly_chart(fig_heat, use_container_width=True, config=PLOTLY_CONFIG)


# ──────────────────────────────────────────────
# TAB 5: COSTOS
# ──────────────────────────────────────────────
with tab_costs:
    # Only active people: those with timesheet entries in the period
    df_cost = df_wd[df_wd["hourly_rate"] > 0].copy()

    if df_cost.empty:
        st.info("No hay datos de costo. Verifica que salaries.json tenga salarios registrados.")
    else:
        total_cost = df_cost["cost"].sum()
        n_active = df_cost["employeeName"].nunique()
        n_proj_cost = df_cost[df_cost["project"] != "Sin proyecto"]["project"].nunique()
        avg_hourly = df_cost.groupby("employeeName")["hourly_rate"].first().mean()

        ck1, ck2, ck3 = st.columns(3)
        ck1.metric("Costo total periodo", f"${total_cost:,.0f}")
        ck2.metric("Proyectos", n_proj_cost)
        ck3.metric("Personas activas", n_active)

        st.markdown("")

        # ── Weekly cost trend ──
        weekly_cost = df_cost.groupby("week_start")["cost"].sum().reset_index().sort_values("week_start")
        weekly_cost["week_label"] = weekly_cost["week_start"].dt.strftime("%d %b")

        fig_wc = go.Figure(go.Bar(
            x=weekly_cost["week_label"], y=weekly_cost["cost"],
            marker_color=BAR_COLOR,
            text=weekly_cost["cost"].apply(lambda x: f"${x:,.0f}"),
            textposition="outside",
            textfont=dict(size=12),
            cliponaxis=False,
        ))
        fig_wc.update_layout(
            **PLOTLY_LAYOUT,
            title="Costo semanal total",
            xaxis_title="Semana", yaxis_title="MXN",
        )
        st.plotly_chart(fig_wc, use_container_width=True, config=PLOTLY_CONFIG)

        # ── Cost by project ──
        cost_by_proj = df_cost[df_cost["project"] != "Sin proyecto"].groupby("project")["cost"].sum().sort_values(ascending=True).reset_index()
        if not cost_by_proj.empty:
            fig_cp = go.Figure(go.Bar(
                x=cost_by_proj["cost"], y=cost_by_proj["project"],
                orientation="h",
                marker_color=BAR_COLOR,
                text=cost_by_proj["cost"].apply(lambda x: f"${x:,.0f}"),
                textposition="outside",
                textfont=dict(size=11),
                cliponaxis=False,
            ))
            fig_cp.update_layout(
                **PLOTLY_LAYOUT,
                title="Costo por proyecto",
                yaxis_title="", xaxis_title="MXN",
                height=max(350, len(cost_by_proj) * 32),
            )
            st.plotly_chart(fig_cp, use_container_width=True, config=PLOTLY_CONFIG)

        # ── Weekly cost by project (stacked) ──
        proj_weekly_cost = df_cost[df_cost["project"] != "Sin proyecto"].groupby(
            ["week_start", "project"]
        )["cost"].sum().reset_index()
        proj_weekly_cost["week_label"] = proj_weekly_cost["week_start"].dt.strftime("%d %b")
        proj_weekly_cost = proj_weekly_cost.sort_values("week_start")

        if not proj_weekly_cost.empty:
            fig_pwc = px.bar(
                proj_weekly_cost, x="week_label", y="cost", color="project",
                title="Costo semanal por proyecto",
                color_discrete_sequence=PALETTE,
                barmode="stack",
            )
            fig_pwc.update_layout(
                **PLOTLY_LAYOUT, xaxis_title="Semana", yaxis_title="MXN", legend_title="",
                legend=dict(orientation="h", yanchor="top", y=-0.25, xanchor="left", x=0, font_size=11),
                bargap=0.5 if len(proj_weekly_cost["week_label"].unique()) <= 2 else 0.2,
            )
            st.plotly_chart(fig_pwc, use_container_width=True, config=PLOTLY_CONFIG)


# ──────────────────────────────────────────────
# TAB 6: REPORTE SEMANAL
# ──────────────────────────────────────────────
with tab_report:
    all_weeks = df_raw[df_raw["is_weekday"]].groupby("week_start").size().reset_index(name="entries").sort_values("week_start", ascending=False)

    if all_weeks.empty:
        st.info("No hay semanas con datos disponibles.")
    else:
        week_options = {row["week_start"].strftime("%d %b %Y"): row["week_start"] for _, row in all_weeks.iterrows()}
        selected_week_label = st.selectbox("Semana", list(week_options.keys()), key="report_week")
        selected_week_start = week_options[selected_week_label]
        week_end = selected_week_start + pd.Timedelta(days=4)

        # Current and previous week data
        dfw = df_raw[(df_raw["week_start"] == selected_week_start) & (df_raw["is_weekday"])].copy()
        prev_week_start = selected_week_start - pd.Timedelta(days=7)
        dfp = df_raw[(df_raw["week_start"] == prev_week_start) & (df_raw["is_weekday"])].copy()

        # ── Core metrics ──
        w_hours = dfw["hours"].sum()
        w_people = dfw["employeeName"].nunique()
        w_projects = dfw[dfw["project"] != "Sin proyecto"]["project"].nunique()
        w_cost = dfw[dfw["hourly_rate"] > 0]["cost"].sum()
        w_avg_per_person = w_hours / w_people if w_people > 0 else 0

        p_hours = dfp["hours"].sum() if not dfp.empty else 0
        p_people = dfp["employeeName"].nunique() if not dfp.empty else 0
        p_cost = dfp[dfp["hourly_rate"] > 0]["cost"].sum() if not dfp.empty else 0
        p_avg_per_person = p_hours / p_people if p_people > 0 else 0

        def delta_str(curr, prev, fmt=",.0f", prefix="", is_pct=False):
            if prev == 0:
                return ""
            d = ((curr - prev) / prev * 100)
            arrow = "+" if d > 0 else ""
            return f" ({arrow}{d:.1f}%)"

        # Tasa de asignacion
        hrs_with_proj = dfw[dfw["project"] != "Sin proyecto"]["hours"].sum()
        assign_rate = (hrs_with_proj / w_hours * 100) if w_hours > 0 else 0
        p_hrs_with_proj = dfp[dfp["project"] != "Sin proyecto"]["hours"].sum() if not dfp.empty else 0
        p_assign_rate = (p_hrs_with_proj / p_hours * 100) if p_hours > 0 else 0

        # ── Cost by project with delta ──
        proj_cost_curr = dfw[(dfw["project"] != "Sin proyecto") & (dfw["hourly_rate"] > 0)].groupby("project").agg(
            cost=("cost", "sum"), hours=("hours", "sum"), people=("employeeName", "nunique")
        ).sort_values("cost", ascending=False).reset_index()

        proj_cost_prev = {}
        if not dfp.empty:
            pcp = dfp[(dfp["project"] != "Sin proyecto") & (dfp["hourly_rate"] > 0)].groupby("project")["cost"].sum()
            proj_cost_prev = pcp.to_dict()

        # ── Hours by project with delta ──
        proj_hrs_curr = dfw[dfw["project"] != "Sin proyecto"].groupby("project").agg(
            hours=("hours", "sum"), people=("employeeName", "nunique")
        ).sort_values("hours", ascending=False).reset_index()

        proj_hrs_prev = {}
        if not dfp.empty:
            php = dfp[dfp["project"] != "Sin proyecto"].groupby("project")["hours"].sum()
            proj_hrs_prev = php.to_dict()

        # ── Overtime ──
        person_hrs = dfw.groupby("employeeName")["hours"].sum().sort_values(ascending=False)
        overtime_people = person_hrs[person_hrs > 40]

        # ── Missing reporters ──
        emp_path = os.path.join(DATA_DIR, "employees.json")
        missing_names = []
        if os.path.exists(emp_path):
            with open(emp_path) as f:
                all_employees_list = json.load(f)
            all_emp_names = {e.get("displayName", "") for e in all_employees_list}
            active_names = set(dfw["employeeName"].unique())
            missing_names = sorted(all_emp_names - active_names - {""} - EXCLUDED_PEOPLE)

        # ── Hours by department ──
        dept_hrs = dfw.groupby("department").agg(
            hours=("hours", "sum"), people=("employeeName", "nunique")
        ).sort_values("hours", ascending=False).reset_index()

        dept_hrs_prev = {}
        if not dfp.empty:
            dhp = dfp.groupby("department")["hours"].sum()
            dept_hrs_prev = dhp.to_dict()

        # ══════════════════════════════════════
        # RENDER REPORT
        # ══════════════════════════════════════

        # ── KPI cards ──
        rk1, rk2, rk3, rk4, rk5 = st.columns(5)
        rk1.metric("Horas totales", f"{w_hours:,.0f}", delta=f"{((w_hours-p_hours)/p_hours*100):+.1f}%" if p_hours > 0 else None)
        rk2.metric("Costo total", f"${w_cost:,.0f}", delta=f"{((w_cost-p_cost)/p_cost*100):+.1f}%" if p_cost > 0 else None)
        rk3.metric("Personas activas", w_people, delta=f"{w_people - p_people:+d}" if p_people > 0 else None)
        rk4.metric("Promedio hrs/persona", f"{w_avg_per_person:,.1f}", delta=f"{((w_avg_per_person-p_avg_per_person)/p_avg_per_person*100):+.1f}%" if p_avg_per_person > 0 else None)
        rk5.metric("Tasa de asignacion", f"{assign_rate:.0f}%", delta=f"{assign_rate - p_assign_rate:+.1f}pp" if p_hours > 0 else None)

        st.markdown("")

        # ── Report body ──
        report_lines = []
        report_lines.append(f"# Reporte Semanal")
        report_lines.append(f"**{selected_week_start.strftime('%d %b')} — {week_end.strftime('%d %b %Y')}**")
        report_lines.append("")

        # Summary table
        report_lines.append("## Snapshot")
        report_lines.append("")
        report_lines.append("| Indicador | Esta semana | Semana anterior | Cambio |")
        report_lines.append("|:--|--:|--:|--:|")
        report_lines.append(f"| Horas totales | {w_hours:,.0f} | {p_hours:,.0f} | {((w_hours-p_hours)/p_hours*100):+.1f}% |" if p_hours > 0 else f"| Horas totales | {w_hours:,.0f} | — | — |")
        report_lines.append(f"| Costo total | ${w_cost:,.0f} | ${p_cost:,.0f} | {((w_cost-p_cost)/p_cost*100):+.1f}% |" if p_cost > 0 else f"| Costo total | ${w_cost:,.0f} | — | — |")
        report_lines.append(f"| Personas activas | {w_people} | {p_people} | {w_people - p_people:+d} |" if p_people > 0 else f"| Personas activas | {w_people} | — | — |")
        report_lines.append(f"| Promedio hrs/persona | {w_avg_per_person:,.1f} | {p_avg_per_person:,.1f} | {((w_avg_per_person-p_avg_per_person)/p_avg_per_person*100):+.1f}% |" if p_avg_per_person > 0 else f"| Promedio hrs/persona | {w_avg_per_person:,.1f} | — | — |")
        report_lines.append(f"| Tasa de asignacion | {assign_rate:.0f}% | {p_assign_rate:.0f}% | {assign_rate - p_assign_rate:+.1f}pp |" if p_hours > 0 else f"| Tasa de asignacion | {assign_rate:.0f}% | — | — |")
        report_lines.append(f"| Proyectos activos | {w_projects} | — | — |")
        report_lines.append("")

        # Cost by project with delta
        report_lines.append("## Costo por Proyecto")
        report_lines.append("")
        if not proj_cost_curr.empty:
            report_lines.append("| Proyecto | Costo | Horas | Personas | vs Anterior |")
            report_lines.append("|:--|--:|--:|--:|--:|")
            for _, r in proj_cost_curr.iterrows():
                prev_c = proj_cost_prev.get(r["project"], 0)
                if prev_c > 0:
                    d = ((r["cost"] - prev_c) / prev_c * 100)
                    delta = f"{d:+.1f}%"
                else:
                    delta = "nuevo" if prev_c == 0 else "—"
                report_lines.append(f"| {r['project']} | ${r['cost']:,.0f} | {r['hours']:,.1f} | {int(r['people'])} | {delta} |")
        else:
            report_lines.append("Sin datos de costo")
        report_lines.append("")

        # Hours by project with delta
        report_lines.append("## Horas por Proyecto")
        report_lines.append("")
        if not proj_hrs_curr.empty:
            report_lines.append("| Proyecto | Horas | Personas | vs Anterior |")
            report_lines.append("|:--|--:|--:|--:|")
            for _, r in proj_hrs_curr.iterrows():
                prev_h = proj_hrs_prev.get(r["project"], 0)
                if prev_h > 0:
                    d = ((r["hours"] - prev_h) / prev_h * 100)
                    delta = f"{d:+.1f}%"
                else:
                    delta = "nuevo"
                report_lines.append(f"| {r['project']} | {r['hours']:,.1f} | {int(r['people'])} | {delta} |")
        report_lines.append("")

        # Department breakdown
        if not dept_hrs.empty:
            report_lines.append("## Por Departamento")
            report_lines.append("")
            report_lines.append("| Departamento | Horas | Personas | vs Anterior |")
            report_lines.append("|:--|--:|--:|--:|")
            for _, r in dept_hrs.iterrows():
                prev_dh = dept_hrs_prev.get(r["department"], 0)
                if prev_dh > 0:
                    d = ((r["hours"] - prev_dh) / prev_dh * 100)
                    delta = f"{d:+.1f}%"
                else:
                    delta = "—"
                report_lines.append(f"| {r['department']} | {r['hours']:,.1f} | {int(r['people'])} | {delta} |")
            report_lines.append("")

        # Overtime
        if not overtime_people.empty:
            report_lines.append(f"## Overtime: +40 hrs ({len(overtime_people)} personas)")
            report_lines.append("")
            report_lines.append("| Persona | Horas | Exceso |")
            report_lines.append("|:--|--:|--:|")
            for name, hrs in overtime_people.items():
                report_lines.append(f"| {name} | {hrs:,.1f} | +{hrs - 40:,.1f} |")
            report_lines.append("")

        # Missing
        if missing_names:
            report_lines.append(f"## Sin registro de horas ({len(missing_names)})")
            report_lines.append("")
            # Show as comma-separated to save space
            report_lines.append(", ".join(missing_names))
            report_lines.append("")

        report_lines.append("---")
        report_lines.append(f"*Pulso Operativo — entropia.ai*")

        report_text = "\n".join(report_lines)

        # ── Display ──
        st.markdown(report_text)

        # ── PDF generation ──
        def generate_pdf():
            from fpdf import FPDF

            class ReportPDF(FPDF):
                def header(self):
                    logo_file = os.path.join(LOGO_PATH, "entropia negro (7).png")
                    if os.path.exists(logo_file):
                        self.image(logo_file, 10, 8, 30)
                    self.set_font("Helvetica", "B", 9)
                    self.set_text_color(100, 100, 100)
                    self.cell(0, 10, "Pulso Operativo", align="R")
                    self.ln(14)
                    self.set_draw_color(200, 200, 200)
                    self.line(10, self.get_y(), 200, self.get_y())
                    self.ln(4)

                def footer(self):
                    self.set_y(-15)
                    self.set_font("Helvetica", "I", 7)
                    self.set_text_color(150, 150, 150)
                    self.cell(0, 10, f"entropia.ai  |  Pagina {self.page_no()}", align="C")

                def section_title(self, title):
                    self.set_font("Helvetica", "B", 12)
                    self.set_text_color(15, 23, 42)
                    self.cell(0, 9, title)
                    self.ln(10)

                def add_table(self, headers, rows, col_widths=None):
                    if col_widths is None:
                        col_widths = [190 / len(headers)] * len(headers)
                    # Header
                    self.set_font("Helvetica", "B", 8)
                    self.set_fill_color(241, 245, 249)
                    self.set_text_color(51, 65, 85)
                    for i, h in enumerate(headers):
                        align = "L" if i == 0 else "R"
                        self.cell(col_widths[i], 7, h, border=0, fill=True, align=align)
                    self.ln()
                    # Rows
                    self.set_font("Helvetica", "", 8)
                    self.set_text_color(51, 65, 85)
                    for row in rows:
                        for i, val in enumerate(row):
                            align = "L" if i == 0 else "R"
                            self.cell(col_widths[i], 6, str(val), border=0, align=align)
                        self.ln()
                    self.ln(4)

            pdf = ReportPDF()
            pdf.set_auto_page_break(auto=True, margin=20)
            pdf.add_page()

            # Title
            pdf.set_font("Helvetica", "B", 18)
            pdf.set_text_color(15, 23, 42)
            pdf.cell(0, 10, "Reporte Semanal")
            pdf.ln(8)
            pdf.set_font("Helvetica", "", 11)
            pdf.set_text_color(100, 116, 139)
            pdf.cell(0, 7, f"{selected_week_start.strftime('%d %b')} - {week_end.strftime('%d %b %Y')}")
            pdf.ln(12)

            # KPI boxes
            kpi_data = [
                ("Horas totales", f"{w_hours:,.0f}"),
                ("Costo total", f"${w_cost:,.0f}"),
                ("Personas", str(w_people)),
                ("Prom hrs/persona", f"{w_avg_per_person:,.1f}"),
                ("Asignacion", f"{assign_rate:.0f}%"),
            ]
            box_w = 36
            x_start = 10
            for i, (label, value) in enumerate(kpi_data):
                x = x_start + i * (box_w + 2)
                pdf.set_fill_color(248, 250, 252)
                pdf.set_draw_color(226, 232, 240)
                pdf.rect(x, pdf.get_y(), box_w, 16, style="DF")
                pdf.set_xy(x + 2, pdf.get_y() + 1)
                pdf.set_font("Helvetica", "", 6)
                pdf.set_text_color(100, 116, 139)
                pdf.cell(box_w - 4, 4, label)
                pdf.set_xy(x + 2, pdf.get_y() + 4)
                pdf.set_font("Helvetica", "B", 11)
                pdf.set_text_color(15, 23, 42)
                pdf.cell(box_w - 4, 6, value)
            pdf.ln(22)

            # Snapshot table
            pdf.section_title("Snapshot")
            snapshot_rows = []
            if p_hours > 0:
                snapshot_rows.append(["Horas totales", f"{w_hours:,.0f}", f"{p_hours:,.0f}", f"{((w_hours-p_hours)/p_hours*100):+.1f}%"])
            else:
                snapshot_rows.append(["Horas totales", f"{w_hours:,.0f}", "—", "—"])
            if p_cost > 0:
                snapshot_rows.append(["Costo total", f"${w_cost:,.0f}", f"${p_cost:,.0f}", f"{((w_cost-p_cost)/p_cost*100):+.1f}%"])
            else:
                snapshot_rows.append(["Costo total", f"${w_cost:,.0f}", "—", "—"])
            if p_people > 0:
                snapshot_rows.append(["Personas activas", str(w_people), str(p_people), f"{w_people - p_people:+d}"])
            else:
                snapshot_rows.append(["Personas activas", str(w_people), "—", "—"])
            if p_avg_per_person > 0:
                snapshot_rows.append(["Prom hrs/persona", f"{w_avg_per_person:,.1f}", f"{p_avg_per_person:,.1f}", f"{((w_avg_per_person-p_avg_per_person)/p_avg_per_person*100):+.1f}%"])
            else:
                snapshot_rows.append(["Prom hrs/persona", f"{w_avg_per_person:,.1f}", "—", "—"])
            if p_hours > 0:
                snapshot_rows.append(["Tasa asignacion", f"{assign_rate:.0f}%", f"{p_assign_rate:.0f}%", f"{assign_rate - p_assign_rate:+.1f}pp"])
            else:
                snapshot_rows.append(["Tasa asignacion", f"{assign_rate:.0f}%", "—", "—"])
            pdf.add_table(["Indicador", "Esta semana", "Anterior", "Cambio"], snapshot_rows, [60, 45, 45, 40])

            # Cost by project
            if not proj_cost_curr.empty:
                pdf.section_title("Costo por Proyecto")
                cost_rows = []
                for _, r in proj_cost_curr.iterrows():
                    prev_c = proj_cost_prev.get(r["project"], 0)
                    delta = f"{((r['cost'] - prev_c) / prev_c * 100):+.1f}%" if prev_c > 0 else "nuevo"
                    cost_rows.append([r["project"], f"${r['cost']:,.0f}", f"{r['hours']:,.1f}", str(int(r["people"])), delta])
                pdf.add_table(["Proyecto", "Costo", "Horas", "Personas", "vs Ant."], cost_rows, [60, 35, 30, 30, 35])

            # Hours by project
            if not proj_hrs_curr.empty:
                pdf.section_title("Horas por Proyecto")
                hrs_rows = []
                for _, r in proj_hrs_curr.iterrows():
                    prev_h = proj_hrs_prev.get(r["project"], 0)
                    delta = f"{((r['hours'] - prev_h) / prev_h * 100):+.1f}%" if prev_h > 0 else "nuevo"
                    hrs_rows.append([r["project"], f"{r['hours']:,.1f}", str(int(r["people"])), delta])
                pdf.add_table(["Proyecto", "Horas", "Personas", "vs Ant."], hrs_rows, [70, 40, 40, 40])

            # Department
            if not dept_hrs.empty:
                pdf.section_title("Por Departamento")
                dept_rows = []
                for _, r in dept_hrs.iterrows():
                    prev_dh = dept_hrs_prev.get(r["department"], 0)
                    delta = f"{((r['hours'] - prev_dh) / prev_dh * 100):+.1f}%" if prev_dh > 0 else "—"
                    dept_rows.append([r["department"], f"{r['hours']:,.1f}", str(int(r["people"])), delta])
                pdf.add_table(["Departamento", "Horas", "Personas", "vs Ant."], dept_rows, [70, 40, 40, 40])

            # Overtime
            if not overtime_people.empty:
                pdf.section_title(f"Overtime +40 hrs ({len(overtime_people)} personas)")
                ot_rows = [[name, f"{hrs:,.1f}", f"+{hrs - 40:,.1f}"] for name, hrs in overtime_people.items()]
                pdf.add_table(["Persona", "Horas", "Exceso"], ot_rows, [90, 50, 50])

            # Missing
            if missing_names:
                pdf.section_title(f"Sin registro de horas ({len(missing_names)})")
                pdf.set_font("Helvetica", "", 8)
                pdf.set_text_color(71, 85, 105)
                pdf.multi_cell(190, 5, ", ".join(missing_names))

            buf = io.BytesIO()
            pdf.output(buf)
            return buf.getvalue()

        st.markdown("")
        col_dl1, col_dl2, col_dl3, _ = st.columns([1, 1, 1, 2])
        with col_dl1:
            pdf_bytes = generate_pdf()
            st.download_button(
                "Descargar PDF",
                data=pdf_bytes,
                file_name=f"reporte_semanal_{selected_week_start.strftime('%Y-%m-%d')}.pdf",
                mime="application/pdf",
            )
        with col_dl2:
            st.download_button(
                "Descargar .md",
                data=report_text,
                file_name=f"reporte_semanal_{selected_week_start.strftime('%Y-%m-%d')}.md",
                mime="text/markdown",
            )
        with col_dl3:
            plain_text = report_text.replace("**", "").replace("|", " | ").replace("# ", "").replace("#", "")
            st.download_button(
                "Descargar .txt",
                data=plain_text,
                file_name=f"reporte_semanal_{selected_week_start.strftime('%Y-%m-%d')}.txt",
                mime="text/plain",
            )
