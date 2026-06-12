import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from datetime import date, timedelta

from auth import authenticate, get_youtube, get_analytics
from data import (
    fetch_all_videos, videos_to_df,
    fetch_channel_analytics, fetch_video_analytics,
    fetch_retention_curve, build_guest_summary,
    TIPO_ORDEN, TIPO_COLORS,
)

st.set_page_config(page_title="Crudo y Queso — Dashboard", layout="wide", page_icon="▶️")

st.markdown("""
<style>
    .metric-card {background:#f8f9fa;border-radius:12px;padding:16px;text-align:center;}
    .rec-card {background:#fff3cd;border-left:4px solid #ffc107;padding:12px;border-radius:4px;margin:8px 0;}
    .rec-good {background:#d4edda;border-left:4px solid #28a745;padding:12px;border-radius:4px;margin:8px 0;}
    .rec-bad {background:#f8d7da;border-left:4px solid #dc3545;padding:12px;border-radius:4px;margin:8px 0;}
    .vid-card {border:1px solid #e0e0e0;border-radius:10px;padding:10px;text-align:center;background:#fff;}
    .vid-title {font-size:0.8rem;font-weight:600;margin-top:6px;line-height:1.3;}
    .vid-stat {font-size:0.75rem;color:#666;margin:2px 0;}
    .accion-card {background:#1e1e2f;border:1px solid #444;border-left:4px solid #FF0050;padding:14px 16px;border-radius:6px;margin:10px 0;}
</style>
""", unsafe_allow_html=True)

TIPO_ICONS = {"Short": "🎬", "Mediano": "🎯", "Completo": "📹"}


def video_cards(df_cards: "pd.DataFrame", n_cols: int = 4, max_videos: int = 12):
    """Muestra tarjetas de video con miniatura, título y métricas."""
    videos = df_cards.head(max_videos).to_dict("records")
    rows = [videos[i:i+n_cols] for i in range(0, len(videos), n_cols)]
    for row in rows:
        cols = st.columns(n_cols)
        for col, v in zip(cols, row):
            with col:
                thumb = v.get("thumbnail", "")
                if thumb:
                    st.image(thumb, use_container_width=True)
                views = v.get("views", 0)
                likes = v.get("likes", 0)
                guest = v.get("guest", "")
                title = v.get("title", "")
                tipo = v.get("tipo", "")
                tipo_label = f"{TIPO_ICONS.get(tipo,'')} {tipo}"
                st.markdown(f"""
<div class="vid-title">{title[:55]}{'...' if len(title)>55 else ''}</div>
<div class="vid-stat">👤 {guest}</div>
<div class="vid-stat">👁️ {int(views):,} vistas &nbsp; ❤️ {int(likes):,}</div>
<div class="vid-stat">{tipo_label}</div>
""", unsafe_allow_html=True)


def semaforo(valor, promedio, invertido=False):
    """Devuelve emoji semáforo comparando valor contra el promedio del canal."""
    if promedio <= 0:
        return "⚪"
    ratio = valor / promedio
    if invertido:
        ratio = 1 / ratio if ratio > 0 else 0
    if ratio >= 1.1:
        return "🟢"
    elif ratio >= 0.8:
        return "🟡"
    else:
        return "🔴"


# ── Autenticación ─────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner="Conectando con YouTube...")
def load_services():
    creds = authenticate()
    return get_youtube(creds), get_analytics(creds)

try:
    youtube, analytics = load_services()
except FileNotFoundError:
    st.error("No se encontró `client_secrets.json`. Copialo en la misma carpeta.")
    st.stop()

# ── Datos del canal ───────────────────────────────────────────────────────────
@st.cache_data(show_spinner="Cargando canal...", ttl=86400)
def load_channel():
    res = youtube.channels().list(part="snippet,statistics", mine=True).execute()
    return res["items"][0]

channel = load_channel()
ch_id   = channel["id"]
ch_name = channel["snippet"]["title"]
ch_st   = channel["statistics"]

@st.cache_data(show_spinner="Cargando videos...", ttl=86400)
def load_videos(cid):
    return videos_to_df(fetch_all_videos(youtube, cid))

df_all = load_videos(ch_id)

# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.header("Filtros")

periodo_opciones = {
    "Última semana":    7,
    "Último mes":       30,
    "Últimos 3 meses":  90,
    "Últimos 6 meses":  180,
    "Último año":       365,
    "Todo el tiempo":   9999,
}
periodo_sel = st.sidebar.selectbox("Período", list(periodo_opciones.keys()), index=4)
dias = periodo_opciones[periodo_sel]
end_date   = date.today()
start_date = date.today() - timedelta(days=dias) if dias < 9999 else date(2000, 1, 1)

video_type = st.sidebar.radio("Tipo de video", ["Todos", "Solo Shorts", "Solo Medianos", "Solo Completos"])

st.sidebar.divider()
if st.sidebar.button("🔄 Recargar datos del canal"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.caption("Los datos se actualizan automáticamente 1 vez por día. Usá este botón para forzar una actualización ahora.")

# ── Filtrar ───────────────────────────────────────────────────────────────────
df = df_all.copy()
if not df.empty:
    df = df[(df["published_at"].dt.date >= start_date) & (df["published_at"].dt.date <= end_date)]
    if video_type == "Solo Shorts":
        df = df[df["tipo"] == "Short"]
    elif video_type == "Solo Medianos":
        df = df[df["tipo"] == "Mediano"]
    elif video_type == "Solo Completos":
        df = df[df["tipo"] == "Completo"]

# ── Header ────────────────────────────────────────────────────────────────────
st.title(f"▶️  {ch_name} — Dashboard")
st.caption("🎬 Shorts (≤70 seg) · 🎯 Medianos (clips de 1-60 min) · 📹 Completos (capítulos +1 hora)")

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Suscriptores", f"{int(ch_st.get('subscriberCount', 0)):,}")
c2.metric("Videos totales", f"{int(ch_st.get('videoCount', 0)):,}")
c3.metric("Vistas totales", f"{int(ch_st.get('viewCount', 0)):,}")
counts_all = df_all["tipo"].value_counts() if not df_all.empty else pd.Series(dtype=int)
c4.metric("🎬 Shorts", f"{counts_all.get('Short', 0):,}")
c5.metric("🎯 Medianos", f"{counts_all.get('Mediano', 0):,}")
c6.metric("📹 Completos", f"{counts_all.get('Completo', 0):,}")

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10 = st.tabs([
    "🏆 Invitados",
    "🎬 Shorts",
    "🎯 Medianos",
    "📹 Completos",
    "📈 Evolución",
    "🔁 Retención",
    "🚦 Semáforo",
    "💡 Recomendaciones",
    "✅ Plan de Acción",
    "🔧 Diagnóstico",
])

# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — INVITADOS
# ════════════════════════════════════════════════════════════════════════════
with tab1:
    st.subheader("Impacto por invitado")

    if df.empty:
        st.info("Sin datos para el período seleccionado.")
    else:
        guest_df = build_guest_summary(df)

        # Top videos del período con miniatura
        st.markdown("#### Top videos del período")
        video_cards(df.sort_values("views", ascending=False), n_cols=4, max_videos=8)
        st.divider()

        # Gráfico principal: vistas totales por invitado
        fig_g = px.bar(
            guest_df.head(20),
            x="Vistas totales",
            y="Invitado",
            orientation="h",
            color="Vistas totales",
            color_continuous_scale="Reds",
            title="Vistas totales por invitado (Shorts + Medianos + Completos)",
        )
        fig_g.update_layout(yaxis={"categoryorder": "total ascending"}, height=500, coloraxis_showscale=False)
        st.plotly_chart(fig_g, use_container_width=True)

        # Comparación Shorts vs Medianos vs Completos por invitado
        top_guests = guest_df.head(10)["Invitado"].tolist()
        df_top = df[df["guest"].isin(top_guests)]
        comp = df_top.groupby(["guest", "tipo"])["views"].sum().reset_index()

        fig_comp = px.bar(
            comp,
            x="guest",
            y="views",
            color="tipo",
            barmode="group",
            category_orders={"tipo": TIPO_ORDEN},
            color_discrete_map=TIPO_COLORS,
            labels={"guest": "Invitado", "views": "Vistas", "tipo": "Formato"},
            title="Top 10 invitados — Shorts vs Medianos vs Completos",
        )
        fig_comp.update_layout(xaxis_tickangle=-30)
        st.plotly_chart(fig_comp, use_container_width=True)

        # Tabla completa
        st.subheader("Tabla detallada por invitado")
        cols_tab = ["Invitado", "Videos", "Vistas totales",
                     "Videos Short", "Vistas Short",
                     "Videos Mediano", "Vistas Mediano",
                     "Videos Completo", "Vistas Completo",
                     "Likes totales", "Comentarios"]
        st.dataframe(
            guest_df[cols_tab].rename(columns={
                "Videos Short": "🎬 Videos", "Vistas Short": "🎬 Vistas",
                "Videos Mediano": "🎯 Videos", "Vistas Mediano": "🎯 Vistas",
                "Videos Completo": "📹 Videos", "Vistas Completo": "📹 Vistas",
            }).style.format({
                "Vistas totales": "{:,}", "🎬 Vistas": "{:,}", "🎯 Vistas": "{:,}", "📹 Vistas": "{:,}",
                "Likes totales": "{:,}", "Comentarios": "{:,}",
            }),
            use_container_width=True,
            hide_index=True,
        )

        # Detalle por invitado
        st.subheader("Detalle por invitado")
        invitados_lista = ["— Elegí un invitado —"] + sorted(df["guest"].unique().tolist())
        inv_sel = st.selectbox("Invitado", invitados_lista)
        if inv_sel != "— Elegí un invitado —":
            df_inv = df[df["guest"] == inv_sel].sort_values("views", ascending=False)
            ia, ib, ic, id_, ie = st.columns(5)
            ia.metric("Videos totales", len(df_inv))
            ib.metric("Vistas totales", f"{df_inv['views'].sum():,}")
            for col, tipo in zip([ic, id_, ie], TIPO_ORDEN):
                sub = df_inv[df_inv["tipo"] == tipo]
                col.metric(f"{TIPO_ICONS[tipo]} {tipo}", f"{sub['views'].sum():,}")
            video_cards(df_inv, n_cols=4, max_videos=16)
            with st.expander("Ver tabla completa"):
                st.dataframe(
                    df_inv[["thumbnail","title","tipo","published_at","views","likes","comments","like_rate"]]
                    .rename(columns={"thumbnail":"Miniatura","title":"Título","tipo":"Formato",
                                     "published_at":"Publicado","views":"Vistas","likes":"Likes",
                                     "comments":"Comentarios","like_rate":"% Likes"}),
                    column_config={"Miniatura": st.column_config.ImageColumn("Miniatura", width="small")},
                    use_container_width=True, hide_index=True,
                )

        st.divider()
        # Buscar invitado específico
        st.subheader("Buscar por palabra clave")
        keyword = st.text_input("Escribí un término para buscar en títulos y descripciones")
        if keyword:
            mask = (
                df["title"].str.lower().str.contains(keyword.lower(), na=False) |
                df["description"].str.lower().str.contains(keyword.lower(), na=False) |
                df["guest"].str.lower().str.contains(keyword.lower(), na=False)
            )
            df_search = df[mask].sort_values("views", ascending=False)
            if df_search.empty:
                st.warning("No se encontraron videos con ese término.")
            else:
                st.metric("Vistas totales de la búsqueda", f"{df_search['views'].sum():,}")
                video_cards(df_search, n_cols=4, max_videos=12)
                st.dataframe(
                    df_search[["thumbnail", "title", "guest", "published_at", "views", "likes", "comments", "tipo"]]
                    .rename(columns={
                        "thumbnail": "Miniatura", "title": "Título", "guest": "Invitado",
                        "published_at": "Publicado", "views": "Vistas", "likes": "Likes",
                        "comments": "Comentarios", "tipo": "Formato",
                    }),
                    column_config={"Miniatura": st.column_config.ImageColumn("Miniatura", width="small")},
                    use_container_width=True, hide_index=True,
                )

# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — SHORTS
# ════════════════════════════════════════════════════════════════════════════
with tab2:
    df_shorts = df[df["tipo"] == "Short"] if not df.empty else pd.DataFrame()
    st.subheader(f"🎬 Análisis de Shorts ({len(df_shorts)} en el período)")
    st.caption("Videos de hasta 70 segundos. Lo único que importa: el gancho de los primeros 1-3 segundos.")

    if df_shorts.empty:
        st.info("Sin Shorts en el período seleccionado.")
    else:
        s1, s2, s3 = st.columns(3)
        s1.metric("Vistas totales Shorts", f"{df_shorts['views'].sum():,}")
        s2.metric("Promedio de vistas", f"{int(df_shorts['views'].mean()):,}")
        s3.metric("Mejor Short", f"{df_shorts['views'].max():,} vistas")

        st.markdown("#### Top Shorts")
        video_cards(df_shorts.sort_values("views", ascending=False), n_cols=4, max_videos=8)
        st.divider()

        top_shorts = df_shorts.nlargest(20, "views")
        fig_s = px.bar(
            top_shorts,
            x="views",
            y="title",
            orientation="h",
            color="views",
            color_continuous_scale="RdPu",
            title="Top 20 Shorts por vistas",
            labels={"views": "Vistas", "title": ""},
        )
        fig_s.update_layout(yaxis={"categoryorder": "total ascending"}, height=550, coloraxis_showscale=False)
        st.plotly_chart(fig_s, use_container_width=True)

        sg = df_shorts.groupby("guest").agg(
            videos=("id", "count"),
            vistas=("views", "sum"),
            likes=("likes", "sum"),
        ).reset_index().sort_values("vistas", ascending=False)

        fig_sg = px.bar(
            sg.head(15),
            x="guest",
            y="vistas",
            color="vistas",
            color_continuous_scale="Reds",
            title="Vistas de Shorts por invitado",
            labels={"guest": "Invitado", "vistas": "Vistas"},
        )
        fig_sg.update_layout(xaxis_tickangle=-30, coloraxis_showscale=False)
        st.plotly_chart(fig_sg, use_container_width=True)

        st.subheader("Shorts con mejor tasa de likes (engajamiento)")
        top_like = df_shorts[df_shorts["views"] >= 100].nlargest(15, "like_rate")
        fig_lr = px.bar(
            top_like,
            x="like_rate",
            y="title",
            orientation="h",
            color="like_rate",
            color_continuous_scale="Greens",
            title="% de likes sobre vistas (mínimo 100 vistas)",
            labels={"like_rate": "% Likes/Vistas", "title": ""},
        )
        fig_lr.update_layout(yaxis={"categoryorder": "total ascending"}, height=450, coloraxis_showscale=False)
        st.plotly_chart(fig_lr, use_container_width=True)

        with st.expander("Ver todos los Shorts"):
            st.dataframe(
                df_shorts[["title", "guest", "published_at", "views", "likes", "comments", "like_rate"]]
                .sort_values("views", ascending=False)
                .rename(columns={
                    "title": "Título", "guest": "Invitado", "published_at": "Publicado",
                    "views": "Vistas", "likes": "Likes", "comments": "Comentarios", "like_rate": "% Likes",
                }),
                use_container_width=True, hide_index=True,
            )

# ════════════════════════════════════════════════════════════════════════════
# TAB 3 — MEDIANOS
# ════════════════════════════════════════════════════════════════════════════
with tab3:
    df_med = df[df["tipo"] == "Mediano"] if not df.empty else pd.DataFrame()
    st.subheader(f"🎯 Análisis de Medianos ({len(df_med)} en el período)")
    st.caption("Clips de 1 a 60 minutos (recortes de la charla, momentos puntuales).")

    if df_med.empty:
        st.info("Sin videos Medianos en el período seleccionado.")
    else:
        m1, m2, m3 = st.columns(3)
        m1.metric("Vistas totales", f"{df_med['views'].sum():,}")
        m2.metric("Promedio de vistas", f"{int(df_med['views'].mean()):,}")
        m3.metric("Duración promedio", f"{df_med['duration_min'].mean():.1f} min")

        st.markdown("#### Top Medianos")
        video_cards(df_med.sort_values("views", ascending=False), n_cols=4, max_videos=8)
        st.divider()

        top_med = df_med.nlargest(20, "views")
        fig_m = px.bar(
            top_med,
            x="views",
            y="title",
            orientation="h",
            color="views",
            color_continuous_scale="Oranges",
            title="Top 20 Medianos por vistas",
            labels={"views": "Vistas", "title": ""},
        )
        fig_m.update_layout(yaxis={"categoryorder": "total ascending"}, height=550, coloraxis_showscale=False)
        st.plotly_chart(fig_m, use_container_width=True)

        # Retención (si hay datos de Analytics)
        df_van_m, err_m = fetch_video_analytics(analytics, start_date.isoformat(), end_date.isoformat())
        if not err_m and not df_van_m.empty:
            df_merged_m = df_med.merge(df_van_m, on="id", how="left", suffixes=("", "_analytics"))
            df_merged_m = df_merged_m.dropna(subset=["averageViewPercentage"])
            if not df_merged_m.empty:
                top_ret_m = df_merged_m.nlargest(15, "averageViewPercentage")
                fig_ret_m = px.bar(
                    top_ret_m,
                    x="averageViewPercentage",
                    y="title",
                    orientation="h",
                    color="averageViewPercentage",
                    color_continuous_scale="Greens",
                    title="Mejor retención promedio (%) — Medianos",
                    labels={"averageViewPercentage": "% Retención", "title": ""},
                )
                fig_ret_m.update_layout(yaxis={"categoryorder": "total ascending"}, height=450, coloraxis_showscale=False)
                st.plotly_chart(fig_ret_m, use_container_width=True)

        mg = df_med.groupby("guest").agg(
            videos=("id", "count"),
            vistas=("views", "sum"),
            likes=("likes", "sum"),
        ).reset_index().sort_values("vistas", ascending=False)

        fig_mg = px.bar(
            mg.head(15),
            x="guest",
            y="vistas",
            color="vistas",
            color_continuous_scale="Oranges",
            title="Vistas de Medianos por invitado",
            labels={"guest": "Invitado", "vistas": "Vistas"},
        )
        fig_mg.update_layout(xaxis_tickangle=-30, coloraxis_showscale=False)
        st.plotly_chart(fig_mg, use_container_width=True)

        with st.expander("Ver todos los Medianos"):
            st.dataframe(
                df_med[["title", "guest", "published_at", "views", "likes", "comments", "duration_min", "like_rate"]]
                .sort_values("views", ascending=False)
                .rename(columns={
                    "title": "Título", "guest": "Invitado", "published_at": "Publicado",
                    "views": "Vistas", "likes": "Likes", "comments": "Comentarios",
                    "duration_min": "Duración (min)", "like_rate": "% Likes",
                }),
                use_container_width=True, hide_index=True,
            )

# ════════════════════════════════════════════════════════════════════════════
# TAB 4 — COMPLETOS
# ════════════════════════════════════════════════════════════════════════════
with tab4:
    df_comp = df[df["tipo"] == "Completo"] if not df.empty else pd.DataFrame()
    st.subheader(f"📹 Análisis de Capítulos Completos ({len(df_comp)} en el período)")
    st.caption("Episodios de más de 1 hora — la entrevista completa.")

    if df_comp.empty:
        st.info("Sin Capítulos Completos en el período seleccionado.")
    else:
        l1, l2, l3 = st.columns(3)
        l1.metric("Vistas totales", f"{df_comp['views'].sum():,}")
        l2.metric("Promedio de vistas", f"{int(df_comp['views'].mean()):,}")
        l3.metric("Duración promedio", f"{df_comp['duration_min'].mean():.0f} min")

        st.markdown("#### Top Capítulos Completos")
        video_cards(df_comp.sort_values("views", ascending=False), n_cols=4, max_videos=8)
        st.divider()

        top_comp = df_comp.nlargest(20, "views")
        fig_l = px.bar(
            top_comp,
            x="views",
            y="title",
            orientation="h",
            color="views",
            color_continuous_scale="Reds",
            title="Top Capítulos Completos por vistas",
            labels={"views": "Vistas", "title": ""},
        )
        fig_l.update_layout(yaxis={"categoryorder": "total ascending"}, height=550, coloraxis_showscale=False)
        st.plotly_chart(fig_l, use_container_width=True)

        # Analytics por video (retención)
        st.subheader("Retención por capítulo (requiere Analytics API)")
        df_van, err = fetch_video_analytics(analytics, start_date.isoformat(), end_date.isoformat())

        if err:
            st.warning(f"Analytics API: {err}")
        elif df_van.empty:
            st.info("No hay datos de Analytics para el período.")
        else:
            df_merged = df_comp.merge(df_van, on="id", how="left", suffixes=("", "_analytics"))
            df_merged = df_merged.dropna(subset=["averageViewPercentage"])

            if not df_merged.empty:
                va1, va2 = st.columns(2)

                top_ret = df_merged.nlargest(15, "averageViewPercentage")
                fig_ret = px.bar(
                    top_ret,
                    x="averageViewPercentage",
                    y="title",
                    orientation="h",
                    color="averageViewPercentage",
                    color_continuous_scale="Greens",
                    title="Mejor retención promedio (%)",
                    labels={"averageViewPercentage": "% Retención", "title": ""},
                )
                fig_ret.update_layout(yaxis={"categoryorder": "total ascending"}, height=450, coloraxis_showscale=False)
                va2.plotly_chart(fig_ret, use_container_width=True)

                df_scatter = df_merged.dropna(subset=["averageViewPercentage", "duration_min"]).copy()
                size_col = "views_x" if "views_x" in df_scatter.columns else "views"
                fig_scatter = px.scatter(
                    df_scatter,
                    x="duration_min",
                    y="averageViewPercentage",
                    size=size_col,
                    color="guest",
                    hover_name="title",
                    title="Duración vs % de retención (burbuja = vistas)",
                    labels={"duration_min": "Duración (min)", "averageViewPercentage": "Retención %", "guest": "Invitado"},
                )
                va1.plotly_chart(fig_scatter, use_container_width=True)

        lg = df_comp.groupby("guest").agg(
            videos=("id", "count"),
            vistas=("views", "sum"),
            likes=("likes", "sum"),
        ).reset_index().sort_values("vistas", ascending=False)

        fig_lg = px.bar(
            lg.head(15),
            x="guest",
            y="vistas",
            color="vistas",
            color_continuous_scale="Reds",
            title="Vistas de Capítulos Completos por invitado",
            labels={"guest": "Invitado", "vistas": "Vistas"},
        )
        fig_lg.update_layout(xaxis_tickangle=-30, coloraxis_showscale=False)
        st.plotly_chart(fig_lg, use_container_width=True)

        with st.expander("Ver todos los Capítulos Completos"):
            st.dataframe(
                df_comp[["title", "guest", "published_at", "views", "likes", "comments", "duration_min", "like_rate"]]
                .sort_values("views", ascending=False)
                .rename(columns={
                    "title": "Título", "guest": "Invitado", "published_at": "Publicado",
                    "views": "Vistas", "likes": "Likes", "comments": "Comentarios",
                    "duration_min": "Duración (min)", "like_rate": "% Likes",
                }),
                use_container_width=True, hide_index=True,
            )

# ════════════════════════════════════════════════════════════════════════════
# TAB 5 — EVOLUCIÓN
# ════════════════════════════════════════════════════════════════════════════
with tab5:
    st.subheader("Evolución temporal del canal")

    if not df.empty:
        monthly_tipo = df.groupby(["month", "tipo"])["views"].sum().reset_index()
        monthly_total = df.groupby("month")["views"].sum().reset_index()
        monthly_total["tipo"] = "Total"
        monthly_all = pd.concat([monthly_tipo, monthly_total], ignore_index=True)
        fig_ev = px.line(
            monthly_all,
            x="month",
            y="views",
            color="tipo",
            markers=True,
            category_orders={"tipo": TIPO_ORDEN + ["Total"]},
            color_discrete_map=TIPO_COLORS,
            title="Vistas por mes — Shorts / Medianos / Completos / Total",
            labels={"month": "Mes", "views": "Vistas", "tipo": "Formato"},
        )
        st.plotly_chart(fig_ev, use_container_width=True)

        pub = df.groupby(["month", "tipo"]).size().reset_index(name="cantidad")
        fig_pub = px.bar(
            pub,
            x="month",
            y="cantidad",
            color="tipo",
            barmode="stack",
            category_orders={"tipo": TIPO_ORDEN},
            color_discrete_map=TIPO_COLORS,
            title="Videos publicados por mes",
            labels={"month": "Mes", "cantidad": "Cantidad", "tipo": "Formato"},
        )
        st.plotly_chart(fig_pub, use_container_width=True)

        st.markdown("### Consistencia vs. desempeño")
        st.caption("¿Publicar más seguido se relaciona con más vistas? Cada punto es un mes.")
        consist = df.groupby("month").agg(videos=("id","count"), vistas=("views","sum")).reset_index()
        if len(consist) >= 2:
            fig_cons = px.scatter(
                consist, x="videos", y="vistas", text="month",
                title="Videos publicados por mes vs. vistas totales de ese mes",
                labels={"videos": "Videos publicados", "vistas": "Vistas del mes"},
                trendline="ols",
            )
            fig_cons.update_traces(textposition="top center")
            st.plotly_chart(fig_cons, use_container_width=True)

    # Analytics diarias del canal
    st.subheader("Analytics diarias del canal")
    df_ch, err_ch = fetch_channel_analytics(analytics, start_date.isoformat(), end_date.isoformat())

    if err_ch:
        st.warning(f"Error al cargar Analytics: {err_ch}")
    elif df_ch.empty:
        st.info("No hay datos de Analytics para el período.")
    else:
        e1, e2 = st.columns(2)
        fig_dv = px.area(df_ch, x="day", y="views", title="Vistas diarias",
                         color_discrete_sequence=["#FF0000"])
        e1.plotly_chart(fig_dv, use_container_width=True)

        fig_wt = px.area(df_ch, x="day", y="estimatedMinutesWatched", title="Minutos vistos por día",
                         color_discrete_sequence=["#FF0050"])
        e2.plotly_chart(fig_wt, use_container_width=True)

        if "subscribersGained" in df_ch.columns:
            df_ch["net_subs"] = df_ch["subscribersGained"] - df_ch.get("subscribersLost", 0)
            fig_sub = px.bar(df_ch, x="day", y="net_subs", title="Suscriptores netos por día",
                             color_discrete_sequence=["#28a745"])
            st.plotly_chart(fig_sub, use_container_width=True)

# ════════════════════════════════════════════════════════════════════════════
# TAB 6 — RETENCIÓN
# ════════════════════════════════════════════════════════════════════════════
with tab6:
    st.subheader("🔁 Retención de audiencia")
    st.caption("Cuánto tiempo ven las personas cada video y dónde abandonan.")

    df_van_ret, err_ret = fetch_video_analytics(analytics, start_date.isoformat(), end_date.isoformat())

    if err_ret:
        st.warning(f"Error al cargar Analytics: {err_ret}")
    elif df_van_ret.empty:
        st.info("No hay datos de Analytics para el período seleccionado.")
    else:
        df_ret = df.merge(df_van_ret, on="id", how="inner", suffixes=("", "_analytics"))

        # ── Métricas resumen por formato ──────────────────────────────────
        st.markdown("### Promedios generales del canal")
        r1, r2, r3 = st.columns(3)
        for col, tipo in zip([r1, r2, r3], TIPO_ORDEN):
            sub = df_ret[df_ret["tipo"] == tipo]
            if not sub.empty and "averageViewDuration" in sub.columns:
                avg_dur = sub["averageViewDuration"].mean()
                avg_pct = sub["averageViewPercentage"].mean() if "averageViewPercentage" in sub.columns else 0
                if tipo == "Short":
                    dur_label = f"{avg_dur:.0f} seg"
                else:
                    dur_label = f"{avg_dur/60:.1f} min"
                col.metric(f"{TIPO_ICONS[tipo]} {tipo} — visto promedio", dur_label)
                col.metric(f"{TIPO_ICONS[tipo]} {tipo} — % retenido", f"{avg_pct:.1f}%")
            else:
                col.metric(f"{tipo}", "Sin datos")

        st.divider()

        # ── Gancho de los Shorts (primeros 3 segundos) ────────────────────
        st.markdown("### 🪝 El gancho de los Shorts (primeros 3 segundos)")
        st.caption("Si la gente no se queda en los primeros 3 segundos, el algoritmo deja de mostrarlo. Calculado sobre los Shorts más vistos del período.")

        df_ret_s = df_ret[df_ret["tipo"] == "Short"].copy()
        top_shorts_hook = df_ret_s.nlargest(8, "views")

        @st.cache_data(show_spinner="Calculando gancho de Shorts...", ttl=86400)
        def calcular_hooks(_analytics, video_ids, durations, end_iso):
            filas = []
            for vid, dur in zip(video_ids, durations):
                df_curve, err = fetch_retention_curve(_analytics, vid, "2020-01-01", end_iso)
                if err or df_curve.empty or dur <= 0:
                    continue
                ratio_3s = min(3 / dur, 1.0)
                df_curve = df_curve.copy()
                df_curve["dist"] = (df_curve["elapsedVideoTimeRatio"] - ratio_3s).abs()
                fila = df_curve.sort_values("dist").iloc[0]
                filas.append({"id": vid, "hook_pct": round(fila["audienceWatchRatio"] * 100, 1)})
            return pd.DataFrame(filas)

        if not top_shorts_hook.empty:
            hooks_df = calcular_hooks(
                analytics,
                tuple(top_shorts_hook["id"]),
                tuple(top_shorts_hook["duration_sec"]),
                end_date.isoformat(),
            )
            if not hooks_df.empty:
                top_shorts_hook = top_shorts_hook.merge(hooks_df, on="id", how="left")
                top_shorts_hook["estado_hook"] = top_shorts_hook["hook_pct"].apply(
                    lambda p: "🟢" if p >= 70 else ("🟡" if p >= 50 else "🔴")
                )
                st.dataframe(
                    top_shorts_hook[["thumbnail","title","guest","views","hook_pct","estado_hook"]]
                    .rename(columns={"thumbnail":"Miniatura","title":"Título","guest":"Invitado",
                                      "views":"Vistas","hook_pct":"% que sigue viendo a los 3s","estado_hook":"Estado"}),
                    column_config={"Miniatura": st.column_config.ImageColumn("Miniatura", width="small")},
                    use_container_width=True, hide_index=True,
                )
                st.caption("🟢 ≥70% sigue viendo a los 3s (gancho fuerte) · 🟡 50-70% · 🔴 <50% (el gancho falla, replantear los primeros segundos)")
            else:
                st.info("No se pudo calcular el gancho para estos Shorts.")
        else:
            st.info("No hay Shorts con datos de Analytics en el período.")

        st.divider()

        # ── Tabla de retención por video ─────────────────────────────────
        st.markdown("### Retención por video")
        tipo_ret = st.radio("Ver", ["Completos", "Medianos", "Shorts", "Todos"], horizontal=True, key="ret_tipo")
        if tipo_ret == "Todos":
            df_tabla = df_ret
        else:
            tipo_map = {"Completos": "Completo", "Medianos": "Mediano", "Shorts": "Short"}
            df_tabla = df_ret[df_ret["tipo"] == tipo_map[tipo_ret]]

        if df_tabla.empty:
            st.info("Sin datos para ese formato.")
        else:
            df_tabla = df_tabla.copy()
            df_tabla["min_vistos"] = (df_tabla["averageViewDuration"] / 60).round(1)
            df_tabla["seg_vistos"] = df_tabla["averageViewDuration"].round(0).astype(int)
            df_tabla["duracion_display"] = df_tabla.apply(
                lambda r: f"{r['seg_vistos']}s" if r["tipo"]=="Short" else f"{r['duration_min']:.0f} min", axis=1
            )
            df_tabla["visto_display"] = df_tabla.apply(
                lambda r: f"{r['seg_vistos']}s" if r["tipo"]=="Short" else f"{r['min_vistos']} min", axis=1
            )
            df_tabla["ret_pct"] = df_tabla["averageViewPercentage"].round(1)

            def color_ret(pct, tipo):
                if tipo == "Short":
                    return "🟢" if pct >= 60 else ("🟡" if pct >= 35 else "🔴")
                else:
                    return "🟢" if pct >= 40 else ("🟡" if pct >= 20 else "🔴")

            df_tabla["estado"] = df_tabla.apply(lambda r: color_ret(r["ret_pct"], r["tipo"]), axis=1)

            cols_show = ["thumbnail","title","guest","tipo","duracion_display","visto_display","ret_pct","estado","views"]
            cols_names = {
                "thumbnail":"Miniatura","title":"Título","guest":"Invitado","tipo":"Formato",
                "duracion_display":"Duración","visto_display":"Promedio visto",
                "ret_pct":"% Retención","estado":"Estado","views":"Vistas"
            }
            st.dataframe(
                df_tabla.sort_values("ret_pct", ascending=False)[cols_show].rename(columns=cols_names),
                column_config={"Miniatura": st.column_config.ImageColumn("Miniatura", width="small")},
                use_container_width=True,
                hide_index=True,
            )

        st.divider()

        # ── Análisis de últimos 10 minutos (solo Completos) ───────────────
        st.markdown("### ¿Cuánta gente llega a los últimos 10 minutos del capítulo?")
        st.caption("Solo aplica a los Capítulos Completos (+1 hora).")

        df_comp_ret = df_ret[df_ret["tipo"] == "Completo"].copy()
        if df_comp_ret.empty:
            st.info("No hay Capítulos Completos con datos de Analytics en el período.")
        else:
            df_comp_ret["umbral_ultimos10_pct"] = (
                (df_comp_ret["duration_sec"] - 600) / df_comp_ret["duration_sec"] * 100
            ).clip(0, 100)
            df_comp_ret["llega_ultimos10"] = (
                df_comp_ret["averageViewPercentage"] >= df_comp_ret["umbral_ultimos10_pct"]
            )
            df_comp_ret["min_vistos"] = (df_comp_ret["averageViewDuration"] / 60).round(1)

            llegan = df_comp_ret["llega_ultimos10"].sum()
            total  = len(df_comp_ret)
            st.markdown(f"""
**{llegan} de {total} capítulos** tienen retención promedio que llega a los últimos 10 minutos.

Esto significa que en esos {llegan} episodios el espectador típico se queda hasta casi el final.
En los restantes {total - llegan}, la gente se va antes de esa sección final.
""")
            fig_u10 = px.bar(
                df_comp_ret.sort_values("averageViewPercentage", ascending=False),
                x="averageViewPercentage",
                y="title",
                orientation="h",
                color="llega_ultimos10",
                color_discrete_map={True: "#28a745", False: "#dc3545"},
                title="% de retención promedio por capítulo (🟢 llega al final | 🔴 se va antes)",
                labels={"averageViewPercentage": "% Retención promedio", "title": "", "llega_ultimos10": "Llega al final"},
                text="min_vistos",
            )
            fig_u10.update_traces(texttemplate="%{text} min vistos", textposition="outside")
            fig_u10.update_layout(yaxis={"categoryorder": "total ascending"}, height=max(400, len(df_comp_ret)*35))
            st.plotly_chart(fig_u10, use_container_width=True)

        st.divider()

        # ── Curva de retención real por video, vs promedio del canal ──────
        st.markdown("### Curva de retención detallada por video")
        st.caption("Seleccioná un video para ver exactamente en qué segundo/minuto la gente abandona, comparado contra el promedio del canal para ese formato.")

        @st.cache_data(show_spinner="Calculando curva promedio del canal...", ttl=86400)
        def curva_promedio(_analytics, video_ids, end_iso):
            curvas = []
            for vid in video_ids:
                df_c, err = fetch_retention_curve(_analytics, vid, "2020-01-01", end_iso)
                if err or df_c.empty:
                    continue
                tmp = df_c[["elapsedVideoTimeRatio", "audienceWatchRatio"]].copy()
                tmp["bucket"] = (tmp["elapsedVideoTimeRatio"] * 20).round() / 20
                curvas.append(tmp)
            if not curvas:
                return pd.DataFrame()
            todas = pd.concat(curvas)
            avg = todas.groupby("bucket")["audienceWatchRatio"].mean().reset_index()
            avg["porcentaje_avg"] = (avg["audienceWatchRatio"] * 100).round(1)
            return avg

        if not df_ret.empty:
            video_opciones = {f"{r['title'][:70]} ({r['tipo']})": r["id"]
                              for _, r in df_ret.sort_values("views", ascending=False).iterrows()}
            vid_sel = st.selectbox("Elegí un video", ["— Seleccioná un video —"] + list(video_opciones.keys()))

            if vid_sel != "— Seleccioná un video —":
                vid_id  = video_opciones[vid_sel]
                vid_row = df_ret[df_ret["id"] == vid_id].iloc[0]
                dur_sec = vid_row["duration_sec"]
                dur_min = vid_row["duration_min"]
                tipo_vid = vid_row["tipo"]

                c_info1, c_info2, c_info3 = st.columns(3)
                c_info1.metric("Duración total", f"{dur_min:.0f} min" if tipo_vid != "Short" else f"{dur_sec:.0f} seg")
                c_info2.metric("Tiempo visto promedio", f"{vid_row['averageViewDuration']/60:.1f} min" if tipo_vid != "Short" else f"{vid_row['averageViewDuration']:.0f} seg")
                c_info3.metric("% Retención promedio", f"{vid_row['averageViewPercentage']:.1f}%")

                with st.spinner("Cargando curva de retención..."):
                    df_curve, err_curve = fetch_retention_curve(
                        analytics, vid_id, "2020-01-01", end_date.isoformat()
                    )

                if err_curve:
                    st.warning(f"No se pudo cargar la curva: {err_curve}")
                elif df_curve.empty:
                    st.info("No hay datos suficientes para este video.")
                else:
                    df_curve["porcentaje"] = (df_curve["audienceWatchRatio"] * 100).round(1)
                    df_curve["tiempo_seg"] = df_curve["elapsedVideoTimeRatio"] * dur_sec

                    fig_curve = go.Figure()
                    fig_curve.add_trace(go.Scatter(
                        x=df_curve["tiempo_seg"], y=df_curve["porcentaje"],
                        mode="lines", fill="tozeroy", name="Este video",
                        line=dict(color="#FF0000"),
                    ))

                    # Curva promedio del canal para ese formato (top 5 por vistas)
                    candidatos = df_ret[df_ret["tipo"] == tipo_vid].nlargest(5, "views")["id"].tolist()
                    avg_curve = curva_promedio(analytics, tuple(candidatos), end_date.isoformat())
                    if not avg_curve.empty:
                        fig_curve.add_trace(go.Scatter(
                            x=avg_curve["bucket"] * dur_sec, y=avg_curve["porcentaje_avg"],
                            mode="lines", name=f"Promedio canal ({tipo_vid})",
                            line=dict(color="gray", dash="dash"),
                        ))

                    if dur_sec > 600:
                        fig_curve.add_vline(
                            x=dur_sec - 600, line_dash="dash", line_color="orange",
                            annotation_text="Últimos 10 min", annotation_position="top right",
                        )
                    if dur_sec > 6:
                        fig_curve.add_vline(
                            x=3, line_dash="dot", line_color="purple",
                            annotation_text="3 seg (gancho)",
                        )
                    fig_curve.add_vline(
                        x=dur_sec * 0.5, line_dash="dot", line_color="lightgray",
                        annotation_text="Mitad del video",
                    )

                    fig_curve.update_layout(
                        title=f"Curva de retención — {vid_row['title'][:60]}",
                        xaxis_title="Tiempo (segundos)", yaxis_title="% espectadores que siguen viendo",
                        height=420, yaxis_range=[0, 110],
                    )
                    st.plotly_chart(fig_curve, use_container_width=True)

                    drop_30 = df_curve[df_curve["elapsedVideoTimeRatio"] <= 0.33]["porcentaje"].min() if not df_curve.empty else 100
                    drop_50 = df_curve[df_curve["elapsedVideoTimeRatio"] <= 0.50]["porcentaje"].min() if not df_curve.empty else 100
                    drop_80 = df_curve[df_curve["elapsedVideoTimeRatio"] <= 0.80]["porcentaje"].min() if not df_curve.empty else 100

                    st.markdown("**Interpretación automática:**")
                    st.markdown(f"""
| Punto del video | % espectadores que llegan |
|---|---|
| Primer tercio (~{dur_sec*0.33/60:.1f} min) | **{drop_30:.0f}%** |
| Mitad (~{dur_sec*0.5/60:.1f} min) | **{drop_50:.0f}%** |
| 80% del video (~{dur_sec*0.8/60:.1f} min) | **{drop_80:.0f}%** |
""")
                    if not avg_curve.empty:
                        avg_at_50 = avg_curve[avg_curve["bucket"] <= 0.5]["porcentaje_avg"].min()
                        if drop_50 > avg_at_50:
                            st.success(f"✅ Este video retiene mejor que el promedio del canal a la mitad ({drop_50:.0f}% vs {avg_at_50:.0f}%).")
                        else:
                            st.warning(f"⚠️ Este video retiene peor que el promedio del canal a la mitad ({drop_50:.0f}% vs {avg_at_50:.0f}%).")
                    if drop_30 < 60:
                        st.warning(f"⚠️ El primer tercio pierde mucha gente ({100-drop_30:.0f}% abandona antes de los {dur_sec*0.33/60:.1f} min). El inicio necesita más gancho.")
                    if drop_80 > 30:
                        st.success(f"✅ El {drop_80:.0f}% llega al 80% del video — el final engancha bien.")

# ════════════════════════════════════════════════════════════════════════════
# TAB 7 — SEMÁFORO
# ════════════════════════════════════════════════════════════════════════════
with tab7:
    st.subheader("🚦 Semáforo de desempeño")
    st.caption("Compara cada invitado contra el promedio del canal en cada formato. 🟢 por arriba del promedio · 🟡 cerca del promedio · 🔴 por debajo.")

    if df.empty:
        st.info("Sin datos para el período seleccionado.")
    else:
        # Promedios del canal por formato
        avg_canal = {}
        for tipo in TIPO_ORDEN:
            sub = df[df["tipo"] == tipo]
            avg_canal[tipo] = sub["views"].mean() if not sub.empty else 0
        avg_like_canal = df["like_rate"].mean()

        guest_df = build_guest_summary(df)
        filas = []
        for _, row in guest_df.iterrows():
            guest = row["Invitado"]
            gdf = df[df["guest"] == guest]
            fila = {"Invitado": guest, "Videos": int(row["Videos"])}
            for tipo in TIPO_ORDEN:
                n = int(row[f"Videos {tipo}"])
                if n > 0:
                    avg_views = row[f"Vistas {tipo}"] / n
                    fila[f"{TIPO_ICONS[tipo]} {tipo}"] = f"{semaforo(avg_views, avg_canal[tipo])} {avg_views:,.0f}"
                else:
                    fila[f"{TIPO_ICONS[tipo]} {tipo}"] = "—"
            avg_like_guest = gdf["like_rate"].mean()
            fila["❤️ % Likes"] = f"{semaforo(avg_like_guest, avg_like_canal)} {avg_like_guest:.1f}%"
            filas.append(fila)

        st.markdown("#### Vistas promedio por video, por formato")
        st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)
        st.caption(f"Promedio del canal — 🎬 Shorts: {avg_canal['Short']:,.0f} vistas · 🎯 Medianos: {avg_canal['Mediano']:,.0f} vistas · 📹 Completos: {avg_canal['Completo']:,.0f} vistas · ❤️ Likes: {avg_like_canal:.1f}%")

        st.divider()

        # ── Embudo Shorts -> Completo por invitado ────────────────────────
        st.markdown("#### 🔄 Embudo: Shorts → Capítulo Completo")
        st.caption("Por cada invitado, relación entre las vistas de sus Shorts y las vistas de su Capítulo Completo. Una proporción alta sugiere que los Shorts atraen tráfico hacia el episodio entero.")

        embudo = []
        for _, row in guest_df.iterrows():
            guest = row["Invitado"]
            if guest == "Solo (sin invitado)":
                continue
            v_short = row["Vistas Short"]
            v_comp  = row["Vistas Completo"]
            if v_comp > 0:
                ratio = v_short / v_comp
                embudo.append({
                    "Invitado": guest,
                    "Vistas Shorts": v_short,
                    "Vistas Completo": v_comp,
                    "Shorts por cada vista del Completo": round(ratio, 2),
                })
        if embudo:
            df_embudo = pd.DataFrame(embudo).sort_values("Shorts por cada vista del Completo", ascending=False)
            st.dataframe(
                df_embudo.style.format({
                    "Vistas Shorts": "{:,}", "Vistas Completo": "{:,}",
                    "Shorts por cada vista del Completo": "{:.2f}",
                }),
                use_container_width=True, hide_index=True,
            )
            st.caption("Un número alto = los Shorts de ese invitado generaron muchas vistas en relación al Completo. Si el Completo tiene pocas vistas pese a Shorts exitosos, el problema puede estar en el título/miniatura del capítulo o en la falta de un CTA claro en el Short hacia el video completo.")
        else:
            st.info("No hay invitados con Shorts y Capítulo Completo en el período para comparar.")

# ════════════════════════════════════════════════════════════════════════════
# TAB 8 — RECOMENDACIONES
# ════════════════════════════════════════════════════════════════════════════
with tab8:
    st.subheader("💡 Análisis y recomendaciones")

    if df.empty:
        st.info("Sin datos para el período seleccionado.")
    else:
        df_s    = df[df["tipo"] == "Short"]
        df_m    = df[df["tipo"] == "Mediano"]
        df_c    = df[df["tipo"] == "Completo"]
        df_van2, _ = fetch_video_analytics(analytics, start_date.isoformat(), end_date.isoformat())
        guest_sum  = build_guest_summary(df)
        solo_row   = guest_sum[guest_sum["Invitado"] == "Solo (sin invitado)"]
        inv_rows   = guest_sum[guest_sum["Invitado"] != "Solo (sin invitado)"]
        best_guest = inv_rows.iloc[0] if not inv_rows.empty else None
        top_comp   = df_c.nlargest(1, "views").iloc[0] if not df_c.empty else None
        top_med    = df_m.nlargest(1, "views").iloc[0] if not df_m.empty else None
        top_short  = df_s.nlargest(1, "views").iloc[0] if not df_s.empty else None

        # ════════════════════════════════════════
        st.markdown("## 📋 QUÉ HICIMOS")
        st.markdown(f"""
En el período seleccionado publicaste **{len(df)} piezas de contenido**:
- **{len(df_s)} Shorts**, **{len(df_m)} Medianos** y **{len(df_c)} Capítulos Completos**
- **{len(inv_rows)} invitados** distintos aparecieron en el canal
- El mes con más publicaciones fue **{df.groupby('month').size().idxmax() if not df.empty else '—'}**
- Total de vistas generadas: **{df['views'].sum():,}**
  — Shorts: **{df_s['views'].sum():,}** · Medianos: **{df_m['views'].sum():,}** · Completos: **{df_c['views'].sum():,}**
        """)

        # ════════════════════════════════════════
        st.markdown("## 🔍 QUÉ PASÓ")

        st.markdown("### Invitados")
        if best_guest is not None:
            avg_solo_vid = int(solo_row["Vistas totales"].sum() / max(solo_row["Videos"].sum(), 1)) if not solo_row.empty else 0
            avg_inv_vid  = int(inv_rows["Vistas totales"].sum() / max(inv_rows["Videos"].sum(), 1))
            st.markdown(f"""
<div class="rec-good">
🏆 <b>{best_guest['Invitado']}</b> fue el invitado con más impacto: <b>{int(best_guest['Vistas totales']):,} vistas</b> en {int(best_guest['Videos'])} videos
({int(best_guest['Vistas Short']):,} Shorts + {int(best_guest['Vistas Mediano']):,} Medianos + {int(best_guest['Vistas Completo']):,} Completos).<br><br>
Promedio por video <b>con invitado</b>: {avg_inv_vid:,} vistas.<br>
Promedio por video <b>sin invitado</b> (solo Tom y Thiago): {avg_solo_vid:,} vistas.
</div>""", unsafe_allow_html=True)

            if avg_inv_vid > avg_solo_vid:
                diff_pct = int((avg_inv_vid - avg_solo_vid) / max(avg_solo_vid, 1) * 100)
                st.markdown(f"""
<div class="rec-card">
📊 Los videos con invitado rinden <b>{diff_pct}% más</b> que los episodios solos en promedio.
Esto no significa que los solos sean malos — pueden ser más auténticos y fidelizadores —
pero el invitado claramente impulsa el alcance.
</div>""", unsafe_allow_html=True)
            else:
                diff_pct = int((avg_solo_vid - avg_inv_vid) / max(avg_inv_vid, 1) * 100)
                st.markdown(f"""
<div class="rec-good">
📊 Los episodios solo con Tom y Thiago rinden <b>{diff_pct}% más</b> que los de invitados en promedio.
Tu audiencia ya confía en ustedes y prefiere ese formato íntimo.
</div>""", unsafe_allow_html=True)

        st.markdown("### Shorts")
        if not df_s.empty:
            avg_s = int(df_s["views"].mean())
            st.markdown(f"""
<div class="rec-good">
🎬 Publicaste <b>{len(df_s)} Shorts</b> con un promedio de <b>{avg_s:,} vistas cada uno</b>.<br>
El Short más visto fue <b>"{top_short['title'][:65]}"</b> con <b>{int(top_short['views']):,} vistas</b>
(invitado: {top_short['guest']}).
</div>""", unsafe_allow_html=True)

            bottom_s = df_s[df_s["views"] < avg_s]
            if not bottom_s.empty:
                st.markdown(f"""
<div class="rec-card">
⚠️ <b>{len(bottom_s)} Shorts</b> están por debajo del promedio del canal ({avg_s:,} vistas).
Eso indica que el gancho (primeros 1-3 segundos) o el tema no enganchó lo suficiente
para que el algoritmo los distribuya. Revisá la pestaña Retención → "El gancho de los Shorts".
</div>""", unsafe_allow_html=True)
        else:
            st.info("No hay Shorts en el período seleccionado.")

        st.markdown("### Medianos")
        if not df_m.empty:
            avg_m = int(df_m["views"].mean())
            st.markdown(f"""
<div class="rec-good">
🎯 Publicaste <b>{len(df_m)} Medianos</b> con un promedio de <b>{avg_m:,} vistas cada uno</b>.<br>
El más visto fue <b>"{top_med['title'][:65]}"</b> con <b>{int(top_med['views']):,} vistas</b>
(invitado: {top_med['guest']}).
</div>""", unsafe_allow_html=True)
        else:
            st.info("No hay Medianos en el período seleccionado.")

        st.markdown("### Capítulos Completos")
        if not df_c.empty:
            avg_c = int(df_c["views"].mean())
            st.markdown(f"""
<div class="rec-good">
📹 Publicaste <b>{len(df_c)} Capítulos Completos</b> con un promedio de <b>{avg_c:,} vistas cada uno</b>.<br>
El más visto fue <b>"{top_comp['title'][:65]}"</b> con <b>{int(top_comp['views']):,} vistas</b>
(invitado: {top_comp['guest']}).
</div>""", unsafe_allow_html=True)

            if not df_van2.empty:
                df_mc = df_c.merge(df_van2, on="id", how="left", suffixes=("", "_analytics")).dropna(subset=["averageViewPercentage"])
                if not df_mc.empty:
                    avg_ret = df_mc["averageViewPercentage"].mean()
                    st.markdown(f"""
<div class="{'rec-good' if avg_ret >= 30 else 'rec-card'}">
⏱️ <b>Retención promedio: {avg_ret:.1f}%</b> de los Capítulos Completos.
{"Buen número — la gente termina de ver una parte importante del contenido." if avg_ret >= 30 else "Está por debajo del 30% recomendado. La gente abandona antes de la mitad."}
</div>""", unsafe_allow_html=True)
        else:
            st.info("No hay Capítulos Completos en el período seleccionado.")

        # ════════════════════════════════════════
        st.markdown("## 🚀 QUÉ HACER AHORA")

        acciones = []

        if best_guest is not None:
            acciones.append(f"""
**1. Traé de vuelta a {best_guest['Invitado']}**
Fue tu invitado más efectivo con {int(best_guest['Vistas totales']):,} vistas.
Repetir invitados exitosos es una estrategia probada — el público ya los conoce y confía.
Idealmente en un formato nuevo o con un ángulo de conversación diferente al anterior.""")

        if not df_s.empty and top_short is not None:
            acciones.append(f"""
**2. Replicá la fórmula de tu Short más viral**
"{top_short['title'][:60]}" funcionó con {int(top_short['views']):,} vistas.
Revisá: ¿qué dice en el primer segundo? ¿Es una pregunta, una afirmación fuerte, o algo inesperado?
Usá esa misma estructura de arranque en los próximos 3 Shorts.""")

        if not df_van2.empty and not df_c.empty:
            df_mc3 = df_c.merge(df_van2, on="id", how="left", suffixes=("", "_analytics")).dropna(subset=["averageViewPercentage"])
            if not df_mc3.empty:
                avg_ret2 = df_mc3["averageViewPercentage"].mean()
                if avg_ret2 < 35:
                    acciones.append(f"""
**3. Mejorá los primeros 2 minutos de los Capítulos Completos**
La retención promedio es {avg_ret2:.0f}% — la gente se va antes de la mitad.
La causa más común: intro demasiado larga o arranque lento.
Probá empezar directamente con la idea más fuerte del episodio, sin presentaciones.""")

        if not inv_rows.empty:
            menos_visto = inv_rows.iloc[-1]
            acciones.append(f"""
**4. Analizá por qué {menos_visto['Invitado']} tuvo menos tracción**
Solo generó {int(menos_visto['Vistas totales']):,} vistas en {int(menos_visto['Videos'])} videos.
Puede ser por el tema tratado, la hora de publicación, la miniatura, o simplemente que el público aún no lo conoce.
Antes de descartarlo, probá con un Short que tenga un gancho más fuerte sobre su historia.""")

        if not df_m.empty and not df_c.empty:
            avg_m_views = df_m["views"].mean()
            avg_c_views = df_c["views"].mean()
            if avg_m_views > avg_c_views * 1.3:
                acciones.append(f"""
**5. Los Medianos están superando a los Completos**
Los clips Medianos promedian {int(avg_m_views):,} vistas vs {int(avg_c_views):,} de los Completos.
Probá usar los Medianos como "tráiler" del capítulo: subilos primero, y en la descripción/comentario
fijado linkeá al Capítulo Completo correspondiente para canalizar ese interés.""")

        if acciones:
            for accion in acciones:
                st.markdown(accion)
                st.divider()
        else:
            st.info("Necesitás más datos en el período para generar recomendaciones.")

# ════════════════════════════════════════════════════════════════════════════
# TAB 9 — PLAN DE ACCIÓN
# ════════════════════════════════════════════════════════════════════════════
with tab9:
    st.subheader("✅ Plan de Acción")
    st.caption("Resumen ejecutivo: lo que el equipo debería revisar y decidir esta semana, en base a los datos del período seleccionado.")

    if df.empty:
        st.info("Sin datos para el período seleccionado.")
    else:
        df_s = df[df["tipo"] == "Short"]
        df_m = df[df["tipo"] == "Mediano"]
        df_c = df[df["tipo"] == "Completo"]
        guest_sum = build_guest_summary(df)
        inv_rows  = guest_sum[guest_sum["Invitado"] != "Solo (sin invitado)"]
        df_van3, _ = fetch_video_analytics(analytics, start_date.isoformat(), end_date.isoformat())

        items = []

        # 1. Invitado a repetir
        if not inv_rows.empty:
            best = inv_rows.iloc[0]
            items.append(("Contenido", f"Re-contactar a **{best['Invitado']}** para grabar de nuevo (su contenido generó {int(best['Vistas totales']):,} vistas)."))

        # 2. Shorts bajo promedio
        if not df_s.empty:
            avg_s = df_s["views"].mean()
            bajos = df_s[df_s["views"] < avg_s * 0.6]
            if not bajos.empty:
                items.append(("Shorts", f"Revisar el gancho (primeros 3s) de los **{len(bajos)} Shorts** con menos del 60% del promedio del canal. Ver pestaña Retención."))

        # 3. Retención de completos
        if not df_van3.empty and not df_c.empty:
            df_mc = df_c.merge(df_van3, on="id", how="left", suffixes=("", "_analytics")).dropna(subset=["averageViewPercentage"])
            if not df_mc.empty:
                avg_ret = df_mc["averageViewPercentage"].mean()
                if avg_ret < 35:
                    peor = df_mc.nsmallest(1, "averageViewPercentage").iloc[0]
                    items.append(("Completos", f"La retención promedio de Completos es {avg_ret:.0f}% (objetivo: 35%+). Empezar por **\"{peor['title'][:50]}...\"** ({peor['averageViewPercentage']:.0f}% retención) — analizar si la intro es muy larga."))
                else:
                    items.append(("Completos", f"La retención promedio de Completos está bien ({avg_ret:.0f}%). Mantener el formato de apertura actual."))

        # 4. Embudo Shorts -> Completo
        embudo_bajo = []
        for _, row in guest_sum.iterrows():
            if row["Invitado"] == "Solo (sin invitado)":
                continue
            if row["Vistas Short"] > 0 and row["Vistas Completo"] == 0:
                embudo_bajo.append(row["Invitado"])
        if embudo_bajo:
            items.append(("Embudo", f"Invitados con Shorts publicados pero sin Capítulo Completo en el período: **{', '.join(embudo_bajo[:5])}**. Si ya grabaron el capítulo entero, programar su publicación."))

        # 5. Consistencia
        if not df.empty:
            meses = df.groupby("month").size()
            if len(meses) >= 2 and meses.std() / meses.mean() > 0.4:
                items.append(("Consistencia", f"La cantidad de publicaciones varía mucho mes a mes (entre {int(meses.min())} y {int(meses.max())}). Definir un calendario fijo de publicación reduce la variabilidad de vistas."))

        # 6. Invitado con menor tracción
        if not inv_rows.empty and len(inv_rows) > 1:
            peor_inv = inv_rows.iloc[-1]
            items.append(("Invitados", f"**{peor_inv['Invitado']}** tuvo la menor tracción ({int(peor_inv['Vistas totales']):,} vistas). Decidir: ¿probar un nuevo ángulo de Short sobre su contenido, o no volver a invitarlo?"))

        if not items:
            st.info("No hay suficientes datos en el período para generar un plan de acción.")
        else:
            for area, texto in items:
                st.markdown(f"""
<div class="accion-card">
<b>[{area}]</b><br>{texto}
</div>""", unsafe_allow_html=True)
                st.checkbox("Revisado / decidido", key=f"plan_{area}_{texto[:30]}")

# ════════════════════════════════════════════════════════════════════════════
# TAB 10 — DIAGNÓSTICO
# ════════════════════════════════════════════════════════════════════════════
with tab10:
    st.subheader("🔧 Diagnóstico — Clasificación de todos los videos")
    st.caption("Usá esta tabla para verificar que cada video esté bien clasificado (Short / Mediano / Completo) y que el invitado detectado sea correcto.")

    if df_all.empty:
        st.info("Sin datos.")
    else:
        counts = df_all["tipo"].value_counts()
        st.markdown(
            f"**Total de videos cargados:** {len(df_all)}  |  "
            + "  |  ".join(f"**{TIPO_ICONS[t]} {t}:** {counts.get(t, 0)}" for t in TIPO_ORDEN)
        )

        import re as _re
        def _limpiar(texto):
            if not isinstance(texto, str):
                return texto
            return _re.sub(r'[^\x00-\x7FáéíóúÁÉÍÓÚñÑüÜ¿¡@._\-\(\)\[\]#:,/ ]', '', texto).strip()

        csv_diag = df_all[["title","tipo","guest","duration_min","views","published_at"]].copy()
        csv_diag["title"] = csv_diag["title"].apply(_limpiar)
        csv_diag["guest"] = csv_diag["guest"].apply(_limpiar)
        csv_diag["published_at"] = csv_diag["published_at"].dt.strftime("%Y-%m-%d")
        csv_diag.columns = ["Titulo","Formato","Invitado detectado","Duracion (min)","Vistas","Publicado"]
        st.download_button(
            label="Descargar lista completa (abrir con Excel)",
            data=csv_diag.to_csv(index=False, encoding="utf-8-sig", sep=";"),
            file_name="videos_clasificados.csv",
            mime="text/csv",
        )

        busq = st.text_input("Filtrar por título o invitado", key="diag_busq")
        df_diag = df_all.copy()
        if busq:
            df_diag = df_diag[
                df_diag["title"].str.lower().str.contains(busq.lower(), na=False) |
                df_diag["guest"].str.lower().str.contains(busq.lower(), na=False)
            ]

        st.dataframe(
            df_diag[["thumbnail","title","tipo","guest","duration_min","views","published_at"]]
            .sort_values("published_at", ascending=False)
            .rename(columns={
                "thumbnail":"Miniatura","title":"Título","tipo":"Formato",
                "guest":"Invitado detectado","duration_min":"Duración (min)",
                "views":"Vistas","published_at":"Publicado",
            }),
            column_config={"Miniatura": st.column_config.ImageColumn("Miniatura", width="small")},
            use_container_width=True,
            hide_index=True,
        )

        st.divider()
        st.markdown("### Resumen de clasificación")
        col_a, col_b = st.columns(2)

        resumen_tipo = df_all.groupby("tipo").agg(
            Videos=("id","count"), Vistas=("views","sum")
        ).reset_index()
        col_a.dataframe(resumen_tipo, use_container_width=True, hide_index=True)

        resumen_guest = df_all.groupby("guest").agg(
            Videos=("id","count"),
            Shorts=("tipo", lambda x: (x=="Short").sum()),
            Medianos=("tipo", lambda x: (x=="Mediano").sum()),
            Completos=("tipo", lambda x: (x=="Completo").sum()),
            Vistas=("views","sum"),
        ).reset_index().sort_values("Videos", ascending=False)
        col_b.dataframe(resumen_guest, use_container_width=True, hide_index=True)
