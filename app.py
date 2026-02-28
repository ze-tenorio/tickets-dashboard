"""
Dashboard de análise de tickets Jira.
Execução: streamlit run app.py
"""
import subprocess
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Caminhos (prioridade: Jira.csv, depois Jira - Jira.csv.csv)
ROOT = Path(__file__).resolve().parent
CSV_RAW_OPTIONS = [ROOT / "Jira.csv", ROOT / "Jira - Jira.csv.csv"]
CSV_CLEAN = ROOT / "jira_tickets_clean.csv"
NORMALIZE_SCRIPT = ROOT / "scripts" / "normalize_jira_csv.py"


def load_data():
    """Carrega o CSV limpo. Se existir jira_tickets_clean.csv, usa ele (inclui edições manuais). Senão, gera a partir de Jira.csv."""
    if CSV_CLEAN.exists():
        df = pd.read_csv(CSV_CLEAN)
    else:
        raw_path = next((p for p in CSV_RAW_OPTIONS if p.exists()), None)
        if raw_path and NORMALIZE_SCRIPT.exists():
            subprocess.run(
                [sys.executable, str(NORMALIZE_SCRIPT), str(raw_path), str(CSV_CLEAN)],
                cwd=str(ROOT),
                check=True,
                capture_output=True,
            )
            df = pd.read_csv(CSV_CLEAN)
        else:
            st.error("Nenhum dado encontrado. Coloque Jira.csv na raiz ou adicione jira_tickets_clean.csv.")
            st.stop()
    return df


def prepare_data(df: pd.DataFrame) -> pd.DataFrame:
    """Converte datas e preenche vazios."""
    df = df.copy()
    for col in ["Created", "Updated", "Resolved", "Due date", "Status Category Changed"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].fillna("").astype(str)
    return df


def apply_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    """Aplica filtros da sidebar."""
    out = df.copy()
    if filters.get("status"):
        out = out[out["Status"].isin(filters["status"])]
    if filters.get("priority"):
        out = out[out["Priority"].isin(filters["priority"])]
    if filters.get("assignee"):
        out = out[out["Assignee"].isin(filters["assignee"])]
    if filters.get("produto"):
        out = out[out["Custom field (Produto)"].isin(filters["produto"])]
    if filters.get("date_min") is not None and "Created" in out.columns:
        out = out[pd.to_datetime(out["Created"], errors="coerce").dt.date >= filters["date_min"]]
    if filters.get("date_max") is not None and "Created" in out.columns:
        out = out[pd.to_datetime(out["Created"], errors="coerce").dt.date <= filters["date_max"]]
    return out


# Configuração da página
st.set_page_config(
    page_title="Dashboard Tickets Jira",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Título
st.title("📊 Análise de tickets Jira")
st.caption("Volume, status, prioridade, responsáveis e produto")

# Carregar dados
df_raw = load_data()
df = prepare_data(df_raw)

# Sidebar: filtros
st.sidebar.header("Filtros")
date_min = df["Created"].min()
date_max = df["Created"].max()
if pd.notna(date_min) and pd.notna(date_max):
    date_min, date_max = date_min.date(), date_max.date()
    f_date_min = st.sidebar.date_input("Criado a partir de", value=date_min, min_value=date_min, max_value=date_max)
    f_date_max = st.sidebar.date_input("Criado até", value=date_max, min_value=date_min, max_value=date_max)
else:
    f_date_min = f_date_max = None

status_options = sorted(df["Status"].dropna().unique().tolist())
f_status = st.sidebar.multiselect("Status", options=status_options, default=[])

priority_options = sorted(df["Priority"].dropna().unique().tolist())
f_priority = st.sidebar.multiselect("Prioridade", options=priority_options, default=[])

assignee_options = sorted(df["Assignee"].dropna().replace("", "(sem assignee)").unique().tolist())
assignee_options = [x if x != "(sem assignee)" else "" for x in assignee_options]
f_assignee = st.sidebar.multiselect("Responsável", options=assignee_options, default=[])

produto_options = sorted(df["Custom field (Produto)"].dropna().replace("", "(vazio)").unique().tolist())
produto_options = [x if x != "(vazio)" else "" for x in produto_options]
f_produto = st.sidebar.multiselect("Produto / Área", options=produto_options, default=[])

filters = {
    "date_min": f_date_min,
    "date_max": f_date_max,
    "status": f_status if f_status else None,
    "priority": f_priority if f_priority else None,
    "assignee": f_assignee if f_assignee else None,
    "produto": f_produto if f_produto else None,
}
df_f = apply_filters(df, filters)

# KPIs
st.subheader("Visão geral")
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total de tickets", len(df_f))
with col2:
    em_aberto = df_f[~df_f["Status"].str.contains("Done", case=False, na=False)]
    st.metric("Em aberto", len(em_aberto))
with col3:
    concluidos = df_f[df_f["Status"].str.contains("Done", case=False, na=False)]
    st.metric("Concluídos", len(concluidos))
with col4:
    p0 = df_f[df_f["Priority"].str.contains("P0", na=False)]
    st.metric("P0 - Críticos", len(p0))

st.divider()

# Volume ao longo do tempo (tickets criados por semana)
st.subheader("Volume ao longo do tempo (tickets criados)")
if df_f["Created"].notna().any():
    df_week = df_f.copy()
    df_week["_semana"] = pd.to_datetime(df_week["Created"]).dt.to_period("W").astype(str)
    by_week = df_week.groupby("_semana").size().reset_index(name="Tickets")
    by_week = by_week.rename(columns={"_semana": "Semana"})
    fig_time = px.bar(
        by_week,
        x="Semana",
        y="Tickets",
        labels={"Semana": "Semana", "Tickets": "Tickets criados"},
        color="Tickets",
        color_continuous_scale="Blues",
    )
    fig_time.update_layout(showlegend=False, margin=dict(t=20), height=320)
    st.plotly_chart(fig_time, use_container_width=True)
else:
    st.info("Sem datas de criação para exibir.")

st.divider()

# Duas colunas: Status e Prioridade
st.subheader("Distribuição por status e prioridade")
c1, c2 = st.columns(2)
with c1:
    status_counts = df_f["Status"].value_counts().reset_index()
    status_counts.columns = ["Status", "Quantidade"]
    fig_status = px.bar(
        status_counts,
        x="Quantidade",
        y="Status",
        orientation="h",
        labels={"Quantidade": "Tickets", "Status": ""},
        color="Quantidade",
        color_continuous_scale="Teal",
    )
    fig_status.update_layout(showlegend=False, margin=dict(t=20), height=340, yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig_status, use_container_width=True)
with c2:
    priority_counts = df_f["Priority"].value_counts().reset_index()
    priority_counts.columns = ["Prioridade", "Quantidade"]
    fig_prio = px.bar(
        priority_counts,
        x="Quantidade",
        y="Prioridade",
        orientation="h",
        labels={"Quantidade": "Tickets", "Prioridade": ""},
        color="Quantidade",
        color_continuous_scale="Oranges",
    )
    fig_prio.update_layout(showlegend=False, margin=dict(t=20), height=340, yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig_prio, use_container_width=True)

# Responsáveis e Produto
st.subheader("Responsáveis e produto / área")
c3, c4 = st.columns(2)
with c3:
    assignee_counts = df_f["Assignee"].replace("", "(sem assignee)").value_counts().head(15).reset_index()
    assignee_counts.columns = ["Responsável", "Quantidade"]
    fig_assignee = px.bar(
        assignee_counts,
        x="Quantidade",
        y="Responsável",
        orientation="h",
        labels={"Quantidade": "Tickets", "Responsável": ""},
        color="Quantidade",
        color_continuous_scale="Purples",
    )
    fig_assignee.update_layout(showlegend=False, margin=dict(t=20), height=380, yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig_assignee, use_container_width=True)
with c4:
    produto_counts = df_f["Custom field (Produto)"].replace("", "(vazio)").value_counts().reset_index()
    produto_counts.columns = ["Produto / Área", "Quantidade"]
    fig_produto = px.bar(
        produto_counts,
        x="Quantidade",
        y="Produto / Área",
        orientation="h",
        labels={"Quantidade": "Tickets", "Produto / Área": ""},
        color="Quantidade",
        color_continuous_scale="Greens",
    )
    fig_produto.update_layout(showlegend=False, margin=dict(t=20), height=380, yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig_produto, use_container_width=True)

# Status Category (donut)
st.subheader("Status category (fluxo)")
if "Status Category" in df_f.columns and df_f["Status Category"].str.strip().ne("").any():
    cat_counts = df_f["Status Category"].replace("", "(vazio)").value_counts().reset_index()
    cat_counts.columns = ["Categoria", "Quantidade"]
    fig_cat = go.Figure(
        data=[
            go.Pie(
                labels=cat_counts["Categoria"],
                values=cat_counts["Quantidade"],
                hole=0.5,
                marker_colors=px.colors.qualitative.Set2[: len(cat_counts)],
            )
        ]
    )
    fig_cat.update_layout(margin=dict(t=20), height=320, showlegend=True, legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig_cat, use_container_width=True)
else:
    st.caption("Sem dados de Status Category.")

st.divider()

# Tabela resumida
st.subheader("Lista de tickets (amostra)")
cols_show = ["Issue key", "Summary", "Status", "Priority", "Assignee", "Custom field (Produto)", "Created"]
cols_show = [c for c in cols_show if c in df_f.columns]
df_show = df_f[cols_show].head(100)
df_show["Created"] = df_show["Created"].dt.strftime("%Y-%m-%d %H:%M") if "Created" in df_show.columns else df_show["Created"]
st.dataframe(df_show, use_container_width=True, hide_index=True)
if len(df_f) > 100:
    st.caption(f"Exibindo 100 de {len(df_f)} tickets. Use os filtros para refinar.")
