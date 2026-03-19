"""Streamlit analytics dashboard for BambooHR timesheet data."""

import io
import os
import json
import requests
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# Force pure-Python JSON engine to avoid orjson circular-import bug
pio.json.config.default_engine = "json"

from bamboohr_client import BambooHRClient
from config import get_bamboohr_credentials, get_secret

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

LOGO_PATH = os.path.join(os.path.dirname(__file__), "logos_entropia")
st.set_page_config(page_title="Pulso Operativo", page_icon=os.path.join(LOGO_PATH, "Flor-negra (2).ico"), layout="wide")

# ── Login gate ──
def check_password():
    """Simple shared password gate."""
    if "authenticated" in st.session_state and st.session_state.authenticated:
        return True

    app_password = get_secret("APP_PASSWORD", "")
    if not app_password:
        return True  # No password configured, skip auth

    st.markdown(
        '<div style="max-width:400px;margin:80px auto;text-align:center;">'
        '<h2 style="color:#0f172a;">Pulso Operativo</h2>'
        '<p style="color:#64748b;">Ingresa el password para continuar</p>'
        '</div>',
        unsafe_allow_html=True,
    )
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        pwd = st.text_input("Password", type="password", key="login_pwd")
        if st.button("Entrar", use_container_width=True):
            if pwd == app_password:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Password incorrecto")
    return False

if not check_password():
    st.stop()

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


# ── Salary fetcher with fallback chain ──
def _fetch_salaries(client: BambooHRClient) -> list[dict]:
    """Try to get salary data from API, then secrets, then local file."""
    # Option 1: BambooHR custom report API
    try:
        return client.get_salary_report()
    except Exception:
        pass

    # Option 2: Streamlit secrets (JSON string)
    try:
        salaries_json = get_secret("SALARIES_JSON")
        if salaries_json:
            return json.loads(salaries_json)
    except Exception:
        pass

    # Option 3: Local file fallback
    sal_path = os.path.join(DATA_DIR, "salaries.json")
    if os.path.exists(sal_path):
        with open(sal_path) as f:
            return json.load(f)

    return []


# ── Load & enrich data (live from BambooHR API) ──
@st.cache_data(ttl=3600)
def load_data(_days_back: int = 90):
    """Fetch live data from BambooHR API with 1-hour cache."""
    api_key, subdomain = get_bamboohr_credentials()
    client = BambooHRClient(api_key, subdomain)

    # 1. Employees
    employees = client.get_employees()
    emp_map = {str(e["id"]): e.get("displayName", f"Employee {e['id']}") for e in employees}
    dept_map = {str(e["id"]): e.get("department") or "Sin departamento" for e in employees}

    # 2. Timesheet entries
    end_date = date.today()
    start_date = end_date - timedelta(days=_days_back)
    entries = client.get_timesheet_entries(start_date.isoformat(), end_date.isoformat())

    # 3. All projects and assignments from BambooHR
    emp_ids = [str(e["id"]) for e in employees]
    all_projects, project_assignments_raw = client.get_project_assignments(emp_ids)
    # Convert employee ID keys to employee names
    project_assignments = {emp_map.get(eid, f"Employee {eid}"): projs for eid, projs in project_assignments_raw.items()}

    if not entries:
        return pd.DataFrame(), {}, employees, all_projects, project_assignments

    df = pd.json_normalize(entries)
    if "employeeId" in df.columns:
        df["employeeName"] = df["employeeId"].astype(str).map(emp_map).fillna("Unknown")
    else:
        df["employeeName"] = "Unknown"

    # Date enrichment
    df["date"] = pd.to_datetime(df["date"])
    df["week"] = df["date"].dt.isocalendar().week.astype(int)
    df["week_start"] = df["date"].dt.to_period("W").apply(lambda p: p.start_time)
    df["weekday"] = df["date"].dt.day_name()
    df["is_weekday"] = df["date"].dt.dayofweek < 5
    if "projectInfo.project.name" in df.columns:
        df["project"] = df["projectInfo.project.name"].fillna("Sin proyecto")
    else:
        df["project"] = "Sin proyecto"
    df["department"] = df["employeeId"].astype(str).map(dept_map).fillna("Sin departamento") if "employeeId" in df.columns else "Sin departamento"

    # Ensure optional detail columns exist
    for col in ["start", "end", "note"]:
        if col not in df.columns:
            df[col] = ""

    # Descontar 1 hr de comida en entries de 6+ hrs
    df["hours_raw"] = df["hours"]
    df["hours"] = pd.to_numeric(df["hours"], errors="coerce").fillna(0)
    df["hours"] = df["hours"].apply(lambda h: max(h - 1, 0) if h >= 6 else h)

    # 3. Salary & hourly cost
    salaries = _fetch_salaries(client)
    hourly_map = {}
    for e in salaries:
        rate_str = (e.get("payRate") or "").strip()
        try:
            num = rate_str.replace(",", "").split()[0]
            rate = float(num)
        except (ValueError, IndexError):
            rate = 0
        eid = e.get("id") or e.get("employeeId")
        if rate > 0 and eid:
            hourly_map[str(eid)] = rate / 173.33

    df["hourly_rate"] = df["employeeId"].astype(str).map(hourly_map).fillna(0)
    df["cost"] = df["hours"] * df["hourly_rate"]

    return df, dept_map, employees, all_projects, project_assignments


# No toolbar on any chart
PLOTLY_CONFIG = {"displayModeBar": False}


with st.spinner("Cargando datos de BambooHR..."):
    df_raw, dept_map, all_employees_list, all_bamboo_projects, bamboo_assignments = load_data()

EXCLUDED_PEOPLE = {
    "Andrés Ponce de León Rosas", "Max Lugo Delgadillo", "Aleister Montfort Ibieta",
}
EXCLUDED_PROJECTS = {
    "Agentes", "AI Agents", "BID consistencia-docs", "Consar",
    "Grupo Felix", "people_test", "Proepta", "Tendencia gastronómica", "Test For Demo",
}
EXCLUDED_ASSIGN_PROJECTS = {
    "Research & Learning", "Reuniones internas", "Desarrollo de Negocios",
    "Administracion/Operaciones", "Administración/Operaciones",
    "Desarrollo de herramientas internas",
}
if not df_raw.empty:
    df_raw = df_raw[~df_raw["employeeName"].isin(EXCLUDED_PEOPLE)]
    df_raw.loc[df_raw["project"].isin(EXCLUDED_PROJECTS), "project"] = "Sin proyecto"

@st.cache_data(ttl=86400)
def get_exchange_rate(from_currency: str, to_currency: str = "MXN", rate_date: str = "") -> float:
    """Fetch exchange rate from Frankfurter API. Cached for 24h.

    Args:
        from_currency: Source currency code (USD, EUR, MXN).
        to_currency: Target currency code (default MXN).
        rate_date: Date in YYYY-MM-DD format. Empty string = latest.
    """
    if from_currency == to_currency:
        return 1.0
    endpoint = rate_date if rate_date else "latest"
    try:
        r = requests.get(
            f"https://api.frankfurter.dev/v1/{endpoint}",
            params={"from": from_currency, "to": to_currency},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()["rates"][to_currency]
    except Exception:
        # Fallback rates if API fails
        fallback = {"USD": 17.7, "EUR": 21.5}
        return fallback.get(from_currency, 20.0)


INTERNAL_PROJECTS = {"Reuniones internas", "Research & Learning", "Backoffice", "people_test", "Sin proyecto", "Administración/Operaciones", "Desarrollo de herramientas internas"}

PROJECTS_FILE = os.path.join(DATA_DIR, "projects.json")


def load_projects() -> list[dict]:
    if os.path.exists(PROJECTS_FILE):
        with open(PROJECTS_FILE) as f:
            return json.load(f)
    return []


def save_projects(projects: list[dict]):
    with open(PROJECTS_FILE, "w") as f:
        json.dump(projects, f, indent=2, ensure_ascii=False, default=str)

if df_raw.empty:
    st.warning("No hay datos de timesheet para el periodo seleccionado.")
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
elif len(date_range) == 1:
    st.warning("Selecciona ambas fechas del rango.")
    st.stop()
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
tab_overview, tab_person, tab_project, tab_dept, tab_costs, tab_assignments, tab_report, tab_rentabilidad = st.tabs(
    ["Overview", "Por Persona", "Por Proyecto", "Por Departamento", "Costos", "Asignaciones", "Reporte", "Rentabilidad"]
)


# ──────────────────────────────────────────────
# TAB 1: OVERVIEW
# ──────────────────────────────────────────────
with tab_overview:
    # KPIs based on full selected period
    period_start = df_wd["date"].min()
    period_end = df_wd["date"].max()
    if not pd.isna(period_start) and not pd.isna(period_end):
        st.caption(f"{period_start.strftime('%d %b %Y')} — {period_end.strftime('%d %b %Y')}")

    k1, k2, k3, k4 = st.columns(4)
    total_hours = df_wd["hours"].sum()
    n_employees = df_wd["employeeName"].nunique()
    n_projects = df_wd[df_wd["project"] != "Sin proyecto"]["project"].nunique()
    # Promedio semanal: horas promedio por persona por semana
    if n_employees > 0 and df_wd["week_start"].nunique() > 0:
        avg_weekly = df_wd.groupby(["employeeName", "week_start"])["hours"].sum().groupby("employeeName").mean().mean()
    else:
        avg_weekly = 0

    k1.metric("Horas totales", f"{total_hours:,.0f}")
    k2.metric("Personas activas", n_employees)
    k3.metric("Proyectos", n_projects)
    k4.metric("Prom hrs / persona / sem", f"{avg_weekly:,.2f}")

    st.markdown("")

    # ── Week-over-week comparison (main chart) ──
    weekly_totals = df_wd.groupby("week_start").agg(
        hours=("hours", "sum"),
        people=("employeeName", "nunique"),
    ).reset_index().sort_values("week_start")
    weekly_totals["week_label"] = weekly_totals["week_start"].dt.strftime("%d %b")
    # avg_per_person available if needed later
    weekly_totals["avg_per_person"] = weekly_totals["hours"] / weekly_totals["people"].replace(0, 1)

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
        hovertemplate="<b>%{x}</b><br>Horas: %{y:,.2f}<extra></extra>",
    ))
    fig_weeks.update_layout(
        **PLOTLY_LAYOUT, hovermode="closest",
        title=f"Horas por semana  <span style='font-size:12px;color:{MUTED}'>{delta_label}</span>",
        xaxis_title="", yaxis_title="Horas",
        showlegend=False,
        bargap=0.7 if len(weekly_totals) <= 2 else 0.3,
    )
    st.plotly_chart(fig_weeks, use_container_width=True, config=PLOTLY_CONFIG)

    # ── Two columns: Top N people + Projects bar ──
    c1, c2 = st.columns(2)

    with c1:
        slider_max = max(5, min(40, n_employees))
        n_top = st.slider("Top personas", min_value=1, max_value=slider_max, value=min(10, slider_max), key="top_n")
        by_emp = df_wd.groupby("employeeName")["hours"].sum().sort_values(ascending=True).tail(n_top).reset_index()

        fig_emp = go.Figure(go.Bar(
            x=by_emp["hours"],
            y=by_emp["employeeName"],
            orientation="h",
            marker_color=BAR_COLOR,
            text=by_emp["hours"].apply(lambda x: f"{x:,.2f}"),
            textposition="outside",
            textfont=dict(size=11),
            cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>Horas: %{x:,.2f}<extra></extra>",
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
            text=by_proj["hours"].apply(lambda x: f"{x:,.2f}"),
            textposition="outside",
            textfont=dict(size=11),
            cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>Horas: %{x:,.2f}<extra></extra>",
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
            hovertemplate="<b>%{x|%d %b}</b><br>Horas: %{y:,.2f}<extra></extra>",
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
            hovertemplate="<b>%{y}</b><br>Base: 40 hrs<extra></extra>",
        ))
        fig_ot.add_trace(go.Bar(
            x=ot_count["excess"],
            y=ot_count["employeeName"],
            orientation="h",
            marker_color="#b91c1c",
            name="Exceso",
            text=ot_count["avg_hrs"].apply(lambda x: f"{x:.0f} hrs"),
            textposition="outside",
            textfont=dict(size=11),
            cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>Exceso: %{x:,.1f} hrs<extra></extra>",
        ))
        fig_ot.update_layout(
            **PLOTLY_LAYOUT,
            title="Promedio semanal de quienes exceden 40 hrs",
            yaxis_title="", xaxis_title="Horas promedio/semana",
            height=max(300, len(ot_count) * 30),
            barmode="stack",
            showlegend=False, hovermode="closest",
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
    available_people = sorted(df["employeeName"].dropna().unique())
    if not available_people:
        st.info("No hay personas con datos en el periodo seleccionado.")
        st.stop()
    person = st.selectbox("Selecciona una persona", available_people, key="person_select")
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
        p2.metric("Horas totales", f"{total_p:,.2f}")
        p3.metric("Dias activos", days_active)
        p4.metric("Promedio diario", f"{avg_daily:,.2f} hrs")

        st.markdown("")

        # Weekly breakdown
        weekly = df_person.groupby("week_start")["hours"].sum().reset_index().sort_values("week_start")
        weekly["week_label"] = weekly["week_start"].dt.strftime("%d %b")

        fig_weekly = go.Figure(go.Bar(
            x=weekly["week_label"], y=weekly["hours"],
            marker_color=BAR_COLOR,
            text=weekly["hours"].apply(lambda x: f"{x:,.2f}"),
            textposition="outside",
            textfont=dict(size=12),
            cliponaxis=False,
            hovertemplate="<b>%{x}</b><br>Horas: %{y:,.2f}<extra></extra>",
        ))
        fig_weekly.update_layout(
            **PLOTLY_LAYOUT,
            title=f"Semanas de {person}",
            xaxis_title="Semana (inicio)", yaxis_title="Horas",
            bargap=0.7 if len(weekly) <= 2 else 0.3,
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
                text=wd["hours"].apply(lambda x: f"{x:,.2f}"),
                textposition="outside",
                cliponaxis=False,
                hovertemplate="<b>%{x}</b><br>Horas: %{y:,.2f}<extra></extra>",
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
                    text=proj_person["hours"].apply(lambda x: f"{x:,.2f}"),
                    textposition="outside",
                    cliponaxis=False,
                    hovertemplate="<b>%{y}</b><br>Horas: %{x:,.2f}<extra></extra>",
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
    # Active vs inactive projects this week
    all_assigned_projs = set()
    for projs in bamboo_assignments.values():
        all_assigned_projs.update(p for p in projs if p not in EXCLUDED_ASSIGN_PROJECTS and p not in EXCLUDED_PROJECTS)
    projs_with_hours = set(df_wd[df_wd["project"] != "Sin proyecto"]["project"].unique())
    active_projs = all_assigned_projs & projs_with_hours
    inactive_projs = all_assigned_projs - projs_with_hours

    pi1, pi2 = st.columns(2)
    pi1.info(f"**Proyectos activos este periodo:** {len(active_projs)}")
    pi2.warning(f"**Proyectos inactivos este periodo:** {len(inactive_projs)}")
    if inactive_projs:
        with st.expander(f"Ver proyectos inactivos ({len(inactive_projs)})"):
            st.write(", ".join(sorted(inactive_projs)))

    projects_with_data = sorted(projs_with_hours)
    if not projects_with_data:
        st.info("No hay proyectos con horas registradas en este periodo.")
    else:
        project = st.selectbox("Selecciona un proyecto", projects_with_data, key="project_select")
        df_proj = df_wd[df_wd["project"] == project]

        total_proj = df_proj["hours"].sum()
        n_contributors = df_proj["employeeName"].nunique()
        proj_days = df_proj["date"].nunique()

        pr1, pr2, pr3 = st.columns(3)
        pr1.metric("Horas totales", f"{total_proj:,.2f}")
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
        fig_proj_stack.update_traces(
            hovertemplate="<b>%{data.name}</b><br>Horas: %{y:,.2f}<extra></extra>",
        )
        fig_proj_stack.update_layout(
            **PLOTLY_LAYOUT, hovermode="closest", xaxis_title="Semana", yaxis_title="Horas", legend_title="",
            legend=dict(orientation="h", yanchor="top", y=-0.25, xanchor="left", x=0, font_size=11),
            bargap=0.7 if len(proj_weekly["week_label"].unique()) <= 2 else 0.3,
        )
        st.plotly_chart(fig_proj_stack, use_container_width=True, config=PLOTLY_CONFIG)

        # Hours per contributor (horizontal bar)
        by_contrib = df_proj.groupby("employeeName")["hours"].sum().sort_values(ascending=True).reset_index()
        fig_contrib = go.Figure(go.Bar(
            x=by_contrib["hours"], y=by_contrib["employeeName"],
            orientation="h",
            marker_color=BAR_COLOR,
            text=by_contrib["hours"].apply(lambda x: f"{x:,.2f}"),
            textposition="outside",
            cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>Horas: %{x:,.2f}<extra></extra>",
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
    available_depts = sorted(df["department"].unique())
    if not available_depts:
        st.info("No hay departamentos con datos en el periodo seleccionado.")
        st.stop()
    dept_sel = st.selectbox("Selecciona un departamento", available_depts, key="dept_select")
    df_dept = df_wd[df_wd["department"] == dept_sel]

    if df_dept.empty:
        st.info("No hay datos para este departamento en el periodo seleccionado.")
    else:
        total_d = df_dept["hours"].sum()
        n_emp_d = df_dept["employeeName"].nunique()
        n_proj_d = df_dept[df_dept["project"] != "Sin proyecto"]["project"].nunique()

        d1, d2, d3 = st.columns(3)
        d1.metric("Horas totales", f"{total_d:,.2f}")
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
        fig_dept_stack.update_traces(
            hovertemplate="<b>%{data.name}</b><br>Horas: %{y:,.2f}<extra></extra>",
        )
        fig_dept_stack.update_layout(
            **PLOTLY_LAYOUT, hovermode="closest", xaxis_title="Semana", yaxis_title="Horas", legend_title="",
            legend=dict(orientation="h", yanchor="top", y=-0.25, xanchor="left", x=0, font_size=11),
            bargap=0.7 if len(dept_weekly["week_label"].unique()) <= 2 else 0.3,
        )
        st.plotly_chart(fig_dept_stack, use_container_width=True, config=PLOTLY_CONFIG)

        dc1, dc2 = st.columns(2)

        with dc1:
            dept_by_emp = df_dept.groupby("employeeName")["hours"].sum().sort_values(ascending=True).reset_index()
            fig_de = go.Figure(go.Bar(
                x=dept_by_emp["hours"], y=dept_by_emp["employeeName"],
                orientation="h",
                marker_color=BAR_COLOR,
                text=dept_by_emp["hours"].apply(lambda x: f"{x:,.2f}"),
                textposition="outside",
                cliponaxis=False,
                hovertemplate="<b>%{y}</b><br>Horas: %{x:,.2f}<extra></extra>",
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
                    text=dept_by_proj["hours"].apply(lambda x: f"{x:,.2f}"),
                    textposition="outside",
                    cliponaxis=False,
                    hovertemplate="<b>%{y}</b><br>Horas: %{x:,.2f}<extra></extra>",
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
                text_auto=".2f",
            )
            fig_heat.update_traces(
                hovertemplate="<b>%{y}</b><br>%{x}: %{z:.2f} hrs<extra></extra>",
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
            hovertemplate="<b>%{x}</b><br>Costo: $%{y:,.0f}<extra></extra>",
        ))
        fig_wc.update_layout(
            **PLOTLY_LAYOUT,
            title="Costo semanal total",
            xaxis_title="Semana", yaxis_title="MXN",
            bargap=0.7 if len(weekly_cost) <= 2 else 0.3,
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
                hovertemplate="<b>%{y}</b><br>Costo: $%{x:,.0f}<extra></extra>",
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
            fig_pwc.update_traces(
                hovertemplate="<b>%{data.name}</b><br>Costo: $%{y:,.0f}<extra></extra>",
            )
            fig_pwc.update_layout(
                **PLOTLY_LAYOUT, hovermode="closest", xaxis_title="Semana", yaxis_title="MXN", legend_title="",
                legend=dict(orientation="h", yanchor="top", y=-0.25, xanchor="left", x=0, font_size=11),
                bargap=0.7 if len(proj_weekly_cost["week_label"].unique()) <= 2 else 0.3,
            )
            st.plotly_chart(fig_pwc, use_container_width=True, config=PLOTLY_CONFIG)


# ──────────────────────────────────────────────
# TAB 6: ASIGNACIONES (Persona × Proyecto)
# ──────────────────────────────────────────────
with tab_assignments:
    df_assigned = df_wd[df_wd["project"] != "Sin proyecto"]

    if df_assigned.empty:
        st.info("No hay datos de asignaciones a proyectos en este periodo.")
    else:
        # ── KPIs ──
        proj_per_person = df_assigned.groupby("employeeName")["project"].nunique()
        avg_proj = proj_per_person.mean()
        max_proj_person = proj_per_person.idxmax()
        max_proj_count = proj_per_person.max()
        multi_proj_rate = (proj_per_person[proj_per_person > 1].count() / proj_per_person.count() * 100) if len(proj_per_person) > 0 else 0

        ak1, ak2, ak3, ak4 = st.columns(4)
        ak1.metric("Promedio proyectos / persona", f"{avg_proj:.1f}")
        ak2.metric("Personas activas", proj_per_person.count())
        ak3.metric("Mas proyectos", f"{max_proj_person}", delta=f"{max_proj_count} proyectos")
        ak4.metric("Multi-proyecto", f"{multi_proj_rate:.0f}%", help="% de personas en mas de 1 proyecto")

        st.markdown("")

        # ── Filter: Person for Treemap ──
        people_list = sorted(df_assigned["employeeName"].unique())
        selected_person_assign = st.selectbox(
            "Persona", ["Todos"] + people_list, key="assign_person_select"
        )

        # Period label from global date filter
        _p_start = df_assigned["date"].min()
        _p_end = df_assigned["date"].max()
        _period_label = f"{_p_start.strftime('%d %b')} — {_p_end.strftime('%d %b %Y')}" if not pd.isna(_p_start) else "periodo seleccionado"

        # Filter data for treemap
        tree_src = df_assigned.copy()

        if selected_person_assign != "Todos":
            tree_src = tree_src[tree_src["employeeName"] == selected_person_assign]
            tree_title = f"Distribucion de tiempo: {selected_person_assign}, {_period_label}"
        else:
            tree_title = f"Distribucion de tiempo: todas las personas, {_period_label}"

        if tree_src.empty:
            st.info("No hay datos para la seleccion.")
        else:
            if selected_person_assign == "Todos":
                tree_data = tree_src.groupby(["employeeName", "project"])["hours"].sum().reset_index()
                fig_tree = px.treemap(
                    tree_data, path=["employeeName", "project"], values="hours",
                    title=tree_title,
                    color_discrete_sequence=PALETTE,
                )
            else:
                tree_data = tree_src.groupby("project")["hours"].sum().reset_index()
                fig_tree = px.treemap(
                    tree_data, path=["project"], values="hours",
                    title=tree_title,
                    color_discrete_sequence=PALETTE,
                )

            fig_tree.update_layout(
                font=dict(family="Inter, system-ui, sans-serif", color="#334155"),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=10, r=10, t=40, b=10),
            )
            n_leaves = len(tree_data)
            if n_leaves > 1:
                fig_tree.update_traces(
                    textinfo="label+value+percent parent",
                    texttemplate="%{label}<br>%{value:,.2f}<br>%{percentParent:.1%}",
                    textfont=dict(size=12),
                    hovertemplate="<b>%{label}</b><br>Horas: %{value:,.2f}<br>%{percentParent:.1%} del total<extra></extra>",
                )
            else:
                fig_tree.update_traces(
                    textinfo="label+value",
                    texttemplate="%{label}<br>%{value:,.2f}",
                    textfont=dict(size=12),
                    hovertemplate="<b>%{label}</b><br>Horas: %{value:,.2f}<extra></extra>",
                )
            st.plotly_chart(fig_tree, use_container_width=True, config=PLOTLY_CONFIG)

        # ── Stacked horizontal bar: hours per person colored by project ──
        person_proj = df_assigned.groupby(["employeeName", "project"])["hours"].sum().reset_index()
        person_totals = person_proj.groupby("employeeName")["hours"].sum().sort_values(ascending=True)
        # Order: bottom=least, top=most (Plotly horizontal bars render bottom-up)
        ordered_names = person_totals.index.tolist()

        fig_stack = px.bar(
            person_proj, x="hours", y="employeeName",
            color="project", orientation="h",
            title="Horas por persona (desglose por proyecto)",
            color_discrete_sequence=PALETTE,
            barmode="stack",
        )
        fig_stack.update_traces(
            hovertemplate="%{data.name}: %{x:,.2f} hrs<extra></extra>",
        )
        fig_stack.update_layout(
            **PLOTLY_LAYOUT, hovermode="closest", xaxis_title="Horas", yaxis_title="", legend_title="",
            legend=dict(orientation="h", yanchor="top", y=-0.3, xanchor="left", x=0, font_size=11),
            height=max(400, len(ordered_names) * 32),
            yaxis=dict(categoryorder="array", categoryarray=ordered_names),
        )
        st.plotly_chart(fig_stack, use_container_width=True, config=PLOTLY_CONFIG)

        # ── Heatmap: Persona × Proyecto ──
        import numpy as np
        from scipy.cluster.hierarchy import linkage, leaves_list

        heat_pp = df_assigned.groupby(["employeeName", "project"])["hours"].sum().reset_index()
        heat_pivot = heat_pp.pivot_table(index="employeeName", columns="project", values="hours", fill_value=0)

        # Hierarchical clustering for rows (people) to group similar profiles
        try:
            if len(heat_pivot) > 2:
                row_linkage = linkage(heat_pivot.values, method="ward")
                row_order = leaves_list(row_linkage)
                heat_pivot = heat_pivot.iloc[row_order]
            # Cluster columns (projects) too
            if len(heat_pivot.columns) > 2:
                col_linkage = linkage(heat_pivot.values.T, method="ward")
                col_order = leaves_list(col_linkage)
                heat_pivot = heat_pivot.iloc[:, col_order]
        except (ValueError, FloatingPointError):
            pass  # Fall back to default ordering

        # Replace zeros with NaN so they show as blank
        heat_display = heat_pivot.replace(0, np.nan)

        # Custom text: show value only where there's data
        text_vals = np.where(heat_pivot.values > 0, np.vectorize(lambda v: f"{v:.1f}")(heat_pivot.values), "")

        fig_heat_pp = go.Figure(data=go.Heatmap(
            z=heat_display.values,
            x=heat_display.columns.tolist(),
            y=heat_display.index.tolist(),
            text=text_vals,
            texttemplate="%{text}",
            textfont=dict(size=11),
            colorscale=[[0, "#22c55e"], [0.5, "#facc15"], [1, "#ef4444"]],
            hovertemplate="<b>%{y}</b><br>Proyecto: %{x}<br>Horas: %{z:,.2f}<extra></extra>",
            hoverongaps=False,
            showscale=True,
            colorbar=dict(title="Horas"),
        ))
        fig_heat_pp.update_layout(
            font=dict(family="Inter, system-ui, sans-serif", color="#334155"),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            title="Heatmap: Persona x Proyecto (horas)",
            xaxis_title="", yaxis_title="",
            xaxis=dict(side="bottom", tickangle=-45),
            height=max(450, len(heat_pivot) * 32),
        )
        st.plotly_chart(fig_heat_pp, use_container_width=True, config=PLOTLY_CONFIG)

    # ── Snapshot: Asignaciones reales de BambooHR ──
    st.markdown("---")
    st.markdown("#### Asignaciones en BambooHR")
    st.caption("Proyectos asignados a cada persona en BambooHR (independiente de si registraron horas)")

    import numpy as np

    # Build full project list and people list from BambooHR assignments
    all_proj_names = sorted(p for p in all_bamboo_projects.values() if p not in EXCLUDED_ASSIGN_PROJECTS)
    # All people who have at least one project assigned
    assigned_people = sorted(bamboo_assignments.keys())
    # Filter out excluded people
    assigned_people = [p for p in assigned_people if p not in EXCLUDED_PEOPLE]

    # Build binary matrix from BambooHR assignments (not timesheet entries)
    snap_binary = pd.DataFrame(0, index=assigned_people, columns=all_proj_names)
    for person, projs in bamboo_assignments.items():
        if person in EXCLUDED_PEOPLE:
            continue
        for proj in projs:
            if proj in snap_binary.columns:
                snap_binary.loc[person, proj] = 1

    # Remove projects with zero assignments
    snap_binary = snap_binary.loc[:, snap_binary.sum(axis=0) > 0]

    # Sort columns: projects with most assigned people first
    col_counts = snap_binary.sum(axis=0).sort_values(ascending=False)
    snap_binary = snap_binary[col_counts.index]
    # Sort rows: people with most projects first
    row_counts = snap_binary.sum(axis=1).sort_values(ascending=False)
    snap_binary = snap_binary.loc[row_counts.index]

    # Display: NaN for zeros so they appear blank in heatmap
    snap_display = snap_binary.replace(0, np.nan)

    fig_snap = go.Figure(data=go.Heatmap(
        z=snap_display.values,
        x=snap_display.columns.tolist(),
        y=snap_display.index.tolist(),
        colorscale=[[0, "rgba(0,0,0,0)"], [1, "#3b82f6"]],
        hovertemplate="<b>%{y}</b><br>Proyecto: %{x}<extra></extra>",
        hoverongaps=False,
        showscale=False,
        zmin=0, zmax=1,
        xgap=2, ygap=2,
    ))
    # Annotations: project count per person (right side)
    for person in snap_binary.index:
        fig_snap.add_annotation(
            x=len(snap_binary.columns) - 0.3, y=person,
            text=f"<b>{int(row_counts[person])}</b>",
            showarrow=False, xanchor="left", xshift=20,
            font=dict(size=11, color="#3b82f6"),
        )
    # Annotations: person count per project (above plot area)
    for proj in snap_binary.columns:
        fig_snap.add_annotation(
            x=proj, y=1, yref="paper",
            text=f"<b>{int(col_counts[proj])}</b>",
            showarrow=False, yanchor="bottom", yshift=4,
            font=dict(size=10, color="#64748b"),
        )
    fig_snap.update_layout(
        font=dict(family="Inter, system-ui, sans-serif", color="#334155"),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        title="Persona × Proyecto (asignaciones BambooHR)",
        xaxis_title="", yaxis_title="",
        xaxis=dict(side="bottom", tickangle=-45, showgrid=False),
        yaxis=dict(showgrid=False),
        margin=dict(l=20, r=80, t=80, b=20),
        height=max(500, len(assigned_people) * 28),
    )
    st.plotly_chart(fig_snap, use_container_width=True, config=PLOTLY_CONFIG)

    # Summary counts
    active_proj_count = (col_counts > 0).sum()
    st.caption(f"{active_proj_count} proyectos con asignaciones · {len(assigned_people)} personas")

    # ── Asignaciones BambooHR: toggle persona/proyecto ──
    st.markdown("---")
    st.markdown("#### Detalle de Asignaciones BambooHR")
    assign_view = st.radio(
        "Agrupar por", ["Persona", "Proyecto"], horizontal=True, key="assign_view_toggle"
    )
    if assign_view == "Persona":
        person_rows = []
        for person in sorted(bamboo_assignments.keys()):
            if person in EXCLUDED_PEOPLE:
                continue
            projs = sorted(p for p in bamboo_assignments[person] if p not in EXCLUDED_ASSIGN_PROJECTS)
            if not projs:
                continue
            person_rows.append({
                "Persona": person,
                "# Proyectos": len(projs),
                "Proyectos": ", ".join(projs),
            })
        df_assign_view = pd.DataFrame(person_rows).sort_values("# Proyectos", ascending=False)
        st.dataframe(df_assign_view, use_container_width=True, hide_index=True)
    else:
        proj_people: dict[str, list[str]] = {}
        for person, projs in bamboo_assignments.items():
            if person in EXCLUDED_PEOPLE:
                continue
            for proj in projs:
                if proj in EXCLUDED_ASSIGN_PROJECTS:
                    continue
                proj_people.setdefault(proj, []).append(person)
        proj_rows = []
        for proj in sorted(proj_people.keys()):
            people = sorted(proj_people[proj])
            proj_rows.append({
                "Proyecto": proj,
                "# Personas": len(people),
                "Colaboradores": ", ".join(people),
            })
        df_assign_view = pd.DataFrame(proj_rows).sort_values("# Personas", ascending=False)
        st.dataframe(df_assign_view, use_container_width=True, hide_index=True)



# ──────────────────────────────────────────────
# TAB 7: REPORTE SEMANAL
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

        # % hrs con proyecto
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

        # ── Sin proyecto breakdown ──
        sin_proy = dfw[dfw["project"] == "Sin proyecto"]
        sin_proy_hrs = sin_proy["hours"].sum()
        sin_proy_pct = (sin_proy_hrs / w_hours * 100) if w_hours > 0 else 0
        sin_proy_by_person = sin_proy.groupby("employeeName")["hours"].sum().sort_values(ascending=False)
        person_total_hrs = dfw.groupby("employeeName")["hours"].sum()
        sin_proy_detail = []
        for name, hrs in sin_proy_by_person.items():
            total = person_total_hrs.get(name, hrs)
            pct = (hrs / total * 100) if total > 0 else 0
            sin_proy_detail.append((name, hrs, pct))
        # People with 100% sin proyecto
        sin_proy_100 = [d for d in sin_proy_detail if d[2] >= 99.9]

        # ══════════════════════════════════════
        # RENDER REPORT
        # ══════════════════════════════════════

        # ── KPI cards ──
        rk1, rk2, rk3, rk4, rk5 = st.columns(5)
        rk1.metric("Horas totales", f"{w_hours:,.0f}", delta=f"{((w_hours-p_hours)/p_hours*100):+.1f}%" if p_hours > 0 else None)
        rk2.metric("Costo total", f"${w_cost:,.0f}", delta=f"{((w_cost-p_cost)/p_cost*100):+.1f}%" if p_cost > 0 else None)
        rk3.metric("Personas activas", w_people, delta=f"{w_people - p_people:+d}" if p_people > 0 else None)
        rk4.metric("Promedio hrs/persona", f"{w_avg_per_person:,.2f}", delta=f"{((w_avg_per_person-p_avg_per_person)/p_avg_per_person*100):+.1f}%" if p_avg_per_person > 0 else None)
        rk5.metric("% hrs con proyecto", f"{assign_rate:.0f}%", delta=f"{assign_rate - p_assign_rate:+.1f}pp" if p_hours > 0 else None)

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
        report_lines.append(f"| Promedio hrs/persona | {w_avg_per_person:,.2f} | {p_avg_per_person:,.2f} | {((w_avg_per_person-p_avg_per_person)/p_avg_per_person*100):+.1f}% |" if p_avg_per_person > 0 else f"| Promedio hrs/persona | {w_avg_per_person:,.2f} | — | — |")
        report_lines.append(f"| % hrs con proyecto | {assign_rate:.0f}% | {p_assign_rate:.0f}% | {assign_rate - p_assign_rate:+.1f}pp |" if p_hours > 0 else f"| % hrs con proyecto | {assign_rate:.0f}% | — | — |")
        report_lines.append(f"| Proyectos activos | {w_projects} | — | — |")
        report_lines.append("")

        # Cost by project with delta
        report_lines.append("## Costo por Proyecto")
        report_lines.append("")
        if not proj_cost_curr.empty:
            report_lines.append("| Proyecto | Costo | Horas | Personas | vs Anterior |")
            report_lines.append("|:--|--:|--:|--:|--:|")
            for _, r in proj_cost_curr.iterrows():
                if r["project"] not in proj_cost_prev:
                    delta = "nuevo"
                else:
                    prev_c = proj_cost_prev[r["project"]]
                    if prev_c > 0:
                        d = ((r["cost"] - prev_c) / prev_c * 100)
                        delta = f"{d:+.1f}%"
                    else:
                        delta = "—"
                report_lines.append(f"| {r['project']} | ${r['cost']:,.0f} | {r['hours']:,.2f} | {int(r['people'])} | {delta} |")
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
                if r["project"] not in proj_hrs_prev:
                    delta = "nuevo"
                else:
                    prev_h = proj_hrs_prev[r["project"]]
                    if prev_h > 0:
                        d = ((r["hours"] - prev_h) / prev_h * 100)
                        delta = f"{d:+.1f}%"
                    else:
                        delta = "—"
                report_lines.append(f"| {r['project']} | {r['hours']:,.2f} | {int(r['people'])} | {delta} |")
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
                report_lines.append(f"| {r['department']} | {r['hours']:,.2f} | {int(r['people'])} | {delta} |")
            report_lines.append("")

        # Overtime
        if not overtime_people.empty:
            report_lines.append(f"## Overtime: +40 hrs ({len(overtime_people)} personas)")
            report_lines.append("")
            report_lines.append("| Persona | Horas | Exceso |")
            report_lines.append("|:--|--:|--:|")
            for name, hrs in overtime_people.items():
                report_lines.append(f"| {name} | {hrs:,.2f} | +{hrs - 40:,.2f} |")
            report_lines.append("")

        # Missing
        if missing_names:
            report_lines.append(f"## Sin registro de horas ({len(missing_names)})")
            report_lines.append("")
            # Show as comma-separated to save space
            report_lines.append(", ".join(missing_names))
            report_lines.append("")

        # Sin proyecto
        if sin_proy_hrs > 0:
            report_lines.append(f"## Sin proyecto ({sin_proy_pct:.0f}% de horas)")
            report_lines.append("")
            report_lines.append(f"**{sin_proy_hrs:,.2f}** de {w_hours:,.0f} horas no tienen proyecto asignado.")
            report_lines.append("")
            if sin_proy_100:
                report_lines.append(f"**100% sin proyecto ({len(sin_proy_100)}):** {', '.join(d[0] for d in sin_proy_100)}")
                report_lines.append("")
            # Top offenders table (show all with sin proyecto hours)
            report_lines.append("| Persona | Hrs sin proyecto | % sin proyecto |")
            report_lines.append("|:--|--:|--:|")
            for name, hrs, pct in sin_proy_detail[:15]:
                report_lines.append(f"| {name} | {hrs:,.2f} | {pct:.0f}% |")
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
                ("Prom hrs/persona", f"{w_avg_per_person:,.2f}"),
                ("% hrs con proyecto", f"{assign_rate:.0f}%"),
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
                snapshot_rows.append(["Prom hrs/persona", f"{w_avg_per_person:,.2f}", f"{p_avg_per_person:,.2f}", f"{((w_avg_per_person-p_avg_per_person)/p_avg_per_person*100):+.1f}%"])
            else:
                snapshot_rows.append(["Prom hrs/persona", f"{w_avg_per_person:,.2f}", "—", "—"])
            if p_hours > 0:
                snapshot_rows.append(["% hrs con proyecto", f"{assign_rate:.0f}%", f"{p_assign_rate:.0f}%", f"{assign_rate - p_assign_rate:+.1f}pp"])
            else:
                snapshot_rows.append(["% hrs con proyecto", f"{assign_rate:.0f}%", "—", "—"])
            pdf.add_table(["Indicador", "Esta semana", "Anterior", "Cambio"], snapshot_rows, [60, 45, 45, 40])

            # Cost by project
            if not proj_cost_curr.empty:
                pdf.section_title("Costo por Proyecto")
                cost_rows = []
                for _, r in proj_cost_curr.iterrows():
                    if r["project"] not in proj_cost_prev:
                        delta = "nuevo"
                    else:
                        prev_c = proj_cost_prev[r["project"]]
                        delta = f"{((r['cost'] - prev_c) / prev_c * 100):+.1f}%" if prev_c > 0 else "—"
                    cost_rows.append([r["project"], f"${r['cost']:,.0f}", f"{r['hours']:,.2f}", str(int(r["people"])), delta])
                pdf.add_table(["Proyecto", "Costo", "Horas", "Personas", "vs Ant."], cost_rows, [60, 35, 30, 30, 35])

            # Hours by project
            if not proj_hrs_curr.empty:
                pdf.section_title("Horas por Proyecto")
                hrs_rows = []
                for _, r in proj_hrs_curr.iterrows():
                    if r["project"] not in proj_hrs_prev:
                        delta = "nuevo"
                    else:
                        prev_h = proj_hrs_prev[r["project"]]
                        delta = f"{((r['hours'] - prev_h) / prev_h * 100):+.1f}%" if prev_h > 0 else "—"
                    hrs_rows.append([r["project"], f"{r['hours']:,.2f}", str(int(r["people"])), delta])
                pdf.add_table(["Proyecto", "Horas", "Personas", "vs Ant."], hrs_rows, [70, 40, 40, 40])

            # Department
            if not dept_hrs.empty:
                pdf.section_title("Por Departamento")
                dept_rows = []
                for _, r in dept_hrs.iterrows():
                    prev_dh = dept_hrs_prev.get(r["department"], 0)
                    delta = f"{((r['hours'] - prev_dh) / prev_dh * 100):+.1f}%" if prev_dh > 0 else "—"
                    dept_rows.append([r["department"], f"{r['hours']:,.2f}", str(int(r["people"])), delta])
                pdf.add_table(["Departamento", "Horas", "Personas", "vs Ant."], dept_rows, [70, 40, 40, 40])

            # Overtime
            if not overtime_people.empty:
                pdf.section_title(f"Overtime +40 hrs ({len(overtime_people)} personas)")
                ot_rows = [[name, f"{hrs:,.2f}", f"+{hrs - 40:,.2f}"] for name, hrs in overtime_people.items()]
                pdf.add_table(["Persona", "Horas", "Exceso"], ot_rows, [90, 50, 50])

            # Missing
            if missing_names:
                pdf.section_title(f"Sin registro de horas ({len(missing_names)})")
                pdf.set_font("Helvetica", "", 8)
                pdf.set_text_color(71, 85, 105)
                pdf.multi_cell(190, 5, ", ".join(missing_names))

            # Sin proyecto
            if sin_proy_hrs > 0:
                pdf.ln(4)
                pdf.section_title(f"Sin proyecto ({sin_proy_pct:.0f}% de horas)")
                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(71, 85, 105)
                pdf.cell(0, 6, f"{sin_proy_hrs:,.2f} de {w_hours:,.0f} horas no tienen proyecto asignado.")
                pdf.ln(8)
                if sin_proy_100:
                    pdf.set_font("Helvetica", "B", 8)
                    pdf.set_text_color(51, 65, 85)
                    pdf.cell(0, 5, f"100% sin proyecto ({len(sin_proy_100)}):")
                    pdf.ln(5)
                    pdf.set_font("Helvetica", "", 8)
                    pdf.multi_cell(190, 5, ", ".join(d[0] for d in sin_proy_100))
                    pdf.ln(4)
                sp_rows = [[name, f"{hrs:,.2f}", f"{pct:.0f}%"] for name, hrs, pct in sin_proy_detail[:15]]
                pdf.add_table(["Persona", "Hrs sin proyecto", "% sin proyecto"], sp_rows, [90, 50, 50])

            buf = io.BytesIO()
            pdf.output(buf)
            return buf.getvalue()

        st.markdown("")
        # Cache PDF so it only generates once per week selection
        _pdf_cache_key = f"pdf_{selected_week_start.strftime('%Y-%m-%d')}"
        if _pdf_cache_key not in st.session_state:
            st.session_state[_pdf_cache_key] = generate_pdf()
        col_dl1, col_dl2, col_dl3, _ = st.columns([1, 1, 1, 2])
        with col_dl1:
            st.download_button(
                "Descargar PDF",
                data=st.session_state[_pdf_cache_key],
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


# ──────────────────────────────────────────────
# TAB 8: RENTABILIDAD
# ──────────────────────────────────────────────
with tab_rentabilidad:

    # ── Helper: compute auto-estimate for a project ──
    def _auto_estimate(project_name: str, start_date_str: str) -> tuple[float, float, float]:
        """Return (auto_estimate, avg_monthly_cost, months_before) for backward estimation."""
        proj_data = df_raw[(df_raw["project"] == project_name) & (df_raw["hourly_rate"] > 0)]
        if proj_data.empty or not start_date_str:
            return 0.0, 0.0, 0.0
        # Monthly average from tracked data
        proj_weekly = proj_data.groupby("week_start")["cost"].sum()
        avg_weekly = proj_weekly.mean()
        avg_monthly = avg_weekly * 4.33  # weeks per month

        # Months between project start and first tracked week
        first_tracked = proj_data["date"].min()
        proj_start = pd.Timestamp(start_date_str)
        if proj_start >= first_tracked:
            return 0.0, avg_monthly, 0.0
        months_before = (first_tracked - proj_start).days / 30.44
        return avg_monthly * months_before, avg_monthly, months_before

    # ── Load project configs ──
    project_configs = load_projects()
    config_by_name = {p["name"]: p for p in project_configs}

    # ── Billable projects from timesheet data ──
    billable_projects_in_data = sorted(
        set(df_raw["project"].unique()) - INTERNAL_PROJECTS
    )

    # ── Compute tracked cost per project ──
    tracked_cost_by_project = (
        df_raw[(df_raw["project"].isin(billable_projects_in_data)) & (df_raw["hourly_rate"] > 0)]
        .groupby("project")["cost"].sum()
        .to_dict()
    )
    tracked_hours_by_project = (
        df_raw[df_raw["project"].isin(billable_projects_in_data)]
        .groupby("project")["hours"].sum()
        .to_dict()
    )

    # ══════════════════════════════════════
    # ADMIN SECTION
    # ══════════════════════════════════════
    with st.expander("🔒 Administrar proyectos"):
        admin_pw = get_secret("ADMIN_PASSWORD", "")
        if not admin_pw:
            st.warning("ADMIN_PASSWORD no configurado en .env")
        else:
            if "admin_auth" not in st.session_state:
                st.session_state.admin_auth = False

            if not st.session_state.admin_auth:
                ac1, ac2 = st.columns([2, 1])
                with ac1:
                    pwd_input = st.text_input("Password de admin", type="password", key="admin_pwd_input")
                with ac2:
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button("Desbloquear"):
                        if pwd_input == admin_pw:
                            st.session_state.admin_auth = True
                            st.rerun()
                        else:
                            st.error("Password incorrecto")
            else:
                st.success("Admin desbloqueado")

                # Project selector
                configured_names = [p["name"] for p in project_configs]
                unconfigured = [p for p in billable_projects_in_data if p not in configured_names]

                admin_options = ["Agregar proyecto", "Editar proyecto existente"] if unconfigured else ["Editar proyecto existente"]
                admin_action = st.radio(
                    "Acción",
                    admin_options,
                    horizontal=True,
                    key="rent_admin_action",
                )

                if admin_action == "Agregar proyecto" and unconfigured:
                    new_proj_name = st.selectbox("Proyecto a configurar", unconfigured, key="rent_new_proj")
                    est, avg_m, months_b = _auto_estimate(new_proj_name, "")
                    st.caption(f"Costo promedio mensual tracked: **${avg_m:,.0f}**")

                    with st.form("add_project_form"):
                        apc1, apc2 = st.columns(2)
                        with apc1:
                            np_client = st.text_input("Cliente", key="np_client")
                            np_currency = st.selectbox("Moneda del contrato", ["MXN", "USD", "EUR"], key="np_currency")
                            np_original_amount = st.number_input("Monto original del contrato", min_value=0.0, step=1000.0, key="np_original_amount")
                            np_contract_type = st.selectbox("Tipo de contrato", ["proyecto", "mensual"], key="np_contract_type")
                            np_start = st.date_input("Fecha inicio del proyecto", key="np_start")
                            np_end = st.date_input("Fecha fin estimada", key="np_end")
                        with apc2:
                            np_margin = st.number_input("Margen objetivo (%)", min_value=0.0, max_value=100.0, value=30.0, step=5.0, key="np_margin")
                            np_status = st.selectbox("Estatus", ["activo", "completado", "pausado"], key="np_status")
                            np_notes = st.text_area("Notas", key="np_notes", height=80)
                            if np_currency != "MXN" and np_original_amount > 0:
                                np_rate = get_exchange_rate(np_currency, "MXN", str(np_start))
                                st.info(f"Tipo de cambio {np_currency}/MXN al {np_start}: **{np_rate:.4f}**\n\nValor en MXN: **${np_original_amount * np_rate:,.0f}**")
                            else:
                                np_rate = 1.0

                        st.markdown("**Gasto estimado pre-tracking**")
                        try:
                            est_auto, avg_m2, months_b2 = _auto_estimate(new_proj_name, str(np_start))
                        except Exception:
                            est_auto, avg_m2, months_b2 = 0.0, 0.0, 0.0
                        if months_b2 > 0:
                            st.caption(f"Sugerido: **${est_auto:,.0f}** (${avg_m2:,.0f}/mes × {months_b2:.1f} meses antes del tracking)")
                        np_estimated = st.number_input("Gasto pre-tracking ($)", min_value=0.0, value=float(est_auto), step=5000.0, key="np_estimated")

                        st.markdown("**Hitos de pago**")
                        n_milestones = st.number_input("Número de hitos", min_value=0, max_value=20, value=0, step=1, key="np_n_milestones")
                        milestones = []
                        for i in range(int(n_milestones)):
                            mc1, mc2, mc3, mc4 = st.columns([3, 2, 1, 2])
                            with mc1:
                                m_desc = st.text_input(f"Descripción hito {i+1}", key=f"np_m_desc_{i}")
                            with mc2:
                                m_amount = st.number_input(f"Monto {i+1}", min_value=0.0, step=10000.0, key=f"np_m_amount_{i}")
                            with mc3:
                                m_paid = st.checkbox("Pagado", key=f"np_m_paid_{i}")
                            with mc4:
                                m_date = st.date_input(f"Fecha {i+1}", key=f"np_m_date_{i}")
                            milestones.append({"description": m_desc, "amount": m_amount, "paid": m_paid, "date": str(m_date)})

                        if st.form_submit_button("Guardar proyecto"):
                            # Calculate MXN value using exchange rate
                            if np_currency != "MXN" and np_original_amount > 0:
                                save_rate = get_exchange_rate(np_currency, "MXN", str(np_start))
                                save_contract_value = round(np_original_amount * save_rate)
                            else:
                                save_rate = 1.0
                                save_contract_value = np_original_amount
                            new_entry = {
                                "name": new_proj_name,
                                "client": np_client,
                                "contract_value": save_contract_value,
                                "contract_type": np_contract_type,
                                "original_currency": np_currency,
                                "original_amount": np_original_amount,
                                "exchange_rate": round(save_rate, 4),
                                "estimated_spent_before": np_estimated,
                                "auto_estimate": est_auto,
                                "start_date": str(np_start),
                                "end_date": str(np_end),
                                "margin_target": np_margin,
                                "status": np_status,
                                "notes": np_notes,
                                "milestones": milestones,
                            }
                            project_configs.append(new_entry)
                            save_projects(project_configs)
                            st.success(f"Proyecto '{new_proj_name}' guardado")
                            st.rerun()

                elif admin_action == "Agregar proyecto" and not unconfigured:
                    st.info("Todos los proyectos facturables ya están configurados.")

                elif admin_action == "Editar proyecto existente" and configured_names:
                    edit_proj = st.selectbox("Proyecto", configured_names, key="rent_edit_proj")
                    pc = config_by_name.get(edit_proj)
                    if not pc:
                        st.warning("Proyecto no encontrado. Recarga la página.")
                        st.stop()

                    with st.form("edit_project_form"):
                        epc1, epc2 = st.columns(2)
                        with epc1:
                            ep_client = st.text_input("Cliente", value=pc.get("client", ""), key="ep_client")
                            ep_curr_options = ["MXN", "USD", "EUR"]
                            ep_curr_idx = ep_curr_options.index(pc.get("original_currency", "MXN")) if pc.get("original_currency", "MXN") in ep_curr_options else 0
                            ep_currency = st.selectbox("Moneda del contrato", ep_curr_options, index=ep_curr_idx, key="ep_currency")
                            ep_original_amount = st.number_input("Monto original", min_value=0.0, value=float(pc.get("original_amount", pc.get("contract_value", 0))), step=1000.0, key="ep_original_amount")
                            ep_contract_type = st.selectbox("Tipo de contrato", ["proyecto", "mensual"], index=["proyecto", "mensual"].index(pc.get("contract_type", "proyecto")), key="ep_contract_type")
                            ep_start = st.date_input("Fecha inicio", value=pd.Timestamp(pc["start_date"]).date() if pc.get("start_date") else date.today(), key="ep_start")
                            ep_end = st.date_input("Fecha fin estimada", value=pd.Timestamp(pc["end_date"]).date() if pc.get("end_date") else date.today(), key="ep_end")
                        with epc2:
                            ep_margin = st.number_input("Margen objetivo (%)", min_value=0.0, max_value=100.0, value=float(pc.get("margin_target", 30)), step=5.0, key="ep_margin")
                            ep_status = st.selectbox("Estatus", ["activo", "completado", "pausado"], index=["activo", "completado", "pausado"].index(pc.get("status", "activo")), key="ep_status")
                            ep_notes = st.text_area("Notas", value=pc.get("notes", ""), key="ep_notes", height=80)
                            if ep_currency != "MXN" and ep_original_amount > 0:
                                ep_rate = get_exchange_rate(ep_currency, "MXN", str(ep_start))
                                ep_contract_mxn = round(ep_original_amount * ep_rate)
                                st.info(f"TC {ep_currency}/MXN al {ep_start}: **{ep_rate:.4f}**\n\nValor MXN: **${ep_contract_mxn:,.0f}**")
                            else:
                                ep_rate = 1.0
                                ep_contract_mxn = ep_original_amount

                        try:
                            est_auto, avg_m, months_b = _auto_estimate(edit_proj, str(ep_start))
                        except Exception:
                            est_auto, avg_m, months_b = 0.0, 0.0, 0.0
                        st.markdown("**Gasto estimado pre-tracking**")
                        if months_b > 0:
                            st.caption(f"Sugerido: **${est_auto:,.0f}** (${avg_m:,.0f}/mes × {months_b:.1f} meses)")
                        ep_estimated = st.number_input("Gasto pre-tracking ($)", min_value=0.0, value=float(pc.get("estimated_spent_before", 0) or est_auto), step=5000.0, key="ep_estimated")

                        st.markdown("**Hitos de pago**")
                        existing_milestones = pc.get("milestones", [])
                        ep_n_milestones = st.number_input("Número de hitos", min_value=0, max_value=20, value=len(existing_milestones), step=1, key="ep_n_milestones")
                        milestones = []
                        for i in range(int(ep_n_milestones)):
                            em = existing_milestones[i] if i < len(existing_milestones) else {}
                            mc1, mc2, mc3, mc4 = st.columns([3, 2, 1, 2])
                            with mc1:
                                m_desc = st.text_input(f"Descripción {i+1}", value=em.get("description", ""), key=f"ep_m_desc_{i}")
                            with mc2:
                                m_amount = st.number_input(f"Monto {i+1}", min_value=0.0, value=float(em.get("amount", 0)), step=10000.0, key=f"ep_m_amount_{i}")
                            with mc3:
                                m_paid = st.checkbox("Pagado", value=em.get("paid", False), key=f"ep_m_paid_{i}")
                            with mc4:
                                m_date = st.date_input(f"Fecha {i+1}", value=pd.Timestamp(em["date"]).date() if em.get("date") else date.today(), key=f"ep_m_date_{i}")
                            milestones.append({"description": m_desc, "amount": m_amount, "paid": m_paid, "date": str(m_date)})

                        epc_save, epc_del = st.columns([1, 1])
                        submitted = st.form_submit_button("Guardar cambios")
                        if submitted:
                            # Recalculate MXN value
                            if ep_currency != "MXN" and ep_original_amount > 0:
                                save_rate = get_exchange_rate(ep_currency, "MXN", str(ep_start))
                                save_contract_value = round(ep_original_amount * save_rate)
                            else:
                                save_rate = 1.0
                                save_contract_value = ep_original_amount
                            pc.update({
                                "client": ep_client,
                                "contract_value": save_contract_value,
                                "contract_type": ep_contract_type,
                                "original_currency": ep_currency,
                                "original_amount": ep_original_amount,
                                "exchange_rate": round(save_rate, 4),
                                "estimated_spent_before": ep_estimated,
                                "auto_estimate": est_auto,
                                "start_date": str(ep_start),
                                "end_date": str(ep_end),
                                "margin_target": ep_margin,
                                "status": ep_status,
                                "notes": ep_notes,
                                "milestones": milestones,
                            })
                            save_projects(project_configs)
                            st.success("Cambios guardados")
                            st.rerun()

                    # Delete button outside form
                    if st.button(f"Eliminar '{edit_proj}'", type="secondary", key="rent_delete"):
                        st.session_state[f"confirm_delete_{edit_proj}"] = True
                    if st.session_state.get(f"confirm_delete_{edit_proj}"):
                        st.warning(f"¿Seguro que quieres eliminar **{edit_proj}**?")
                        dc1, dc2 = st.columns(2)
                        with dc1:
                            if st.button("Sí, eliminar", key="rent_confirm_del"):
                                project_configs[:] = [p for p in project_configs if p["name"] != edit_proj]
                                save_projects(project_configs)
                                st.session_state.pop(f"confirm_delete_{edit_proj}", None)
                                st.rerun()
                        with dc2:
                            if st.button("Cancelar", key="rent_cancel_del"):
                                st.session_state.pop(f"confirm_delete_{edit_proj}", None)
                                st.rerun()

                elif admin_action == "Editar proyecto existente" and not configured_names:
                    st.info("No hay proyectos configurados. Agrega uno primero.")

    # ══════════════════════════════════════
    # MAIN VIEW: RENTABILIDAD
    # ══════════════════════════════════════

    # Reload configs after potential edits
    project_configs = load_projects()
    active_configs = [p for p in project_configs if p.get("status", "activo") == "activo"]

    if not project_configs:
        st.info("No hay proyectos configurados. Usa la sección de admin para agregar proyectos.")
    else:
        # Build summary data for each configured project
        rentab_data = []
        for pc in project_configs:
            name = pc["name"]
            contract = pc.get("contract_value", 0)
            ctype = pc.get("contract_type", "proyecto")
            est_before = pc.get("estimated_spent_before", 0)
            tracked = tracked_cost_by_project.get(name, 0)
            target = pc.get("margin_target", 30)

            # Burn rate (monthly avg from tracked data)
            proj_weeks = df_raw[(df_raw["project"] == name) & (df_raw["hourly_rate"] > 0)].groupby("week_start")["cost"].sum()
            avg_weekly = proj_weeks.mean() if not proj_weeks.empty else 0
            burn_monthly = avg_weekly * 4.33

            # For monthly contracts, use the higher of: tracked burn rate vs
            # est_before / months_active (captures untracked costs like full-time people)
            if ctype == "mensual" and est_before > 0:
                try:
                    proj_start = pd.Timestamp(pc.get("start_date"))
                    months_active = max((pd.Timestamp("today") - proj_start).days / 30.44, 1)
                    burn_from_est = est_before / months_active
                    burn_monthly = max(burn_monthly, burn_from_est)
                except Exception:
                    pass

            milestones = pc.get("milestones", [])
            total_facturado = sum(m.get("amount", 0) for m in milestones)
            total_cobrado = sum(m.get("amount", 0) for m in milestones if m.get("paid"))

            if ctype == "mensual":
                # Monthly: compare monthly cost vs monthly income
                total_spent = burn_monthly  # display as "gasto mensual"
                margin = contract - burn_monthly
                pct_used = (burn_monthly / contract * 100) if contract > 0 else 0
                pct_margin = (margin / contract * 100) if contract > 0 else 0
                months_remaining = 0  # not applicable for monthly
            else:
                # Lump sum: compare total accumulated cost vs contract
                total_spent = est_before + tracked
                margin = contract - total_spent if contract > 0 else 0
                pct_used = (total_spent / contract * 100) if contract > 0 else 0
                pct_margin = (margin / contract * 100) if contract > 0 else 0
                months_remaining = (margin / burn_monthly) if burn_monthly > 0 and margin > 0 else 0

            rentab_data.append({
                "name": name,
                "client": pc.get("client", ""),
                "status": pc.get("status", "activo"),
                "contract_type": ctype,
                "contract": contract,
                "est_before": est_before,
                "tracked": tracked,
                "total_spent": total_spent,
                "margin": margin,
                "pct_used": pct_used,
                "pct_margin": pct_margin,
                "target": target,
                "burn_monthly": burn_monthly,
                "months_remaining": months_remaining,
                "milestones": milestones,
                "total_facturado": total_facturado,
                "total_cobrado": total_cobrado,
                "original_currency": pc.get("original_currency", "MXN"),
                "original_amount": pc.get("original_amount", contract),
                "exchange_rate": pc.get("exchange_rate", 1.0),
            })

        # Sort by % used descending (most at-risk first)
        rentab_data.sort(key=lambda x: x["pct_used"], reverse=True)

        # ── Separate project vs monthly ──
        proj_only = [r for r in rentab_data if r["contract_type"] == "proyecto"]
        monthly_only = [r for r in rentab_data if r["contract_type"] == "mensual"]

        # ── KPI cards (project-type only for totals) ──
        total_contracts = sum(r["contract"] for r in proj_only)
        total_spent_proj = sum(r["total_spent"] for r in proj_only)
        total_margin_proj = total_contracts - total_spent_proj
        avg_pct_margin = (total_margin_proj / total_contracts * 100) if total_contracts > 0 else 0
        total_cobrado_all = sum(r["total_cobrado"] for r in rentab_data)

        rk1, rk2, rk3, rk4, rk5 = st.columns(5)
        rk1.metric("Contratos (proyecto)", f"${total_contracts:,.0f}")
        rk2.metric("Gastado acumulado", f"${total_spent_proj:,.0f}")
        rk3.metric("Margen bruto", f"${total_margin_proj:,.0f}")
        rk4.metric("Margen promedio", f"{avg_pct_margin:.1f}%")
        rk5.metric("Proyectos activos", f"{len([r for r in rentab_data if r['status'] == 'activo'])}")

        st.markdown("")

        def _rentab_bar_chart(data, title):
            """Render horizontal bar chart for a list of rentab_data entries."""
            if not data:
                return
            data_sorted = sorted(data, key=lambda x: x["pct_used"], reverse=True)
            bar_names = [r["name"] for r in data_sorted]
            bar_pcts = [min(r["pct_used"], 150) for r in data_sorted]
            bar_colors = []
            for r in data_sorted:
                if r["pct_used"] > 85:
                    bar_colors.append("#dc2626")
                elif r["pct_used"] > 60:
                    bar_colors.append("#d97706")
                else:
                    bar_colors.append("#16a34a")

            is_monthly = data_sorted[0].get("contract_type") == "mensual"
            fig = go.Figure()
            fig.add_trace(go.Bar(
                y=bar_names[::-1],
                x=bar_pcts[::-1],
                orientation="h",
                marker_color=bar_colors[::-1],
                text=[f"{p:.0f}%" for p in bar_pcts[::-1]],
                textposition="auto",
                hovertemplate=[
                    f"<b>{r['name']}</b><br>"
                    + (f"Ingreso mensual: ${r['contract']:,.0f}<br>"
                       f"Gasto mensual: ${r['burn_monthly']:,.0f}<br>"
                       f"Margen mensual: ${r['margin']:,.0f} ({r['pct_margin']:.1f}%)"
                       if is_monthly else
                       f"Contrato: ${r['contract']:,.0f}<br>"
                       f"Gastado: ${r['total_spent']:,.0f} ({r['pct_used']:.1f}%)<br>"
                       f"Margen: ${r['margin']:,.0f} ({r['pct_margin']:.1f}%)<br>"
                       f"Burn rate: ${r['burn_monthly']:,.0f}/mes<br>"
                       f"Meses restantes: {r['months_remaining']:.1f}")
                    + "<extra></extra>"
                    for r in data_sorted[::-1]
                ],
            ))
            max_pct = max(bar_pcts) if bar_pcts else 100
            fig.update_layout(
                **PLOTLY_LAYOUT,
                title=title,
                xaxis_title="% consumido" if not is_monthly else "% del ingreso mensual gastado",
                yaxis_title="",
                height=max(300, len(bar_names) * 45),
                xaxis=dict(range=[0, max(max_pct + 10, 110)], ticksuffix="%"),
            )
            fig.update_layout(hovermode="closest")
            fig.add_vline(x=60, line_dash="dot", line_color="#d97706", opacity=0.5, annotation_text="60%", annotation_position="top")
            fig.add_vline(x=85, line_dash="dot", line_color="#dc2626", opacity=0.5, annotation_text="85%", annotation_position="top")
            fig.add_vline(x=100, line_dash="dash", line_color="#0f172a", opacity=0.7, annotation_text="100%", annotation_position="top")
            st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

        # ── Charts ──
        if proj_only:
            _rentab_bar_chart(proj_only, "Contratos por proyecto: presupuesto consumido")
        if monthly_only:
            _rentab_bar_chart(monthly_only, "Contratos mensuales: gasto vs ingreso")

        # ── Per-project detail cards ──
        for r in rentab_data:
            status_badge = {"activo": "🟢", "completado": "✅", "pausado": "⏸️"}.get(r["status"], "")
            is_monthly = r.get("contract_type") == "mensual"
            label_suffix = "/mes" if is_monthly else ""
            with st.expander(f"{status_badge} **{r['name']}** — {r['client']}  |  {r['pct_used']:.0f}% consumido  |  Margen: {r['pct_margin']:.0f}%  {'(mensual)' if is_monthly else ''}"):
                dc1, dc2, dc3, dc4 = st.columns(4)
                if is_monthly:
                    dc1.metric("Ingreso mensual", f"${r['contract']:,.0f}")
                    dc2.metric("Gasto mensual", f"${r['burn_monthly']:,.0f}")
                    dc3.metric("Margen mensual", f"${r['margin']:,.0f}", delta=f"{r['pct_margin']:.1f}%")
                    dc4.metric("% costo/ingreso", f"{r['pct_used']:.1f}%")
                else:
                    dc1.metric("Contrato", f"${r['contract']:,.0f}")
                    dc2.metric("Gastado total", f"${r['total_spent']:,.0f}")
                    dc3.metric("Margen", f"${r['margin']:,.0f}", delta=f"{r['pct_margin']:.1f}%")
                    dc4.metric("Burn rate", f"${r['burn_monthly']:,.0f}/mes",
                               delta=f"{r['months_remaining']:.1f} meses rest." if r["months_remaining"] > 0 else "—")

                # Currency info
                if r["original_currency"] != "MXN":
                    st.caption(f"Contrato original: {r['original_currency']}${r['original_amount']:,.0f}  |  TC: {r['exchange_rate']:.4f} {r['original_currency']}/MXN")

                # Breakdown
                bc1, bc2 = st.columns(2)
                with bc1:
                    if is_monthly:
                        st.markdown(f"""
| Concepto | Monto/mes |
|:--|--:|
| Ingreso contrato | ${r['contract']:,.0f} |
| Gasto promedio | ${r['burn_monthly']:,.0f} |
| **Margen mensual** | **${r['margin']:,.0f}** |
| Margen objetivo | {r['target']:.0f}% |
""")
                    else:
                        st.markdown(f"""
| Concepto | Monto |
|:--|--:|
| Gasto pre-tracking (estimado) | ${r['est_before']:,.0f} |
| Gasto tracked (timesheet) | ${r['tracked']:,.0f} |
| **Total gastado** | **${r['total_spent']:,.0f}** |
| Margen objetivo | {r['target']:.0f}% |
""")

                # Milestones
                with bc2:
                    if r["milestones"]:
                        st.markdown("**Hitos de pago**")
                        for m in r["milestones"]:
                            paid_icon = "✅" if m.get("paid") else "⏳"
                            st.markdown(f"- {paid_icon} {m['description']}: **${m.get('amount', 0):,.0f}** — {m.get('date', '')}")
                        st.markdown(f"**Total facturado:** ${r['total_facturado']:,.0f}  |  **Cobrado:** ${r['total_cobrado']:,.0f}")

    # ── Unconfigured projects reminder (always visible) ──
    configured_names = {p["name"] for p in project_configs}
    unconfigured_projs = [
        (p, tracked_cost_by_project.get(p, 0), tracked_hours_by_project.get(p, 0))
        for p in billable_projects_in_data if p not in configured_names
    ]
    if unconfigured_projs:
        st.markdown("")
        st.markdown("### Proyectos sin configurar")
        st.caption("Estos proyectos tienen horas registradas pero no se han configurado para seguimiento de rentabilidad.")
        uc_lines = []
        for name, cost, hrs in sorted(unconfigured_projs, key=lambda x: -x[1]):
            uc_lines.append(f"| {name} | ${cost:,.0f} | {hrs:,.2f} |")
        st.markdown("| Proyecto | Costo tracked | Horas tracked |\n|:--|--:|--:|\n" + "\n".join(uc_lines))
