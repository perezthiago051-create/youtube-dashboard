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
)

st.set_page_config(page_title="Crudo y Queso — Dashboard", layout="wide", page_icon="▶️")

st.markdown("""
<style>
    .metric-card {background:#f8f9fa;border-radius:12px;padding:16px;text-align:center;}
    .rec-card {background:#fff3cd;border-left:4px solid #ffc107;padding:12px;border-radius:4px;margin:8px 0;}
    .rec-good {background:#d4edda;border-left:4px solid #28a745;padding:12px;border-radius:4px;margin:8px 0;}
    .vid-card {border:1px solid #e0e0e0;border-radius:10px;padding:10px;text-align:center;background:#fff;}
    .vid-title {font-size:0.8rem;font-weight:600;margin-top:6px;line-height:1.3;}
    .vid-stat {font-size:0.75rem;color:#666;margin:2px 0;}
</style>
""", unsafe_allow_html=True)


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
                short_label = "🎬 Short" if v.get("is_short") else "📹 Largo"
                st.markdown(f"""
<div class="vid-title">{title[:55]}{'...' if len(title)>55 else ''}</div>
<div class="vid-stat">👤 {guest}</div>
<div class="vid-stat">👁️ {int(views):,} vistas &nbsp; ❤️ {int(likes):,}</div>
<div class="vid-stat">{short_label}</div>
""", unsafe_allow_html=True)

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

video_type = st.sidebar.radio("Tipo de video", ["Todos", "Solo Shorts", "Solo largos"])

st.sidebar.divider()
if st.sidebar.button("🔄 Recargar datos del canal"):
    st.cache_data.clear()
    st.rerun()

# ── Filtrar ───────────────────────────────────────────────────────────────────
df = df_all.copy()
if not df.empty:
    df = df[(df["published_at"].dt.date >= start_date) & (df["published_at"].dt.date <= end_date)]
    if video_type == "Solo Shorts":
        df = df[df["is_short"]]
    elif video_type == "Solo largos":
        df = df[~df["is_short"]]

# ── Header ────────────────────────────────────────────────────────────────────
st.title(f"▶️  {ch_name} — Dashboard")

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Suscriptores", f"{int(ch_st.get('subscriberCount', 0)):,}")
c2.metric("Videos totales", f"{int(ch_st.get('videoCount', 0)):,}")
c3.metric("Vistas totales", f"{int(ch_st.get('viewCount', 0)):,}")
shorts_count = df_all["is_short"].sum() if not df_all.empty else 0
largos_count = (~df_all["is_short"]).sum() if not df_all.empty else 0
c4.metric("Shorts", f"{shorts_count:,}")
c5.metric("Videos largos", f"{largos_count:,}")

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "🏆 Invitados",
    "🎬 Shorts",
    "📹 Videos Largos",
    "📈 Evolución",
    "🔁 Retención",
    "💡 Recomendaciones",
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
            title="Vistas totales por invitado (Shorts + Largos)",
        )
        fig_g.update_layout(yaxis={"categoryorder": "total ascending"}, height=500, coloraxis_showscale=False)
        st.plotly_chart(fig_g, use_container_width=True)

        # Comparación Shorts vs Largos por invitado
        top_guests = guest_df.head(10)["Invitado"].tolist()
        df_top = df[df["guest"].isin(top_guests)]
        comp = df_top.groupby(["guest", "is_short"])["views"].sum().reset_index()
        comp["tipo"] = comp["is_short"].map({True: "Shorts", False: "Largos"})

        fig_comp = px.bar(
            comp,
            x="guest",
            y="views",
            color="tipo",
            barmode="group",
            color_discrete_map={"Shorts": "#FF0050", "Largos": "#FF0000"},
            labels={"guest": "Invitado", "views": "Vistas", "tipo": "Tipo"},
            title="Top 10 invitados — Shorts vs Largos",
        )
        fig_comp.update_layout(xaxis_tickangle=-30)
        st.plotly_chart(fig_comp, use_container_width=True)

        # Tabla completa
        st.subheader("Tabla detallada por invitado")
        st.dataframe(
            guest_df.style.format({
                "Vistas totales": "{:,}",
                "Vistas Shorts": "{:,}",
                "Vistas Largos": "{:,}",
                "Likes totales": "{:,}",
                "Comentarios": "{:,}",
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
            df_inv_s = df_inv[df_inv["is_short"]]
            df_inv_l = df_inv[~df_inv["is_short"]]
            ia, ib, ic, id_ = st.columns(4)
            ia.metric("Videos totales", len(df_inv))
            ib.metric("Vistas totales", f"{df_inv['views'].sum():,}")
            ic.metric("Vistas Shorts", f"{df_inv_s['views'].sum():,}")
            id_.metric("Vistas Largos", f"{df_inv_l['views'].sum():,}")
            video_cards(df_inv, n_cols=4, max_videos=16)
            with st.expander("Ver tabla completa"):
                st.dataframe(
                    df_inv[["thumbnail","title","tipo","published_at","views","likes","comments","like_rate"]]
                    .rename(columns={"thumbnail":"Miniatura","title":"Título","tipo":"Tipo",
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
                    df_search[["thumbnail", "title", "guest", "published_at", "views", "likes", "comments", "is_short"]]
                    .rename(columns={
                        "thumbnail": "Miniatura", "title": "Título", "guest": "Invitado",
                        "published_at": "Publicado", "views": "Vistas", "likes": "Likes",
                        "comments": "Comentarios", "is_short": "Short",
                    }),
                    column_config={"Miniatura": st.column_config.ImageColumn("Miniatura", width="small")},
                    use_container_width=True, hide_index=True,
                )

# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — SHORTS
# ════════════════════════════════════════════════════════════════════════════
with tab2:
    df_shorts = df[df["is_short"]] if not df.empty else pd.DataFrame()
    st.subheader(f"Análisis de Shorts ({len(df_shorts)} en el período)")

    if df_shorts.empty:
        st.info("Sin Shorts en el período seleccionado.")
    else:
        s1, s2, s3 = st.columns(3)
        s1.metric("Vistas totales Shorts", f"{df_shorts['views'].sum():,}")
        s2.metric("Promedio de vistas", f"{int(df_shorts['views'].mean()):,}")
        s3.metric("Mejor Short", f"{df_shorts['views'].max():,} vistas")

        # Top Shorts con miniaturas
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

        # Shorts por invitado
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

        # Likes rate de Shorts
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

        # Tabla
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
# TAB 3 — VIDEOS LARGOS
# ════════════════════════════════════════════════════════════════════════════
with tab3:
    df_largos = df[~df["is_short"]] if not df.empty else pd.DataFrame()
    st.subheader(f"Análisis de Videos Largos ({len(df_largos)} en el período)")

    if df_largos.empty:
        st.info("Sin videos largos en el período seleccionado.")
    else:
        l1, l2, l3 = st.columns(3)
        l1.metric("Vistas totales", f"{df_largos['views'].sum():,}")
        l2.metric("Promedio de vistas", f"{int(df_largos['views'].mean()):,}")
        l3.metric("Duración promedio", f"{df_largos['duration_min'].mean():.0f} min")

        # Top largos con miniaturas
        st.markdown("#### Top Videos Largos")
        video_cards(df_largos.sort_values("views", ascending=False), n_cols=4, max_videos=8)
        st.divider()

        top_largos = df_largos.nlargest(20, "views")
        fig_l = px.bar(
            top_largos,
            x="views",
            y="title",
            orientation="h",
            color="views",
            color_continuous_scale="Reds",
            title="Top 20 Videos Largos por vistas",
            labels={"views": "Vistas", "title": ""},
        )
        fig_l.update_layout(yaxis={"categoryorder": "total ascending"}, height=550, coloraxis_showscale=False)
        st.plotly_chart(fig_l, use_container_width=True)

        # Analytics por video (CTR y retención)
        st.subheader("CTR y Retención por video (requiere Analytics API)")
        df_van, err = fetch_video_analytics(analytics, start_date.isoformat(), end_date.isoformat())

        if err:
            st.warning(f"Analytics API: {err}")
        elif df_van.empty:
            st.info("No hay datos de Analytics para el período.")
        else:
            # Merge con datos básicos
            df_merged = df_largos.merge(df_van, on="id", how="left", suffixes=("", "_analytics"))
            df_merged = df_merged.dropna(subset=["averageViewPercentage"])

            if not df_merged.empty:
                va1, va2 = st.columns(2)

                # Retención promedio
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

                # Duración del video vs retención
                df_scatter = df_merged.dropna(subset=["averageViewPercentage", "duration_min"]).copy()
                size_col = "views_x" if "views_x" in df_scatter.columns else "views"
                fig_scatter = px.scatter(
                    df_scatter,
                    x="duration_min",
                    y="averageViewPercentage",
                    size=size_col,
                    color="guest",
                    hover_name="title",
                    title="Duración del video vs % de retención (burbuja = vistas)",
                    labels={"duration_min": "Duración (min)", "averageViewPercentage": "Retención %", "guest": "Invitado"},
                )
                st.plotly_chart(fig_scatter, use_container_width=True)

        # Largos por invitado
        lg = df_largos.groupby("guest").agg(
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
            title="Vistas de Videos Largos por invitado",
            labels={"guest": "Invitado", "vistas": "Vistas"},
        )
        fig_lg.update_layout(xaxis_tickangle=-30, coloraxis_showscale=False)
        st.plotly_chart(fig_lg, use_container_width=True)

        with st.expander("Ver todos los Videos Largos"):
            st.dataframe(
                df_largos[["title", "guest", "published_at", "views", "likes", "comments", "duration_min", "like_rate"]]
                .sort_values("views", ascending=False)
                .rename(columns={
                    "title": "Título", "guest": "Invitado", "published_at": "Publicado",
                    "views": "Vistas", "likes": "Likes", "comments": "Comentarios",
                    "duration_min": "Duración (min)", "like_rate": "% Likes",
                }),
                use_container_width=True, hide_index=True,
            )

# ════════════════════════════════════════════════════════════════════════════
# TAB 4 — EVOLUCIÓN
# ════════════════════════════════════════════════════════════════════════════
with tab4:
    st.subheader("Evolución temporal del canal")

    if not df.empty:
        monthly_st = df.groupby(["month", "is_short"])["views"].sum().reset_index()
        monthly_st["tipo"] = monthly_st["is_short"].map({True: "Shorts", False: "Largos"})
        monthly_total = df.groupby("month")["views"].sum().reset_index()
        monthly_total["tipo"] = "Total"
        monthly_total["is_short"] = None
        monthly_all = pd.concat([monthly_st[["month","views","tipo"]], monthly_total[["month","views","tipo"]]], ignore_index=True)
        fig_ev = px.line(
            monthly_all,
            x="month",
            y="views",
            color="tipo",
            markers=True,
            color_discrete_map={"Shorts": "#FF0050", "Largos": "#CC0000", "Total": "#333333"},
            title="Vistas por mes — Shorts / Largos / Total",
            labels={"month": "Mes", "views": "Vistas", "tipo": "Tipo"},
        )
        st.plotly_chart(fig_ev, use_container_width=True)

        # Videos publicados por mes
        pub = df.groupby(["month", "is_short"]).size().reset_index(name="cantidad")
        pub["tipo"] = pub["is_short"].map({True: "Shorts", False: "Largos"})
        fig_pub = px.bar(
            pub,
            x="month",
            y="cantidad",
            color="tipo",
            barmode="stack",
            color_discrete_map={"Shorts": "#FF0050", "Largos": "#FF0000"},
            title="Videos publicados por mes",
            labels={"month": "Mes", "cantidad": "Cantidad", "tipo": "Tipo"},
        )
        st.plotly_chart(fig_pub, use_container_width=True)

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

        if "impressionClickThroughRate" in df_ch.columns:
            e3, e4 = st.columns(2)
            fig_ctr2 = px.line(df_ch, x="day", y="impressionClickThroughRate",
                               title="CTR diario (%)", color_discrete_sequence=["#0066CC"])
            e3.plotly_chart(fig_ctr2, use_container_width=True)

            if "subscribersGained" in df_ch.columns:
                df_ch["net_subs"] = df_ch["subscribersGained"] - df_ch.get("subscribersLost", 0)
                fig_sub = px.bar(df_ch, x="day", y="net_subs", title="Suscriptores netos por día",
                                 color_discrete_sequence=["#28a745"])
                e4.plotly_chart(fig_sub, use_container_width=True)

# ════════════════════════════════════════════════════════════════════════════
# TAB 5 — RETENCIÓN
# ════════════════════════════════════════════════════════════════════════════
with tab5:
    st.subheader("🔁 Retención de audiencia")
    st.caption("Cuánto tiempo ven las personas cada video y dónde abandonan.")

    df_van_ret, err_ret = fetch_video_analytics(analytics, start_date.isoformat(), end_date.isoformat())

    if err_ret:
        st.warning(f"Error al cargar Analytics: {err_ret}")
    elif df_van_ret.empty:
        st.info("No hay datos de Analytics para el período seleccionado.")
    else:
        df_ret = df.merge(df_van_ret, on="id", how="inner", suffixes=("", "_analytics"))
        df_ret_s = df_ret[df_ret["is_short"]]
        df_ret_l = df_ret[~df_ret["is_short"]]

        # ── Métricas resumen ─────────────────────────────────────────────
        st.markdown("### Promedios generales del canal")
        r1, r2, r3, r4 = st.columns(4)

        if not df_ret_s.empty and "averageViewDuration" in df_ret_s.columns:
            avg_dur_s = df_ret_s["averageViewDuration"].mean()
            avg_pct_s = df_ret_s["averageViewPercentage"].mean() if "averageViewPercentage" in df_ret_s.columns else 0
            r1.metric("⏱️ Shorts — seg vistos promedio", f"{avg_dur_s:.0f} seg")
            r2.metric("📊 Shorts — % retenido promedio", f"{avg_pct_s:.1f}%")
        else:
            r1.metric("Shorts", "Sin datos")

        if not df_ret_l.empty and "averageViewDuration" in df_ret_l.columns:
            avg_dur_l = df_ret_l["averageViewDuration"].mean()
            avg_pct_l = df_ret_l["averageViewPercentage"].mean() if "averageViewPercentage" in df_ret_l.columns else 0
            avg_min_l = avg_dur_l / 60
            r3.metric("⏱️ Largos — min vistos promedio", f"{avg_min_l:.1f} min")
            r4.metric("📊 Largos — % retenido promedio", f"{avg_pct_l:.1f}%")
        else:
            r3.metric("Largos", "Sin datos")

        st.divider()

        # ── Tabla de retención por video ─────────────────────────────────
        st.markdown("### Retención por video")
        tipo_ret = st.radio("Ver", ["Largos", "Shorts", "Ambos"], horizontal=True, key="ret_tipo")
        df_tabla = {"Largos": df_ret_l, "Shorts": df_ret_s, "Ambos": df_ret}[tipo_ret]

        if df_tabla.empty:
            st.info("Sin datos para ese tipo.")
        else:
            df_tabla = df_tabla.copy()
            df_tabla["min_vistos"] = (df_tabla["averageViewDuration"] / 60).round(1)
            df_tabla["seg_vistos"] = df_tabla["averageViewDuration"].round(0).astype(int)
            df_tabla["duracion_display"] = df_tabla.apply(
                lambda r: f"{r['seg_vistos']}s" if r["is_short"] else f"{r['duration_min']:.0f} min", axis=1
            )
            df_tabla["visto_display"] = df_tabla.apply(
                lambda r: f"{r['seg_vistos']}s" if r["is_short"] else f"{r['min_vistos']} min", axis=1
            )
            df_tabla["ret_pct"] = df_tabla["averageViewPercentage"].round(1)

            # Color semáforo por retención
            def color_ret(pct, is_short):
                if is_short:
                    return "🟢" if pct >= 60 else ("🟡" if pct >= 35 else "🔴")
                else:
                    return "🟢" if pct >= 40 else ("🟡" if pct >= 20 else "🔴")

            df_tabla["estado"] = df_tabla.apply(
                lambda r: color_ret(r["ret_pct"], r["is_short"]), axis=1
            )

            cols_show = ["thumbnail","title","guest","tipo","duracion_display","visto_display","ret_pct","estado","views"]
            cols_names = {
                "thumbnail":"Miniatura","title":"Título","guest":"Invitado","tipo":"Tipo",
                "duracion_display":"Duración","visto_display":"Promedio visto",
                "ret_pct":"% Retención","estado":"Estado","views":"Vistas"
            }
            st.dataframe(
                df_tabla.sort_values("ret_pct", ascending=False)[cols_show]
                .rename(columns=cols_names),
                column_config={"Miniatura": st.column_config.ImageColumn("Miniatura", width="small")},
                use_container_width=True,
                hide_index=True,
            )

        st.divider()

        # ── Análisis de últimos 10 minutos ───────────────────────────────
        st.markdown("### ¿Cuánta gente llega a los últimos 10 minutos?")
        st.caption("Solo aplica a videos largos de más de 20 minutos.")

        df_largos_ret = df_ret_l[df_ret_l["duration_min"] >= 20].copy()
        if df_largos_ret.empty:
            st.info("No hay videos largos de más de 20 minutos con datos de Analytics.")
        else:
            df_largos_ret["umbral_ultimos10_pct"] = (
                (df_largos_ret["duration_sec"] - 600) / df_largos_ret["duration_sec"] * 100
            ).clip(0, 100)
            df_largos_ret["llega_ultimos10"] = (
                df_largos_ret["averageViewPercentage"] >= df_largos_ret["umbral_ultimos10_pct"]
            )
            df_largos_ret["min_vistos"] = (df_largos_ret["averageViewDuration"] / 60).round(1)

            llegan = df_largos_ret["llega_ultimos10"].sum()
            total  = len(df_largos_ret)
            st.markdown(f"""
**{llegan} de {total} videos** tienen retención promedio que llega a los últimos 10 minutos.

Esto significa que en esos {llegan} videos el espectador típico se queda hasta casi el final.
En los restantes {total - llegan}, la gente se va antes de esa sección final.
""")
            fig_u10 = px.bar(
                df_largos_ret.sort_values("averageViewPercentage", ascending=False),
                x="averageViewPercentage",
                y="title",
                orientation="h",
                color="llega_ultimos10",
                color_discrete_map={True: "#28a745", False: "#dc3545"},
                title="% de retención promedio por video largo (🟢 llega al final | 🔴 se va antes)",
                labels={"averageViewPercentage": "% Retención promedio", "title": "", "llega_ultimos10": "Llega al final"},
                text="min_vistos",
            )
            fig_u10.update_traces(texttemplate="%{text} min vistos", textposition="outside")
            fig_u10.update_layout(yaxis={"categoryorder": "total ascending"}, height=max(400, len(df_largos_ret)*35))
            st.plotly_chart(fig_u10, use_container_width=True)

        st.divider()

        # ── Curva de retención real por video ────────────────────────────
        st.markdown("### Curva de retención detallada por video")
        st.caption("Seleccioná un video para ver exactamente en qué segundo/minuto la gente abandona.")

        if not df_ret.empty:
            video_opciones = {f"{r['title'][:70]} ({r['tipo']})": r["id"]
                              for _, r in df_ret.sort_values("views", ascending=False).iterrows()}
            vid_sel = st.selectbox("Elegí un video", ["— Seleccioná un video —"] + list(video_opciones.keys()))

            if vid_sel != "— Seleccioná un video —":
                vid_id  = video_opciones[vid_sel]
                vid_row = df_ret[df_ret["id"] == vid_id].iloc[0]
                dur_sec = vid_row["duration_sec"]
                dur_min = vid_row["duration_min"]

                c_info1, c_info2, c_info3 = st.columns(3)
                c_info1.metric("Duración total", f"{dur_min:.0f} min" if not vid_row["is_short"] else f"{dur_sec:.0f} seg")
                c_info2.metric("Tiempo visto promedio", f"{vid_row['averageViewDuration']/60:.1f} min" if not vid_row["is_short"] else f"{vid_row['averageViewDuration']:.0f} seg")
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
                    df_curve["tiempo_display"] = df_curve["elapsedVideoTimeRatio"].apply(
                        lambda r: f"{r * dur_sec / 60:.1f} min" if dur_sec > 120 else f"{r * dur_sec:.0f} seg"
                    )
                    df_curve["porcentaje"] = (df_curve["audienceWatchRatio"] * 100).round(1)
                    df_curve["tiempo_seg"] = df_curve["elapsedVideoTimeRatio"] * dur_sec

                    fig_curve = px.area(
                        df_curve,
                        x="tiempo_seg",
                        y="porcentaje",
                        title=f"Curva de retención — {vid_row['title'][:60]}",
                        labels={"tiempo_seg": "Tiempo (segundos)", "porcentaje": "% espectadores que siguen viendo"},
                        color_discrete_sequence=["#FF0000"],
                    )

                    # Línea de los últimos 10 min
                    if dur_sec > 600:
                        fig_curve.add_vline(
                            x=dur_sec - 600,
                            line_dash="dash",
                            line_color="orange",
                            annotation_text="Últimos 10 min",
                            annotation_position="top right",
                        )

                    # Línea de 50% del video
                    fig_curve.add_vline(
                        x=dur_sec * 0.5,
                        line_dash="dot",
                        line_color="gray",
                        annotation_text="Mitad del video",
                    )

                    fig_curve.update_layout(height=420, yaxis_range=[0, 110])
                    st.plotly_chart(fig_curve, use_container_width=True)

                    # Interpretación automática
                    drop_30 = df_curve[df_curve["elapsedVideoTimeRatio"] <= 0.33]["porcentaje"].min() if not df_curve.empty else 100
                    drop_50 = df_curve[df_curve["elapsedVideoTimeRatio"] <= 0.50]["porcentaje"].min() if not df_curve.empty else 100
                    drop_80 = df_curve[df_curve["elapsedVideoTimeRatio"] <= 0.80]["porcentaje"].min() if not df_curve.empty else 100

                    st.markdown("**Interpretación automática:**")
                    st.markdown(f"""
| Punto del video | % espectadores que llegan |
|---|---|
| Primer tercio (~{dur_sec*0.33/60:.0f} min) | **{drop_30:.0f}%** |
| Mitad (~{dur_sec*0.5/60:.0f} min) | **{drop_50:.0f}%** |
| 80% del video (~{dur_sec*0.8/60:.0f} min) | **{drop_80:.0f}%** |
| Últimos 10 min | **solo calculable con curva completa** |
""")
                    if drop_30 < 60:
                        st.warning(f"⚠️ El primer tercio pierde mucha gente ({100-drop_30:.0f}% abandona antes de los {dur_sec*0.33/60:.0f} min). El inicio necesita más gancho.")
                    if drop_50 < 40:
                        st.warning(f"⚠️ La mitad del video ya perdió el {100-drop_50:.0f}% del público. El contenido del medio puede estar flojo o muy extenso.")
                    if drop_80 > 30:
                        st.success(f"✅ El {drop_80:.0f}% llega al 80% del video — el final engancha bien.")


# ════════════════════════════════════════════════════════════════════════════
# TAB 6 — RECOMENDACIONES
# ════════════════════════════════════════════════════════════════════════════
with tab6:
    st.subheader("💡 Análisis y recomendaciones")

    if df.empty:
        st.info("Sin datos para el período seleccionado.")
    else:
        df_s   = df[df["is_short"]]
        df_l   = df[~df["is_short"]]
        df_van2, _ = fetch_video_analytics(analytics, start_date.isoformat(), end_date.isoformat())
        guest_sum  = build_guest_summary(df)
        solo_row   = guest_sum[guest_sum["Invitado"] == "Solo (sin invitado)"]
        inv_rows   = guest_sum[guest_sum["Invitado"] != "Solo (sin invitado)"]
        best_guest = inv_rows.iloc[0] if not inv_rows.empty else None
        top_largo  = df_l.nlargest(1, "views").iloc[0] if not df_l.empty else None
        top_short  = df_s.nlargest(1, "views").iloc[0] if not df_s.empty else None

        # ════════════════════════════════════════
        st.markdown("## 📋 QUÉ HICIMOS")
        st.markdown(f"""
En el período seleccionado publicaste **{len(df)} piezas de contenido**:
- **{len(df_s)} Shorts** y **{len(df_l)} Videos Largos**
- **{len(inv_rows)} invitados** distintos aparecieron en el canal
- El mes con más publicaciones fue **{df.groupby('month').size().idxmax() if not df.empty else '—'}**
- Total de vistas generadas: **{df['views'].sum():,}**
  — Shorts: **{df_s['views'].sum():,}** vistas
  — Largos: **{df_l['views'].sum():,}** vistas
        """)

        # ════════════════════════════════════════
        st.markdown("## 🔍 QUÉ PASÓ")

        st.markdown("### Invitados")
        if best_guest is not None:
            avg_inv  = int(inv_rows["Vistas totales"].mean())
            avg_solo = int(solo_row["Vistas totales"].mean()) if not solo_row.empty else 0
            avg_solo_vid = int(solo_row["Vistas totales"].sum() / max(solo_row["Videos"].sum(), 1)) if not solo_row.empty else 0
            avg_inv_vid  = int(inv_rows["Vistas totales"].sum() / max(inv_rows["Videos"].sum(), 1))
            st.markdown(f"""
<div class="rec-good">
🏆 <b>{best_guest['Invitado']}</b> fue el invitado con más impacto: <b>{int(best_guest['Vistas totales']):,} vistas</b> en {int(best_guest['Videos'])} videos
({int(best_guest['Vistas Shorts']):,} por Shorts + {int(best_guest['Vistas Largos']):,} por Largos).<br><br>
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
Eso indica que el gancho (primeros 1-2 segundos) o el tema no enganchó lo suficiente
para que el algoritmo los distribuya.
</div>""", unsafe_allow_html=True)
        else:
            st.info("No hay Shorts en el período seleccionado.")

        st.markdown("### Videos Largos")
        if not df_l.empty:
            avg_l = int(df_l["views"].mean())
            st.markdown(f"""
<div class="rec-good">
📹 Publicaste <b>{len(df_l)} Videos Largos</b> con un promedio de <b>{avg_l:,} vistas cada uno</b>.<br>
El más visto fue <b>"{top_largo['title'][:65]}"</b> con <b>{int(top_largo['views']):,} vistas</b>
(invitado: {top_largo['guest']}).
</div>""", unsafe_allow_html=True)

            if not df_van2.empty:
                df_ml = df_l.merge(df_van2, on="id", how="left", suffixes=("", "_analytics")).dropna(subset=["averageViewPercentage"])
                if not df_ml.empty:
                    avg_ret = df_ml["averageViewPercentage"].mean()
                    st.markdown(f"""
<div class="{'rec-good' if avg_ret >= 30 else 'rec-card'}">
⏱️ <b>Retención promedio: {avg_ret:.1f}%</b> de los videos largos.
{"Buen número — la gente termina de ver una parte importante del contenido." if avg_ret >= 30 else "Está por debajo del 30% recomendado. La gente abandona antes de la mitad."}
</div>""", unsafe_allow_html=True)

        # ════════════════════════════════════════
        st.markdown("## 🚀 QUÉ HACER AHORA")

        acciones = []

        # Acción sobre invitados
        if best_guest is not None:
            acciones.append(f"""
**1. Traé de vuelta a {best_guest['Invitado']}**
Fue tu invitado más efectivo con {int(best_guest['Vistas totales']):,} vistas.
Repetir invitados exitosos es una estrategia probada — el público ya los conoce y confía.
Idealmente en un formato nuevo o con un ángulo de conversación diferente al anterior.""")

        # Acción sobre Shorts
        if not df_s.empty and top_short is not None:
            acciones.append(f"""
**2. Replicá la fórmula de tu Short más viral**
"{top_short['title'][:60]}" funcionó con {int(top_short['views']):,} vistas.
Revisá: ¿qué dice en el primer segundo? ¿Es una pregunta, una afirmación fuerte, o algo inesperado?
Usá esa misma estructura de arranque en los próximos 3 Shorts.""")

        # Acción sobre retención (reemplaza CTR que ya no está disponible)

        # Acción sobre retención
        if not df_van2.empty and not df_l.empty:
            df_ml3 = df_l.merge(df_van2, on="id", how="left", suffixes=("", "_analytics")).dropna(subset=["averageViewPercentage"])
            if not df_ml3.empty:
                avg_ret2 = df_ml3["averageViewPercentage"].mean()
                if avg_ret2 < 35:
                    acciones.append(f"""
**4. Mejorá los primeros 2 minutos de los Videos Largos**
La retención promedio es {avg_ret2:.0f}% — la gente se va antes de la mitad.
La causa más común: intro demasiado larga o arranque lento.
Probá empezar directamente con la idea más fuerte del episodio, sin presentaciones.""")

        # Acción sobre invitado sin explorar
        if not inv_rows.empty:
            menos_visto = inv_rows.iloc[-1]
            acciones.append(f"""
**5. Analizá por qué {menos_visto['Invitado']} tuvo menos tracción**
Solo generó {int(menos_visto['Vistas totales']):,} vistas en {int(menos_visto['Videos'])} videos.
Puede ser por el tema tratado, la hora de publicación, la miniatura, o simplemente que el público aún no lo conoce.
Antes de descartarlo, probá con un Short que tenga un gancho más fuerte sobre su historia.""")

        if acciones:
            for accion in acciones:
                st.markdown(accion)
                st.divider()
        else:
            st.info("Necesitás más datos en el período para generar recomendaciones.")

# ════════════════════════════════════════════════════════════════════════════
# TAB 7 — DIAGNÓSTICO
# ════════════════════════════════════════════════════════════════════════════
with tab7:
    st.subheader("🔧 Diagnóstico — Clasificación de todos los videos")
    st.caption("Usá esta tabla para verificar que cada video esté bien clasificado. Si ves errores avisale al desarrollador.")

    if df_all.empty:
        st.info("Sin datos.")
    else:
        st.markdown(f"**Total de videos cargados:** {len(df_all)}  |  "
                    f"**Shorts:** {df_all['is_short'].sum()}  |  "
                    f"**Largos:** {(~df_all['is_short']).sum()}")

        # Botón de descarga — punto y coma para Excel en español, sin emojis
        import re as _re
        def _limpiar(texto):
            if not isinstance(texto, str):
                return texto
            return _re.sub(r'[^\x00-\x7FáéíóúÁÉÍÓÚñÑüÜ¿¡@._\-\(\)\[\]#:,/ ]', '', texto).strip()

        csv_diag = df_all[["title","tipo","guest","duration_min","views","published_at"]].copy()
        csv_diag["title"]   = csv_diag["title"].apply(_limpiar)
        csv_diag["guest"]   = csv_diag["guest"].apply(_limpiar)
        csv_diag["published_at"] = csv_diag["published_at"].dt.strftime("%Y-%m-%d")
        csv_diag.columns = ["Titulo","Tipo","Invitado detectado","Duracion (min)","Vistas","Publicado"]
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
                "thumbnail":"Miniatura","title":"Título","tipo":"Tipo",
                "guest":"Invitado detectado","duration_min":"Duración (min)",
                "views":"Vistas","published_at":"Publicado",
            }),
            column_config={"Miniatura": st.column_config.ImageColumn("Miniatura", width="small")},
            use_container_width=True,
            hide_index=True,
        )

        st.divider()
        st.markdown("### Validación contra números reales")
        ESPERADO_LARGOS = {
            "Solo (sin invitado)": 13,
            "SarcaOne":            6,
            "Roas Marketing":      6,
            "Silvia Vales":        6,
            "Juan Massola":        6,
            "Nahuel":              5,
            "Bauti Aschiero":      1,
        }
        largos_actuales = df_all[~df_all["is_short"]].groupby("guest")["id"].count().to_dict()
        val_rows = []
        for inv, esperado in ESPERADO_LARGOS.items():
            actual = largos_actuales.get(inv, 0)
            diferencia = actual - esperado
            estado = "✅" if diferencia == 0 else ("⬆️ sobran" if diferencia > 0 else "⬇️ faltan")
            val_rows.append({"Invitado": inv, "Esperado": esperado, "Actual": actual,
                             "Diferencia": abs(diferencia), "Estado": estado if diferencia == 0 else f"{estado} {abs(diferencia)}"})
        st.dataframe(pd.DataFrame(val_rows), use_container_width=True, hide_index=True)
        total_largos = df_all[~df_all["is_short"]]["id"].count()
        st.markdown(f"**Total largos detectados:** {total_largos} (esperado: 43)")

        # Mostrar los largos de "Solo" para identificar el intruso
        solo_largos = df_all[(~df_all["is_short"]) & (df_all["guest"] == "Solo (sin invitado)")].copy()
        solo_largos = solo_largos[["title","duration_min","views","published_at"]].sort_values("published_at")
        solo_largos.columns = ["Título","Duración (min)","Vistas","Publicado"]
        solo_largos["Publicado"] = solo_largos["Publicado"].dt.strftime("%Y-%m-%d")
        with st.expander(f"Ver los {len(solo_largos)} largos de 'Solo (sin invitado)' — identificar el intruso"):
            st.dataframe(solo_largos, use_container_width=True, hide_index=True)

        st.divider()
        st.markdown("### Resumen de clasificación")
        col_a, col_b = st.columns(2)

        resumen_tipo = df_all.groupby("tipo").agg(
            Videos=("id","count"), Vistas=("views","sum")
        ).reset_index()
        col_a.dataframe(resumen_tipo, use_container_width=True, hide_index=True)

        resumen_guest = df_all.groupby("guest").agg(
            Videos=("id","count"),
            Shorts=("is_short","sum"),
            Largos=("is_short", lambda x: (~x).sum()),
            Vistas=("views","sum"),
        ).reset_index().sort_values("Videos", ascending=False)
        col_b.dataframe(resumen_guest, use_container_width=True, hide_index=True)
