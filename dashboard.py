import io
import os
import tempfile
from pathlib import Path
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
# Sessiestate voor cumulatieve tabel + permanente opslag
# -----------------------------
DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATA_FILE = DATA_DIR / "weekuren_cumulatief.csv"

REQUIRED_BASE_COLS = ["Naam", "Coach"]

if "cumulative" not in st.session_state:
    # Probeer bestaande opslag in te lezen
    if DATA_FILE.exists():
        try:
            cum = pd.read_csv(DATA_FILE)
        except Exception:
            cum = pd.DataFrame(columns=REQUIRED_BASE_COLS)
    else:
        cum = pd.DataFrame(columns=REQUIRED_BASE_COLS)

    # Zorg dat verplichte kolommen bestaan en op juiste plek staan
    for col in REQUIRED_BASE_COLS:
        if col not in cum.columns:
            cum[col] = ""
    # Kolomvolgorde: Naam, Coach, daarna de rest
    other_cols = [c for c in cum.columns if c not in REQUIRED_BASE_COLS]
    cum = cum[REQUIRED_BASE_COLS + other_cols]

    st.session_state.cumulative = cum

# Opties: resetten of downloaden
with st.sidebar:
    st.header("Opties")
    st.caption(f"Opslagpad: `{DATA_FILE}`")

    # Coach-filter
    cum_for_filter = st.session_state.cumulative.copy()
    coach_options = sorted([c for c in cum_for_filter.get("Coach", pd.Series([])).dropna().unique().tolist() if str(c).strip() != ""])
    selected_coaches = st.multiselect("Filter op coach", options=coach_options, default=[])
    st.session_state["_coach_filter"] = selected_coaches

    if st.button("🔄 Reset tabel", type="secondary"):
        st.session_state.cumulative = pd.DataFrame(columns=REQUIRED_BASE_COLS)  # leegmaken
        # Verwijder bestand indien aanwezig
        try:
            if DATA_FILE.exists():
                DATA_FILE.unlink()
        except Exception:
            pass
        st.success("Cumulatieve tabel is gereset (geheugen + bestand).")

    if not st.session_state.cumulative.empty and "Naam" in st.session_state.cumulative.columns:
        csv_bytes = st.session_state.cumulative.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="💾 Download cumulatieve CSV",
            data=csv_bytes,
            file_name="weekuren_cumulatief.csv",
            mime="text/csv",
        )
            label="💾 Download cumulatieve CSV",
            data=csv_bytes,
            file_name="weekuren_cumulatief.csv",
            mime="text/csv",
        )

st.divider()

# -----------------------------
# Upload & kolommen kiezen
# -----------------------------

def read_uploaded_to_df(file) -> pd.DataFrame | None:
    if file is None:
        return None
    name = getattr(file, "name", "uploaded")
    lower = name.lower()

    # Excel-bestand: altijd 1 tabblad -> direct inlezen
    if lower.endswith(".xlsx") or lower.endswith(".xls"):
        try:
            return pd.read_excel(file, sheet_name=0, header=0)
        except Exception as e:
            st.error(f"Kan Excel niet openen: {e}")
            return None

    # CSV-bestand
    else:
        raw = file.read()
        for kwargs in ({}, {"sep": ";"}, {"encoding": "latin-1"}, {"sep": ";", "encoding": "latin-1"}):
            try:
                return pd.read_csv(io.BytesIO(raw), **kwargs)
            except Exception:
                continue
        st.error("CSV kon niet gelezen worden met bekende instellingen.")
        return None


def hhmm_from_minutes(total_minutes: float) -> str:
    if pd.isna(total_minutes):
        return ""
    total_minutes = int(round(total_minutes))
    h, m = divmod(total_minutes, 60)
    return f"{h}:{m:02d}"


def cell_to_minutes(v) -> float:
    """Converteert diverse formaten (timedelta, 'H:MM', 'HH:MM', float uren) naar minuten."""
    if pd.isna(v):
        return 0.0
    # timedelta
    if hasattr(v, 'components') or isinstance(v, pd.Timedelta):
        try:
            return float(pd.to_timedelta(v).total_seconds() / 60.0)
        except Exception:
            pass
    # strings zoals '1:30' of '01:30'
    if isinstance(v, str):
        s = v.strip()
        if ":" in s:
            try:
                parts = s.split(":")
                if len(parts) >= 2:
                    h = int(parts[0])
                    m = int(parts[1][:2])
                    return float(h * 60 + m)
            except Exception:
                pass
        # Komma als decimaal -> vervang door punt
        s2 = s.replace(",", ".")
        try:
            # interpreteer als uren
            hrs = float(s2)
            return hrs * 60.0
        except Exception:
            return 0.0
    # numeriek: interpreteer als uren
    try:
        return float(v) * 60.0
    except Exception:
        return 0.0


uploaded = st.file_uploader("Upload wekelijkse CSV of Excel (1 tabblad)", type=["csv", "xlsx", "xls"]) 

df = read_uploaded_to_df(uploaded)

if df is not None:
    st.subheader("1) Controleer data (B + L:AE)")
    st.dataframe(df.head(20), use_container_width=True)

    # ---- Bepaal naam en uren op basis van kolomposities ----
    # Kolom B = index 1 (0-based)
    # Kolommen L t/m AE = index 11 t/m 30 (inclusief)
    if df.shape[1] < 31:
        st.error("Het bestand heeft minder dan 31 kolommen. Verwacht: Namen in kolom B en uren in kolommen L t/m AE.")
    else:
        name_series = df.iloc[:, 1].astype(str).str.strip()
        hours_block = df.iloc[:, 11:31]  # L..AE

        # Converteer alle cellen naar minuten en sommeer
        minutes_sum = hours_block.applymap(cell_to_minutes).sum(axis=1)

        # Bouw per-student tabel
        per_student = pd.DataFrame({
            "Naam": name_series,
            "minutes": minutes_sum
        })
        # Filter lege namen
        per_student = per_student[per_student["Naam"].notna() & (per_student["Naam"].str.len() > 0)]

        # Format naar H:MM
        per_student["Uren (min)"] = per_student["minutes"].fillna(0)
        per_student["Uren"] = per_student["Uren (min)"].apply(hhmm_from_minutes)

        # Kolomlabel o.b.v. uploadmoment
        now = datetime.now(TZ)
        iso_year, iso_week, _ = now.isocalendar()
        week_label = f"W{iso_week:02d}-{iso_year}"

        # Merge in cumulatieve tabel
        cum = st.session_state.cumulative.copy()
        for col in REQUIRED_BASE_COLS:
            if col not in cum.columns:
                cum[col] = ""

        new_week_df = per_student[["Naam", "Uren"]].copy()
        new_week_df.rename(columns={"Uren": week_label}, inplace=True)

        # Outer join op Naam, behoud Coach uit bestaande cum
        if cum.empty or list(cum.columns) == ["Naam", "Coach"]:
            merged = pd.merge(new_week_df, cum[["Naam", "Coach"]], on="Naam", how="left")
        else:
            merged = pd.merge(cum, new_week_df, on="Naam", how="outer")

        # Zorg voor kolomvolgorde: Naam, Coach, daarna bestaande weekkolommen + nieuwe
        wk_cols = [c for c in merged.columns if c not in ["Naam", "Coach"]]
        merged = merged[["Naam", "Coach"] + wk_cols]

        merged.sort_values("Naam", inplace=True, kind="stable")
        merged.reset_index(drop=True, inplace=True)

                st.session_state.cumulative = merged

        # -- Permanente opslag (atomair schrijven)
        try:
            with tempfile.NamedTemporaryFile("w", delete=False, dir=str(DATA_DIR), suffix=".csv") as tmp:
                merged.to_csv(tmp.name, index=False)
                tmp_name = tmp.name
            os.replace(tmp_name, DATA_FILE)
        except Exception as e:
            st.warning(f"Kon niet naar bestand schrijven: {e}")

        st.success(f"Kolom voor {week_label} toegevoegd en opgeslagen.")

# -----------------------------
# Weergave met kleuren per weekkolom + Coach bewerken
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

    # Filter op coach indien gekozen
    df_show = st.session_state.cumulative.copy()
    selected = st.session_state.get("_coach_filter", [])
    if selected:
        df_show = df_show[df_show["Coach"].isin(selected)]

    # Zorg voor kolomvolgorde: Naam, Coach, rest
    fixed_cols = ["Naam", "Coach"]
    other_cols = [c for c in df_show.columns if c not in fixed_cols]
    df_show = df_show[fixed_cols + other_cols]

    styled = style_df(df_show.copy())
    st.dataframe(styled, use_container_width=True, height=520)

    st.caption(
        f"Groen = ≥ {STUDENT_THRESHOLD_HOURS} uur, Rood = minder dan {STUDENT_THRESHOLD_HOURS} uur."
    )

    # ---- Coach-editor ----
    with st.expander("Coach toewijzen/bewerken"):
        edit_df = st.data_editor(
            st.session_state.cumulative[["Naam", "Coach"]].copy().sort_values("Naam"),
            num_rows="dynamic",
            use_container_width=True,
            key="coach_editor",
        )
        # Merge terug op Naam
        if isinstance(edit_df, pd.DataFrame):
            base = st.session_state.cumulative.copy()
            base = base.drop(columns=["Coach"], errors="ignore").merge(
                edit_df, on="Naam", how="left"
            )
            # Zorg voor kolomvolgorde
            wk_cols = [c for c in base.columns if c not in ["Naam", "Coach"]]
            base = base[["Naam", "Coach"] + wk_cols]

            # Sla alleen op en update als er wijzigingen zijn
            if not base.equals(st.session_state.cumulative):
                st.session_state.cumulative = base
                # persist
                try:
                    with tempfile.NamedTemporaryFile("w", delete=False, dir=str(DATA_DIR), suffix=".csv") as tmp:
                        base.to_csv(tmp.name, index=False)
                        tmp_name = tmp.name
                    os.replace(tmp_name, DATA_FILE)
                except Exception as e:
                    st.warning(f"Kon wijzigingen niet opslaan: {e}")
                st.success("Coach-gegevens bijgewerkt en opgeslagen.")
else:
    st.info("Nog geen data. Upload een CSV of Excel om te starten.")
