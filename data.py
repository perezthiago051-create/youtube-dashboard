import re
import pandas as pd

# ── Mapa de invitados conocidos del canal ─────────────────────────────────────
# Busca estas palabras clave en título + descripción completa (en minúsculas).
# El orden importa: primero los más específicos.
GUEST_MAP = {
    "SarcaOne":       [
        "sarcaone", "sarca one", "@sarcaone", "instagram.com/sarcaone",
        "gonzalo sarca", "(sarca)", "freestyler argentino", " sarca,", " sarca ",
    ],
    "Roas Marketing": [
        "roas.marketing", "@roas.marketing", "instagram.com/roas.marketing",
        "roas marketing", "lucas nigon", "lucas nigón",
    ],
    "Silvia Vales":   [
        "silviavales", "silvia vales", "@silviavales", "instagram.com/silviavales",
        "silviavales.consultora", "coach y chamana", "master coach", "chamana",
    ],
    "Juan Massola":   [
        "juanmassola", "juan massola", "@juanmassola", "instagram.com/juanmassola", "massola",
    ],
    "Nahuel":         [
        "nahue_leon_", "@nahue_leon_", "instagram.com/nahue_leon_", "nahue leon", "nahuel",
    ],
    "Bauti Aschiero": [
        "bautiaschiero", "@bautiaschiero", "instagram.com/bautiaschiero",
        "bauti aschiero", "bauti", "aschiero",
    ],
}

# Handles propios del canal (para no confundirlos con invitados)
_CANAL_HANDLES = {"crudoyqueso", "crudoyquesopodcast", "tomperez", "thiago"}

# ── Umbrales de clasificación de formato (en segundos) ─────────────────────────
SHORT_MAX_SEC   = 70      # <= 70s (o con #shorts) => Short
COMPLETO_MIN_SEC = 3600   # > 60 min => Completo (capítulo entero)
# Entre SHORT_MAX_SEC y COMPLETO_MIN_SEC => Mediano (clips de 3-25 min típicamente)

TIPO_ORDEN = ["Short", "Mediano", "Completo"]
TIPO_COLORS = {
    "Short":    "#FF0050",
    "Mediano":  "#FF8C00",
    "Completo": "#CC0000",
    "Total":    "#333333",
}


def parse_duration(duration: str) -> int:
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration or "PT0S")
    if not match:
        return 0
    h = int(match.group(1) or 0)
    m = int(match.group(2) or 0)
    s = int(match.group(3) or 0)
    return h * 3600 + m * 60 + s


def classify_video_type(video: dict) -> str:
    """Clasifica el video en 3 formatos:
    - Short: duración <= 70s o tiene #shorts en título/descripción
    - Mediano: clips de 70s a 60 min (lo típico: 3-25 min)
    - Completo: capítulos enteros de más de 60 min
    """
    cd  = video.get("contentDetails", {})
    sn  = video.get("snippet", {})
    dur = parse_duration(cd.get("duration", "PT0S"))

    if dur <= SHORT_MAX_SEC:
        return "Short"

    text = (sn.get("title", "") + sn.get("description", "")[:300]).lower()
    if "#short" in text:
        return "Short"

    if dur > COMPLETO_MIN_SEC:
        return "Completo"

    return "Mediano"


def extract_guest(title: str, description: str = "") -> str:
    """Busca invitados por sus handles de Instagram en título + descripción completa."""
    # Buscar en título + descripción completa
    text = (title + " " + description).lower()
    for guest_name, keywords in GUEST_MAP.items():
        for kw in keywords:
            if kw in text:
                return guest_name
    return "Solo (sin invitado)"


def fetch_all_videos(youtube, channel_id: str) -> list:
    videos, token = [], None
    while True:
        res = youtube.search().list(
            part="id",
            channelId=channel_id,
            maxResults=50,
            pageToken=token,
            type="video",
            order="date",
        ).execute()

        ids = [i["id"]["videoId"] for i in res.get("items", [])]
        if ids:
            detail = youtube.videos().list(
                part="snippet,statistics,contentDetails",
                id=",".join(ids),
            ).execute()
            videos.extend(detail.get("items", []))

        token = res.get("nextPageToken")
        if not token:
            break
    return videos


def videos_to_df(videos: list) -> pd.DataFrame:
    rows = []
    for v in videos:
        sn    = v.get("snippet", {})
        st    = v.get("statistics", {})
        cd    = v.get("contentDetails", {})
        title = sn.get("title", "")
        desc  = sn.get("description", "")
        views = int(st.get("viewCount", 0))
        likes = int(st.get("likeCount", 0))
        tipo  = classify_video_type(v)
        dur_sec = parse_duration(cd.get("duration", "PT0S"))
        rows.append({
            "id":           v["id"],
            "title":        title,
            "description":  desc,
            "published_at": sn.get("publishedAt", ""),
            "views":        views,
            "likes":        likes,
            "comments":     int(st.get("commentCount", 0)),
            "duration_sec": dur_sec,
            "duration_min": round(dur_sec / 60, 1),
            "tipo":         tipo,
            "is_short":     tipo == "Short",  # compat
            "guest":        extract_guest(title, desc),
            "like_rate":    round(likes / max(views, 1) * 100, 2),
            "thumbnail":    sn.get("thumbnails", {}).get("medium", {}).get("url", ""),
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df["published_at"] = pd.to_datetime(df["published_at"], utc=True)
        df["date"]  = df["published_at"].dt.date
        df["month"] = df["published_at"].dt.to_period("M").astype(str)
    return df


def fetch_channel_analytics(analytics, start: str, end: str):
    try:
        res = analytics.reports().query(
            ids="channel==MINE",
            startDate=start,
            endDate=end,
            metrics="views,estimatedMinutesWatched,averageViewDuration,subscribersGained,subscribersLost",
            dimensions="day",
            sort="day",
        ).execute()
        cols = [h["name"] for h in res.get("columnHeaders", [])]
        df = pd.DataFrame(res.get("rows", []), columns=cols)
        if not df.empty:
            df["day"] = pd.to_datetime(df["day"])
            for c in df.columns[1:]:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        return df, None
    except Exception as e:
        return pd.DataFrame(), str(e)


def fetch_video_analytics(analytics, start: str, end: str):
    try:
        res = analytics.reports().query(
            ids="channel==MINE",
            startDate=start,
            endDate=end,
            metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage",
            dimensions="video",
            sort="-views",
            maxResults=200,
        ).execute()
        cols = [h["name"] for h in res.get("columnHeaders", [])]
        df = pd.DataFrame(res.get("rows", []), columns=cols)
        if not df.empty:
            df = df.rename(columns={"video": "id"})
            for c in df.columns[1:]:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        return df, None
    except Exception as e:
        return pd.DataFrame(), str(e)


def build_guest_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Resumen por invitado, desglosado por los 3 formatos (Short/Mediano/Completo)."""
    if df.empty:
        return pd.DataFrame()
    result = []
    for guest in df["guest"].unique():
        gdf = df[df["guest"] == guest]
        row = {
            "Invitado":       guest,
            "Videos":         len(gdf),
            "Vistas totales": int(gdf["views"].sum()),
            "Likes totales":  int(gdf["likes"].sum()),
            "Comentarios":    int(gdf["comments"].sum()),
        }
        for tipo in TIPO_ORDEN:
            tdf = gdf[gdf["tipo"] == tipo]
            row[f"Videos {tipo}"] = len(tdf)
            row[f"Vistas {tipo}"] = int(tdf["views"].sum())
        result.append(row)
    return pd.DataFrame(result).sort_values("Vistas totales", ascending=False)


def fetch_retention_curve(analytics, video_id: str, start: str, end: str):
    """Curva de retención real para un video específico (audienceWatchRatio)."""
    try:
        res = analytics.reports().query(
            ids="channel==MINE",
            startDate=start,
            endDate=end,
            metrics="audienceWatchRatio,relativeRetentionPerformance",
            dimensions="elapsedVideoTimeRatio",
            filters=f"video=={video_id}",
        ).execute()
        cols = [h["name"] for h in res.get("columnHeaders", [])]
        df = pd.DataFrame(res.get("rows", []), columns=cols)
        if not df.empty:
            for c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        return df, None
    except Exception as e:
        return pd.DataFrame(), str(e)
