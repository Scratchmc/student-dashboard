import io
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

# -----------------------------
# 🔧 Instellingen
# -----------------------------
STUDENT_THRESHOLD_HOURS = 16  # minimum uren per week
TZ = ZoneInfo("Europe/Amsterdam")

st.set_page_config(page_title="Weekuren (Scratch)", layout="wide")
st.title("📊 Weekuren per student")
st.caption("Upload wekelijks je CSV. Elke upload voegt een nieuwe kolom toe met het weeknummer.")

# -----------------------------
# Helpers
# -----------------------------

def format_minutes_to_hhmm(total_minutes: float) -> str:
    if pd.isna(total_minutes):
        return ""
    total_minutes = int(round(total_minutes))
    h, m = divmod(total_minutes, 60)
    return f"{h}:{m:02d}"


def parse_datetime_series(series: pd.Series) -> pd.Series:
    """Probeert slim datums/tijden te parsen."""
    return pd.to_datetime(series, errors="coerce", dayfirst=False, utc=False)


def compute_durations(df: pd.DataFrame, name_col: str, start_col: str, end_col: str) -> pd.DataFrame:
    tmp = df[[name_col, start_col, end_col]].copy()
    tmp[start_col] = parse_datetime_series(tmp[start_col])
    tmp[end_col] = parse_datetime_series(tmp[end_col])

    # Geldige rijen: beide tijden aanwezig en end > start
    valid = tmp[start_col].notna() & tmp[end_col].notna() & (tmp[end_col] > tmp[start_col])
    tmp = tmp[valid]

    # Duur in minuten
    minutes = (tmp[end_col] - tmp[start_col]).dt.total_seconds() / 60.0
    tmp["_minutes"] = minutes

    # Som per student
    per_student = tmp.groupby(name_col, dropna=False)["_minutes"].sum().to_frame(name="minutes")
    per_student.index.name = "Naam"
    per_student.reset_index(inplace=True)
    return per_student


def color_threshold(val):
    if val == "":
        return ""
    # val komt als string H:MM; reken terug naar minuten
    try:
        h, m = val.split(":")
        total_minutes = int(h) * 60 + int(m)
    except Exception:
        return ""
    if total_minutes >= STUDENT_THRESHOLD_HOURS * 60:
        return "background-color: #e8f5e9; color: #1b5e20; font-weight: 600;"  # groen
    else:
        return "background-color: #ffebee; color: #b71c1c; font-weight: 600;"  # rood


# -----------------------------
# Sessiestate voor cumulatieve tabel
# -----------------------------
if "cumulative" not in st.session_state:
    st.session_state.cumulative = pd.DataFrame(columns=["Naam"])  # lege tabel

# Opties: resetten of downloaden
with st.sidebar:
    st.header("Opties")
    if st.button("🔄 Reset tabel", type="secondary"):
        st.session_state.cumulative = pd.DataFrame(columns=["Naam"])  # leegmaken
        st.success("Cumulatieve tabel is gereset.")

    if not st.session_state.cumulative.empty and "Naam" in st.session_state.cumulative.columns:
        csv_bytes = st.session_state.cumulative.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="💾 Download cumulatieve CSV",
            data=csv_bytes,
            file_name="weekuren_cumulatief.csv",
            mime="text/csv",
        )

st.divider()

# -----------------------------
# Upload & kolommen kiezen
# -----------------------------
uploaded = st.file_uploader("Upload wekelijkse CSV", type=["csv"]) 

if uploaded is not None:
    try:
        raw = uploaded.read()
        df = pd.read_csv(io.BytesIO(raw))
    except Exception:
        # Soms helpt het om ; als separator te gebruiken
        uploaded.seek(0)
        df = pd.read_csv(uploaded, sep=";")

    st.subheader("1) Controleer kolommen")
    st.dataframe(df.head(20), use_container_width=True)

    cols = df.columns.tolist()
    name_col = st.selectbox("Kolom met naam student", options=cols)

    # Probeer slimme default voor tijdkolommen
    default_start = next((c for c in cols if c.lower().strip() in [
        "check in time", "check-in time", "check in", "start", "start time", "checkin time"
    ]), None)
    default_end = next((c for c in cols if c.lower().strip() in [
        "check out time", "check-out time", "check out", "einde", "end", "end time", "checkout time"
    ]), None)

    start_col = st.selectbox("Starttijd-kolom (check-in)", options=cols, index=cols.index(default_start) if default_start in cols else 0)
    end_col = st.selectbox("Eindtijd-kolom (check-out)", options=cols, index=cols.index(default_end) if default_end in cols else 0)

    st.subheader("2) Bereken weekuren")
    per_student = compute_durations(df, name_col, start_col, end_col)

    # Format naar H:MM en ook ruwe minuten bewaren voor sorteren
    per_student["Uren (min)"] = per_student["minutes"].fillna(0)
    per_student["Uren"] = per_student["Uren (min)"].apply(format_minutes_to_hhmm)
    per_student.rename(columns={name_col: "Naam"}, inplace=True)

    # Kolomlabel op basis van uploadmoment (weeknummer NL)
    now = datetime.now(TZ)
    iso_year, iso_week, _ = now.isocalendar()
    week_label = f"W{iso_week:02d}-{iso_year}"

    # Merge in cumulatieve tabel
    cum = st.session_state.cumulative.copy()
    # Zorg dat 'Naam' kolom er is
    if "Naam" not in cum.columns:
        cum["Naam"] = []

    # Maak tabel met alleen Naam en nieuwe weekkolom (als H:MM string)
    new_week_df = per_student[["Naam", "Uren"]].copy()
    new_week_df.rename(columns={"Uren": week_label}, inplace=True)

    # Outer join op naam
    if cum.empty or list(cum.columns) == ["Naam"]:
        merged = new_week_df
    else:
        merged = pd.merge(cum, new_week_df, on="Naam", how="outer")

    # Sorteer namen alfabetisch
    merged.sort_values("Naam", inplace=True, kind="stable")
    merged.reset_index(drop=True, inplace=True)

    # Bewaar in sessie
    st.session_state.cumulative = merged

    st.success(f"Kolom voor {week_label} toegevoegd.")

# -----------------------------
# Weergave met kleuren per weekkolom
# -----------------------------
if not st.session_state.cumulative.empty:
    st.subheader("3) Overzicht (per week)")

    def style_df(df_in: pd.DataFrame):
        # Bepaal welke kolommen weekkolommen zijn (Wnn-JJJJ)
        week_cols = [c for c in df_in.columns if isinstance(c, str) and c.startswith("W") and "-" in c]
        styler = df_in.style
        for c in week_cols:
            styler = styler.applymap(color_threshold, subset=pd.IndexSlice[:, [c]])
        return styler

    styled = style_df(st.session_state.cumulative.copy())
    st.dataframe(styled, use_container_width=True, height=520)

    st.caption(
        f"Groen = ≥ {STUDENT_THRESHOLD_HOURS} uur, Rood = minder dan {STUDENT_THRESHOLD_HOURS} uur."
    )

else:
    st.info("Nog geen data. Upload een CSV om te starten.")
