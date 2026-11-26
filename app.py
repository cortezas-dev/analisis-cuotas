"""
📊 Panel de Cuotas y Partidos — Streamlit + The Odds API
Listo para desplegar en Streamlit Community Cloud (share.streamlit.io) vía GitHub.
"""

import html as htmllib
import random
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st

# ──────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN GENERAL
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Panel de Cuotas",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

API_BASE = "https://api.the-odds-api.com/v4"
BEST = "⭐ Mejor cuota (todas las casas)"
OTHER = "🏅 Otros deportes"
GROUP_MAP = {
    "Soccer": "⚽ Fútbol",
    "Basketball": "🏀 Baloncesto",
    "Baseball": "⚾ Béisbol",
    "Tennis": "🎾 Tenis",
}
CATEGORY_ORDER = ["⚽ Fútbol", "🏀 Baloncesto", "⚾ Béisbol", "🎾 Tenis", OTHER]
MARKET_LABELS = {
    "h2h": "Ganador (1X2 / Moneyline)",
    "totals": "Totales (Over/Under)",
    "spreads": "Hándicap (Spread)",
}
MARKET_SHORT = {"h2h": "1X2/ML", "totals": "O/U", "spreads": "HC"}
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
TIMEZONES = [
    "Europe/Madrid",
    "Atlantic/Canary",
    "Europe/London",
    "America/New_York",
    "America/Mexico_City",
    "America/Argentina/Buenos_Aires",
    "UTC",
]

st.markdown(
    """
<style>
.hero{padding:1.2rem 1.6rem;border-radius:16px;
      background:linear-gradient(135deg,#0f766e 0%,#2563eb 100%);color:#fff;margin-bottom:1.1rem}
.hero h1{margin:0;font-size:1.8rem;color:#fff;padding:0}
.hero p{margin:.35rem 0 0;opacity:.92}
.mk-title{font-weight:600;font-size:.78rem;opacity:.75;margin:.2rem 0 .4rem;
          text-transform:uppercase;letter-spacing:.05em}
.chips{display:flex;flex-direction:column;gap:6px}
.chip{display:flex;align-items:center;gap:8px;padding:6px 10px;border-radius:10px;
      background:rgba(128,128,128,.12);border:1px solid rgba(128,128,128,.22)}
.chip-l{flex:1;font-size:.88rem}
.chip-o{font-weight:700;background:#0f766e;color:#fff;padding:2px 9px;border-radius:8px;font-size:.9rem}
.chip-p{font-size:.78rem;opacity:.7;min-width:36px;text-align:right}
.empty{opacity:.55;font-size:.85rem}
</style>
""",
    unsafe_allow_html=True,
)


# ──────────────────────────────────────────────────────────────────────────────
# UTILIDADES
# ──────────────────────────────────────────────────────────────────────────────
def eur(x: float) -> str:
    """Formatea un importe en euros al estilo español: 1.234,56 €"""
    s = f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} €"


def fmt_dt(dt) -> str:
    return f"{DIAS[dt.weekday()]} {dt:%d/%m} · {dt:%H:%M}"


def category_of(group: str) -> str:
    return GROUP_MAP.get(group, OTHER)


def get_secret_key() -> str:
    try:
        return str(st.secrets.get("ODDS_API_KEY", ""))
    except Exception:
        return ""


# ──────────────────────────────────────────────────────────────────────────────
# THE ODDS API
# ──────────────────────────────────────────────────────────────────────────────
class OddsAPIError(Exception):
    pass


def _api_get(path: str, api_key: str, params: dict | None = None):
    query = {"apiKey": api_key, **(params or {})}
    try:
        r = requests.get(f"{API_BASE}{path}", params=query, timeout=20)
    except requests.RequestException as exc:
        raise OddsAPIError(f"Error de conexión con The Odds API: {exc}") from exc

    if r.status_code == 401:
        raise OddsAPIError("API Key no válida o desactivada. Revísala en the-odds-api.com.")
    if r.status_code == 429:
        raise OddsAPIError("Has superado el límite de peticiones o de créditos de tu plan.")
    if r.status_code == 422:
        raise OddsAPIError("422")
    if not r.ok:
        raise OddsAPIError(f"Error {r.status_code}: {r.text[:200]}")
    return r.json(), r.headers.get("x-requests-remaining")


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_sports(api_key: str) -> list[dict]:
    data, _ = _api_get("/sports/", api_key)
    return data


@st.cache_data(ttl=300, show_spinner=False)
def fetch_odds(api_key: str, sport_key: str, region: str):
    """Pide cuotas probando de más a menos mercados (no todos los deportes admiten todos)."""
    attempts = ["h2h,spreads,totals", "h2h,totals", "h2h,spreads", "h2h"]
    last_error = None
    for markets in attempts:
        try:
            return _api_get(
                f"/sports/{sport_key}/odds/",
                api_key,
                {
                    "regions": region,
                    "markets": markets,
                    "oddsFormat": "decimal",
                    "dateFormat": "iso",
                },
            )
        except OddsAPIError as exc:
            if str(exc) != "422":
                raise
            last_error = exc
    raise OddsAPIError(
        "Esta competición no tiene cuotas disponibles ahora mismo para los mercados solicitados."
    ) from last_error


# ──────────────────────────────────────────────────────────────────────────────
# DATOS DE DEMOSTRACIÓN (mismo formato que The Odds API)
# ──────────────────────────────────────────────────────────────────────────────
DEMO_SPORTS = [
    {"key": "soccer_spain_la_liga", "title": "La Liga – España", "group": "Soccer"},
    {"key": "soccer_epl", "title": "Premier League – Inglaterra", "group": "Soccer"},
    {"key": "soccer_uefa_champs_league", "title": "UEFA Champions League", "group": "Soccer"},
    {"key": "basketball_nba", "title": "NBA", "group": "Basketball"},
    {"key": "basketball_euroleague", "title": "Euroliga", "group": "Basketball"},
    {"key": "baseball_mlb", "title": "MLB", "group": "Baseball"},
    {"key": "tennis_atp_demo", "title": "ATP Tour (demo)", "group": "Tennis"},
    {"key": "icehockey_nhl", "title": "NHL", "group": "Ice Hockey"},
    {"key": "americanfootball_nfl", "title": "NFL", "group": "American Football"},
]

DEMO_TEAMS = {
    "soccer_spain_la_liga": [
        "Real Madrid", "FC Barcelona", "Atlético de Madrid", "Athletic Club",
        "Real Sociedad", "Villarreal", "Real Betis", "Sevilla FC", "Valencia CF",
        "Girona FC", "Celta de Vigo", "RCD Mallorca",
    ],
    "soccer_epl": [
        "Manchester City", "Arsenal", "Liverpool", "Chelsea", "Tottenham",
        "Newcastle", "Aston Villa", "Manchester United", "Brighton", "West Ham",
    ],
    "soccer_uefa_champs_league": [
        "Real Madrid", "Bayern Munich", "Paris Saint-Germain", "Inter", "FC Barcelona",
        "Manchester City", "Arsenal", "Borussia Dortmund", "Juventus", "Benfica",
    ],
    "basketball_nba": [
        "Los Angeles Lakers", "Boston Celtics", "Golden State Warriors", "Denver Nuggets",
        "Milwaukee Bucks", "New York Knicks", "Miami Heat", "Dallas Mavericks",
        "Phoenix Suns", "Philadelphia 76ers",
    ],
    "basketball_euroleague": [
        "Real Madrid", "FC Barcelona", "Olympiacos", "Panathinaikos", "Fenerbahçe",
        "Anadolu Efes", "Partizan", "Maccabi Tel Aviv", "Baskonia", "Valencia Basket",
    ],
    "baseball_mlb": [
        "New York Yankees", "Los Angeles Dodgers", "Boston Red Sox", "Atlanta Braves",
        "Houston Astros", "New York Mets", "Chicago Cubs", "San Diego Padres",
        "Philadelphia Phillies", "San Francisco Giants",
    ],
    "tennis_atp_demo": [
        "Carlos Alcaraz", "Jannik Sinner", "Novak Djokovic", "Alexander Zverev",
        "Daniil Medvedev", "Taylor Fritz", "Casper Ruud", "Alex de Minaur",
        "Holger Rune", "Andrey Rublev",
    ],
    "icehockey_nhl": [
        "Boston Bruins", "Toronto Maple Leafs", "Edmonton Oilers", "Colorado Avalanche",
        "Vegas Golden Knights", "New York Rangers", "Florida Panthers", "Dallas Stars",
    ],
    "americanfootball_nfl": [
        "Kansas City Chiefs", "San Francisco 49ers", "Philadelphia Eagles", "Buffalo Bills",
        "Dallas Cowboys", "Baltimore Ravens", "Detroit Lions", "Miami Dolphins",
    ],
}

DEMO_BOOKS = [("bet365", "Bet365", 0.055), ("codere", "Codere", 0.070), ("pinnacle", "Pinnacle", 0.030)]
# (paso entre líneas de totales, variación de probabilidad por paso)
DEMO_STEP = {
    "Soccer": (1.0, 0.17), "Basketball": (5.0, 0.09), "Baseball": (1.0, 0.10),
    "Tennis": (1.0, 0.10), "Ice Hockey": (1.0, 0.12), "American Football": (3.0, 0.08),
}


def _book_odds(p: float, margin: float, rng: random.Random) -> float:
    return max(1.02, round(1 / (p * (1 + margin)) * rng.uniform(0.97, 1.03), 2))


def _base_total(key: str, group: str, rng: random.Random) -> float:
    if group == "Soccer":
        return rng.choice([2.5, 2.5, 3.5])
    if group == "Basketball":
        return (rng.randint(155, 170) if "euroleague" in key else rng.randint(214, 238)) + 0.5
    if group == "Baseball":
        return rng.choice([7.5, 8.5, 9.5])
    if group == "Tennis":
        return rng.choice([20.5, 21.5, 22.5])
    if group == "Ice Hockey":
        return rng.choice([5.5, 6.5])
    return rng.randint(40, 52) + 0.5


def _spread_size(group: str, rng: random.Random) -> float:
    if group == "Soccer":
        return rng.choice([0.5, 1.5])
    if group == "Basketball":
        return round(rng.uniform(1.5, 11.5) * 2) / 2
    if group == "Tennis":
        return rng.choice([1.5, 2.5, 3.5])
    if group == "American Football":
        return round(rng.uniform(1, 10) * 2) / 2
    return 1.5


def generate_demo_events(sport_key: str) -> list[dict]:
    meta = next(s for s in DEMO_SPORTS if s["key"] == sport_key)
    group = meta["group"]
    is_soccer = group == "Soccer"
    teams = DEMO_TEAMS[sport_key]
    base = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    rng = random.Random(f"{sport_key}-{base.date()}")
    step, shift = DEMO_STEP[group]
    n_events = 6 if group == "Tennis" else 8

    events = []
    for i in range(n_events):
        home, away = rng.sample(teams, 2)
        kickoff = base + timedelta(hours=rng.randint(3, 160), minutes=rng.choice([0, 15, 30, 45]))

        if is_soccer:
            p_home = rng.uniform(0.25, 0.62)
            p_draw = rng.uniform(0.20, 0.30)
            p_away = max(0.08, 1 - p_home - p_draw)
        else:
            p_home = rng.uniform(0.30, 0.75)
            p_draw, p_away = 0.0, 1 - p_home

        main_total = _base_total(sport_key, group, rng)
        spread = _spread_size(group, rng)
        home_is_fav = p_home >= p_away
        home_pt = -spread if home_is_fav else spread
        p_cover = rng.uniform(0.47, 0.53)

        bookmakers = []
        for bkey, btitle, margin in DEMO_BOOKS:
            h2h = [{"name": home, "price": _book_odds(p_home, margin, rng)}]
            if is_soccer:
                h2h.append({"name": "Draw", "price": _book_odds(p_draw, margin, rng)})
            h2h.append({"name": away, "price": _book_odds(p_away, margin, rng)})

            totals = []
            for k in (-1, 0, 1):
                line = main_total + k * step
                p_over = min(0.92, max(0.08, 0.5 - k * shift))
                totals.append({"name": "Over", "price": _book_odds(p_over, margin, rng), "point": line})
                totals.append({"name": "Under", "price": _book_odds(1 - p_over, margin, rng), "point": line})

            spreads = [
                {"name": home, "price": _book_odds(p_cover, margin, rng), "point": home_pt},
                {"name": away, "price": _book_odds(1 - p_cover, margin, rng), "point": -home_pt},
            ]
            bookmakers.append({
                "key": bkey,
                "title": btitle,
                "markets": [
                    {"key": "h2h", "outcomes": h2h},
                    {"key": "totals", "outcomes": totals},
                    {"key": "spreads", "outcomes": spreads},
                ],
            })

        events.append({
            "id": f"demo-{sport_key}-{i}",
            "sport_key": sport_key,
            "commence_time": kickoff.isoformat().replace("+00:00", "Z"),
            "home_team": home,
            "away_team": away,
            "bookmakers": bookmakers,
        })
    return sorted(events, key=lambda e: e["commence_time"])


# ──────────────────────────────────────────────────────────────────────────────
# PROCESADO DE CUOTAS
# ──────────────────────────────────────────────────────────────────────────────
def _selection_name(mkey: str, name: str, home: str, point, is_soccer: bool) -> str:
    if mkey == "h2h":
        if name.lower() == "draw":
            return "Empate (X)"
        if name == home:
            return f"{name} (1 · Local)" if is_soccer else f"{name} (Local)"
        return f"{name} (2 · Visitante)" if is_soccer else f"{name} (Visitante)"
    if mkey == "totals":
        label = "Más de" if name.lower() == "over" else "Menos de"
        return f"{label} {point:g}"
    return f"{name} {point:+g}"


def _order(mkey: str, name: str, home: str) -> int:
    if mkey == "totals":
        return 0 if name.lower() == "over" else 1
    if name == home:
        return 0
    return 1 if name.lower() == "draw" else 2


def market_name(group: str, mkey: str) -> str:
    if mkey == "h2h":
        return "Resultado final (1X2)" if group == "Soccer" else "Ganador del partido (Moneyline)"
    if mkey == "totals":
        unit = {
            "Soccer": "goles", "Basketball": "puntos", "Baseball": "carreras",
            "Tennis": "juegos", "Ice Hockey": "goles", "American Football": "puntos",
        }.get(group, "puntos/goles")
        return f"Total de {unit} (Over/Under)"
    return "Hándicap asiático" if group == "Soccer" else "Hándicap / Spread"


def build_selections(events: list[dict], tz: ZoneInfo, bookmaker: str, league: str, group: str) -> pd.DataFrame:
    is_soccer = group == "Soccer"
    rows = []
    for ev in events:
        kickoff = datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00")).astimezone(tz)
        home, away = ev["home_team"], ev["away_team"]
        for bk in ev.get("bookmakers", []):
            if bookmaker != BEST and bk["title"] != bookmaker:
                continue
            for mk in bk.get("markets", []):
                mkey = mk["key"]
                if mkey not in MARKET_LABELS:
                    continue
                for o in mk.get("outcomes", []):
                    price = o.get("price")
                    if not price or price <= 1:
                        continue
                    point = o.get("point")
                    rows.append({
                        "event_id": ev["id"],
                        "Grupo": group,
                        "Liga": league,
                        "Partido": f"{home} vs {away}",
                        "Local": home,
                        "Inicio": kickoff,
                        "mkey": mkey,
                        "Mercado": market_name(group, mkey),
                        "Selección": _selection_name(mkey, o["name"], home, point, is_soccer),
                        "Línea": point,
                        "Cuota": float(price),
                        "Casa": bk["title"],
                        "orden": _order(mkey, o["name"], home),
                    })
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["Línea"] = pd.to_numeric(df["Línea"], errors="coerce")
    # Mejor cuota por selección (si hay varias casas)
    df = (
        df.sort_values("Cuota", ascending=False)
        .drop_duplicates(["event_id", "mkey", "Selección"])
        .reset_index(drop=True)
    )
    df["Prob (%)"] = 1 / df["Cuota"] * 100  # probabilidad implícita

    # Probabilidad "sin margen" aproximada (normalizando cada mercado/línea)
    df["_grp"] = df["Línea"].abs().fillna(-1)
    g = df.groupby(["event_id", "mkey", "_grp"])["Prob (%)"]
    total, count = g.transform("sum"), g.transform("count")
    df["Prob sin margen (%)"] = (df["Prob (%)"] / total * 100).where(count >= 2)
    return df.drop(columns="_grp")


def balanced_line(sub: pd.DataFrame) -> pd.DataFrame:
    """Para totales/hándicap: elige la línea con cuotas más igualadas (la 'principal')."""
    if sub.empty:
        return sub
    tmp = sub.assign(_k=sub["Línea"].abs())
    spreads = tmp.groupby("_k")["Cuota"].agg(lambda s: s.max() - s.min() if len(s) > 1 else 99)
    return tmp[tmp["_k"] == spreads.idxmin()].drop(columns="_k").sort_values("orden")


def chips_html(rows: pd.DataFrame) -> str:
    if rows.empty:
        return '<div class="empty">Sin cuotas</div>'
    items = "".join(
        f'<div class="chip"><span class="chip-l">{htmllib.escape(r["Selección"])}</span>'
        f'<span class="chip-o">{r["Cuota"]:.2f}</span>'
        f'<span class="chip-p">{r["Prob (%)"]:.0f}%</span></div>'
        for _, r in rows.iterrows()
    )
    return f'<div class="chips">{items}</div>'


def render_event_card(ev_df: pd.DataFrame):
    first = ev_df.iloc[0]
    with st.container(border=True):
        st.markdown(f"**{first['Partido']}**  \n🕒 {fmt_dt(first['Inicio'])} · _{first['Liga']}_")
        cols = st.columns(3)
        blocks = [
            ("h2h", "Ganador", ev_df[ev_df.mkey == "h2h"].sort_values("orden")),
            ("totals", "Over / Under", balanced_line(ev_df[ev_df.mkey == "totals"])),
            ("spreads", "Hándicap", balanced_line(ev_df[ev_df.mkey == "spreads"])),
        ]
        for col, (_, title, sub) in zip(cols, blocks):
            with col:
                st.markdown(f'<div class="mk-title">{title}</div>{chips_html(sub)}', unsafe_allow_html=True)


ALT_NAMES = {
    "h2h": '"1X2", "Match Winner", "Moneyline" o "Ganador del partido"',
    "totals": '"Total", "Más/Menos" u "Over/Under"',
    "spreads": '"Hándicap", "Spread" o "Línea"',
}


def steps_md(row: pd.Series) -> str:
    return (
        f"1. Abre tu casa de apuestas y ve a **{row['Liga']}**.\n"
        f"2. Busca el partido **{row['Partido']}** ({fmt_dt(row['Inicio'])}).\n"
        f"3. Abre el mercado **{row['Mercado']}** (también puede llamarse {ALT_NAMES[row['mkey']]}).\n"
        f"4. Elige **{row['Selección']}** — cuota de referencia **{row['Cuota']:.2f}** "
        f"(la mejor encontrada: {row['Casa']}).\n"
        f"5. Pon tu importe y comprueba el retorno antes de confirmar."
    )


# ──────────────────────────────────────────────────────────────────────────────
# BARRA LATERAL
# ──────────────────────────────────────────────────────────────────────────────
st.sidebar.title("⚙️ Configuración")

use_demo = st.sidebar.toggle("🧪 Datos de demostración", value=True,
                             help="Actívalo para probar la app sin API Key.")
api_key = st.sidebar.text_input(
    "API Key de The Odds API",
    value=get_secret_key(),
    type="password",
    disabled=use_demo,
    help="Consíguela gratis en the-odds-api.com. También puedes guardarla como "
         "secreto ODDS_API_KEY en Streamlit Cloud.",
).strip()
region = st.sidebar.selectbox("Región de casas de apuestas", ["eu", "uk", "us", "au"], index=0,
                              disabled=use_demo)

if not use_demo and not api_key:
    st.sidebar.warning("Introduce tu API Key o activa los datos de demostración.")
    st.markdown(
        '<div class="hero"><h1>📊 Panel de Cuotas y Partidos</h1>'
        "<p>Introduce tu API Key en la barra lateral o activa el modo demostración.</p></div>",
        unsafe_allow_html=True,
    )
    st.stop()

# Lista de competiciones
try:
    if use_demo:
        sports = DEMO_SPORTS
    else:
        sports = [s for s in fetch_sports(api_key) if s.get("active") and not s.get("has_outrights")]
except OddsAPIError as exc:
    st.error(f"❌ {exc}")
    st.stop()

by_category: dict[str, list[dict]] = {}
for s in sports:
    by_category.setdefault(category_of(s["group"]), []).append(s)
categories = [c for c in CATEGORY_ORDER if c in by_category]
if not categories:
    st.error("No se han encontrado competiciones activas.")
    st.stop()

category = st.sidebar.selectbox("Deporte", categories)
leagues = sorted(by_category[category], key=lambda s: s["title"])
league_titles = {s["key"]: s["title"] for s in leagues}
league_groups = {s["key"]: s["group"] for s in leagues}
sport_key = st.sidebar.selectbox("Competición", list(league_titles), format_func=lambda k: league_titles.get(k, k))

tz_name = st.sidebar.selectbox("Zona horaria", TIMEZONES, index=0)
tz = ZoneInfo(tz_name)
horizon = st.sidebar.slider("Partidos de los próximos … días", 1, 14, 7)

# Carga de partidos
with st.spinner("Cargando partidos y cuotas…"):
    try:
        if use_demo:
            raw_events, remaining = generate_demo_events(sport_key), None
        else:
            raw_events, remaining = fetch_odds(api_key, sport_key, region)
    except OddsAPIError as exc:
        st.error(f"❌ {exc}")
        st.stop()

now_utc = datetime.now(timezone.utc)
limit_utc = now_utc + timedelta(days=horizon)
events = [
    e for e in raw_events
    if now_utc <= datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00")) <= limit_utc
]

bookmakers_available = sorted({b["title"] for e in events for b in e.get("bookmakers", [])})
bookmaker = st.sidebar.selectbox("Casa de apuestas", [BEST] + bookmakers_available)

if remaining is not None:
    st.sidebar.caption(f"Créditos restantes de la API: **{remaining}**")
if not use_demo:
    st.sidebar.caption("Cada consulta consume 1 crédito por mercado y región (hasta 3).")
if st.sidebar.button("🔄 Actualizar datos"):
    st.cache_data.clear()
    st.rerun()

# ──────────────────────────────────────────────────────────────────────────────
# CABECERA
# ──────────────────────────────────────────────────────────────────────────────
st.markdown(
    f'<div class="hero"><h1>📊 Panel de Cuotas y Partidos</h1>'
    f"<p>{category} · {league_titles[sport_key]} · horario {tz_name}</p></div>",
    unsafe_allow_html=True,
)
if use_demo:
    st.info("🧪 **Modo demostración**: las cuotas son ficticias y solo sirven para probar la app.")

df = build_selections(events, tz, bookmaker, league_titles[sport_key], league_groups[sport_key])
if df.empty:
    st.warning("No hay partidos con cuotas en este rango. Prueba con más días u otra competición.")
    st.stop()

tab_matches, tab_analysis, tab_sim, tab_guide = st.tabs(
    ["📅 Partidos y cuotas", "🎯 Análisis conservador", "💶 Simulador", "📚 Guía de mercados"]
)

# ──────────────────────────────────────────────────────────────────────────────
# TAB 1 · PARTIDOS
# ──────────────────────────────────────────────────────────────────────────────
with tab_matches:
    markets_view = st.multiselect(
        "Mercados a mostrar", list(MARKET_LABELS), default=list(MARKET_LABELS),
        format_func=MARKET_LABELS.get, key="mk_view",
    )
    view = st.radio("Vista", ["Tarjetas", "Tabla"], horizontal=True)

    n_events = df["event_id"].nunique()
    c1, c2, c3 = st.columns(3)
    c1.metric("Partidos", n_events)
    c2.metric("Selecciones con cuota", len(df))
    c3.metric("Casas de apuestas", len(bookmakers_available) if bookmaker == BEST else 1)

    view_df = df[df["mkey"].isin(markets_view)]
    if view == "Tarjetas":
        for ev_id in view_df.drop_duplicates("event_id").sort_values("Inicio")["event_id"]:
            render_event_card(view_df[view_df["event_id"] == ev_id])
    else:
        table = view_df.sort_values(["Inicio", "Partido", "mkey", "orden"]).copy()
        table["Fecha"] = table["Inicio"].dt.strftime("%d/%m/%Y")
        table["Hora"] = table["Inicio"].dt.strftime("%H:%M")
        st.dataframe(
            table[["Fecha", "Hora", "Partido", "Mercado", "Selección", "Cuota", "Prob (%)", "Casa"]],
            width="stretch",
            hide_index=True,
            column_config={
                "Cuota": st.column_config.NumberColumn(format="%.2f"),
                "Prob (%)": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f%%"),
            },
        )

# ──────────────────────────────────────────────────────────────────────────────
# TAB 2 · ANÁLISIS CONSERVADOR
# ──────────────────────────────────────────────────────────────────────────────
with tab_analysis:
    st.subheader("Selecciones con mayor probabilidad estadística")
    st.caption(
        "Probabilidad implícita = 1 / cuota × 100. Las cuotas más bajas son las que el mercado "
        "considera más probables. **Una probabilidad alta no garantiza ganar ni que haya valor.**"
    )
    f1, f2, f3 = st.columns(3)
    min_odds, max_odds = f1.slider("Rango de cuotas", 1.01, 3.00, (1.10, 1.60), step=0.01)
    markets_an = f2.multiselect(
        "Mercados", list(MARKET_LABELS), default=list(MARKET_LABELS),
        format_func=MARKET_LABELS.get, key="mk_an",
    )
    top_n = f3.number_input("Nº de selecciones", 3, 50, 10)
    one_per_event = st.checkbox("Máximo una selección por partido", value=True)

    pool = (
        df[df["mkey"].isin(markets_an) & df["Cuota"].between(min_odds, max_odds)]
        .sort_values(["Prob (%)", "Inicio"], ascending=[False, True])
        .reset_index(drop=True)
    )
    ranking = pool.drop_duplicates("event_id") if one_per_event else pool
    ranking = ranking.head(int(top_n)).copy()

    if ranking.empty:
        st.warning("Ninguna selección cumple los filtros. Amplía el rango de cuotas.")
    else:
        show = ranking.copy()
        show.insert(0, "#", range(1, len(show) + 1))
        show["Fecha y hora"] = show["Inicio"].map(fmt_dt)
        st.dataframe(
            show[["#", "Fecha y hora", "Partido", "Mercado", "Selección", "Cuota",
                  "Prob (%)", "Prob sin margen (%)", "Casa"]],
            width="stretch",
            hide_index=True,
            column_config={
                "Cuota": st.column_config.NumberColumn(format="%.2f"),
                "Prob (%)": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f%%"),
                "Prob sin margen (%)": st.column_config.NumberColumn(
                    format="%.1f%%", help="Aproximación quitando el margen de la casa."),
            },
        )

        chart = pd.Series(
            ranking["Prob (%)"].values,
            index=[f"{i + 1}. {s}" for i, s in enumerate(ranking["Selección"])],
        )
        st.bar_chart(chart, horizontal=True)

        st.subheader("🧭 Paso a paso: dónde buscar cada selección")
        for i, (_, row) in enumerate(ranking.head(10).iterrows(), start=1):
            with st.expander(
                f"{i}. {row['Partido']} → {row['Selección']} @ {row['Cuota']:.2f} "
                f"({row['Prob (%)']:.1f}%)"
            ):
                st.markdown(steps_md(row))

# ──────────────────────────────────────────────────────────────────────────────
# TAB 3 · SIMULADOR
# ──────────────────────────────────────────────────────────────────────────────
with tab_sim:
    st.subheader("Simulador de apuesta baja")
    stake = st.number_input("Importe a apostar (€)", min_value=0.10, value=1.00, step=0.50, format="%.2f")

    if ranking.empty:
        st.info("Ajusta los filtros de la pestaña de análisis para tener selecciones que simular.")
    else:
        st.markdown("**Apuestas simples** (las del ranking)")
        sim = ranking[["Partido", "Selección", "Cuota", "Prob (%)"]].copy()
        sim["Retorno total"] = (stake * sim["Cuota"]).round(2)
        sim["Beneficio neto"] = (sim["Retorno total"] - stake).round(2)
        st.dataframe(
            sim, width="stretch", hide_index=True,
            column_config={
                "Cuota": st.column_config.NumberColumn(format="%.2f"),
                "Prob (%)": st.column_config.NumberColumn(format="%.1f%%"),
                "Retorno total": st.column_config.NumberColumn(format="%.2f €"),
                "Beneficio neto": st.column_config.NumberColumn(format="%.2f €"),
            },
        )

        st.markdown("**Apuesta combinada**")
        combo_pool = pool.copy()
        combo_pool["Etiqueta"] = combo_pool.apply(
            lambda r: f"{r['Partido']} — {r['Selección']} @ {r['Cuota']:.2f} [{MARKET_SHORT[r['mkey']]}]",
            axis=1,
        )
        combo_pool = combo_pool.drop_duplicates("Etiqueta").set_index("Etiqueta")
        default_labels = [
            lbl for lbl in
            combo_pool.reset_index().drop_duplicates("event_id")["Etiqueta"].head(3)
        ]
        chosen = st.multiselect("Elige las selecciones de tu combinada", list(combo_pool.index),
                                default=default_labels)

        if len(chosen) >= 2:
            picks = combo_pool.loc[chosen]
            if picks["event_id"].duplicated().any():
                st.warning("⚠️ Has elegido varias selecciones del mismo partido: las casas suelen "
                           "no permitirlo en una combinada.")
            combo_odds = float(picks["Cuota"].prod())
            combo_prob = float((picks["Prob (%)"] / 100).prod() * 100)
            ret = stake * combo_odds
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Cuota combinada", f"{combo_odds:.2f}")
            m2.metric("Prob. implícita", f"{combo_prob:.1f}%")
            m3.metric("Retorno total", eur(ret))
            m4.metric("Beneficio neto", eur(ret - stake))
            st.caption(f"Si fallas una sola selección pierdes los {eur(stake)} apostados. "
                       "La probabilidad combinada asume eventos independientes.")
        elif len(chosen) == 1:
            st.info("Elige al menos 2 selecciones para calcular una combinada.")

# ──────────────────────────────────────────────────────────────────────────────
# TAB 4 · GUÍA DE MERCADOS
# ──────────────────────────────────────────────────────────────────────────────
with tab_guide:
    st.subheader("Guía rápida de mercados")
    st.markdown("""
### 🏆 Ganador (1X2 / Moneyline)
- **1X2 (fútbol):** apuestas a **1** = gana el local, **X** = empate, **2** = gana el visitante (90 min + descuento).
- **Moneyline (NBA, MLB, tenis…):** apuestas a quién gana el partido. Normalmente no hay empate.

### 🛡️ Doble oportunidad (fútbol)
Cubres dos de los tres resultados: **1X** (local gana o empata), **X2** (visitante gana o empata) o **12** (no hay empate).
Las cuotas son más bajas porque es más probable, pero esta app no las muestra: búscalas en tu casa de apuestas.

### ⚖️ Hándicap / Spread
Se da una ventaja o desventaja ficticia a un equipo antes de empezar.
- **Real Madrid −1.5:** debe ganar por **2 o más** goles.
- **Rival +1.5:** gana la apuesta si empata, gana o pierde por **un solo** gol.

### 📈 Totales (Over / Under)
Apuestas a la suma total de goles, puntos o carreras.
- **Más de 2.5 goles (Over):** se necesitan 3 o más goles.
- **Menos de 2.5 goles (Under):** 0, 1 o 2 goles.

### 🧮 Cuota y probabilidad implícita
- **Retorno** = importe × cuota · **Beneficio neto** = retorno − importe.
- **Probabilidad implícita** = 1 / cuota × 100. Una cuota de 1.50 implica ≈ 66,7 %.
- Las casas incluyen un **margen**: la suma de probabilidades de un mercado supera el 100 %.
  Por eso la tabla muestra también la probabilidad *sin margen*.

### 🔗 Combinadas
Se multiplican las cuotas: más premio, pero **basta fallar una selección para perderlo todo**.

> **Ejemplo con 1 €:** cuota 1.50 → retorno 1,50 € y beneficio neto 0,50 €.
""")
    st.warning(
        "🔞 **Juego responsable:** las apuestas son solo para mayores de 18 años y siempre tienen riesgo. "
        "Esta app es informativa y no garantiza resultados. Apuesta solo lo que puedas permitirte perder; "
        "si sientes que pierdes el control, visita jugarbien.es."
    )

st.caption("Datos: The Odds API · Esta herramienta no es asesoramiento financiero ni de apuestas.")
