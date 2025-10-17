import io
import os
import tempfile
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

# ---------------------------------
# 🔧 Instellingen
# ---------------------------------
STUDENT_THRESHOLD_HOURS = 16  # minimum uren per week voor groen
TZ = ZoneInfo("Europe/Amsterdam")

st.set_page_config(page_title="Weekuren (Scratch)", layout="wide")
st.title("📊 Weekuren per student")
st.caption(
    "Upload wekelijks je CSV/Excel. Namen in kolom B. In-/uitcheckparen uit vaste kolommen: "
    "M–O, Q–S, U–W, Y–AA, AC–AE. Elke upload voegt een weekkolom toe."
)

# ---------------------------------
# Permanente opslag
# ---------------------------------
DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATA_FILE = DATA_DIR / "weekuren_cumulatief.csv"
REQUIRED_BASE_COLS = ["Naam", "Coach"]

# Kolomparen (0-based indexen) voor in-/uitchecks
# A=0, B=1, ..., M=12, O=14, Q=16, S=18, U=20, W=22, Y=24, AA=26, AC=28, AE=30
CHECK_PAIRS = [
    (12, 14),  # M & O
    (16, 18),  # Q & S
    (20, 22),  # U & W
    (24, 26),  # Y & AA
    (28, 30),  # AC & AE
]

# ---------------------------------
# Helpers
# ---------------------------------

def hhmm_from_minutes(total_minutes: float) -> str:
    if pd.isna(total_minutes):
        return ""
    total_minutes = int(round(float(total_minutes)))
    h, m = divmod(total_minutes, 60)
    return f"{h}:{m:02d}"


def color_threshold(val: str):
    """Kleurfunctie voor weekkolommen op basis van H:MM string."""
    if not isinstance(val, str) or val == "":
        return ""
    try:
        h, m = val.split(":")
        total_minutes = int(h) * 60 + int(m)
    except Exception:
        return ""
    if total_minutes >= STUDENT_THRESHOLD_HOURS * 60:
        return "background-color: #e8f5e9; color: #1b5e20; font-weight: 600;"  # groen
    else:
        return "background-color: #ffebee; color: #b71c1c; font-weight: 600;"  # rood


def read_uploaded_to_df(file) -> pd.DataFrame | None:
    """Leest CSV of Excel (1 tab) in een DataFrame.
    - Excel: eerste sheet automatisch.
    - CSV: probeert ',', daarna ';', met en zonder latin-1 encoding.
    """
    if file is None:
        return None
    name = getattr(file, "name", "uploaded")
    lower = str(name).lower()

    if lower.endswith((".xlsx", ".xls")):
        try:
            return pd.read_excel(file, sheet_name=0, header=0)
        except Exception as e:
            st.error(f"Kan Excel niet openen: {e}")
            return None
    else:
        raw = file.read()
        for kwargs in ({}, {"sep": ";"}, {"encoding": "latin-1"}, {"sep": ";", "encoding": "latin-1"}):
            try:
                return pd.read_csv(io.BytesIO(raw), **kwargs)
            except Exception:
                continue
        st.error("CSV kon niet gelezen worden met bekende instellingen.")
        return None


# ---------------------------------
# Init sessiestate (lees permanente opslag in)
# ---------------------------------
if "cumulative" not in st.session_state:
    if DATA_FILE.exists():
        try:
            cum = pd.read_csv(DATA_FILE)
        except Exception:
            cum = pd.DataFrame(columns=REQUIRED_BASE_COLS)
    else:
        cum = pd.DataFrame(columns=REQUIRED_BASE_COLS)
    # Verplicht: Naam + Coach
    for col in REQUIRED_BASE_COLS:
        if col not in cum.columns:
            cum[col] = ""
    other_cols = [c for c in cum.columns if c not in REQUIRED_BASE_COLS]
    cum = cum[REQUIRED_BASE_COLS + other_cols]
    st.session_state.cumulative = cum

# ---------------------------------
# Sidebar (filter, reset, download)
# ---------------------------------
with st.sidebar:
    st.header("Opties")
    st.caption(f"Opslagpad: `{DATA_FILE}`")

    # Coach-filter
    cum_for_filter = st.session_state.cumulative.copy()
    coach_options = sorted([
        c for c in cum_for_filter.get("Coach", pd.Series([])).dropna().unique().tolist()
        if str(c).strip() != ""
    ])
    selected_coaches = st.multiselect("Filter op coach", options=coach_options, default=[])
    st.session_state["_coach_filter"] = selected_coaches

    if st.button("🔄 Reset tabel", type="secondary"):
        st.session_state.cumulative = pd.DataFrame(columns=REQUIRED_BASE_COLS)
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

st.divider()

# ---------------------------------
# Upload & verwerken (direct, geen inspectiestap)
# ---------------------------------
uploaded = st.file_uploader(
    "Upload wekelijkse CSV of Excel (1 tabblad; Namen in B, paren: M–O, Q–S, U–W, Y–AA, AC–AE)",
    type=["csv", "xlsx", "xls"],
)

df = read_uploaded_to_df(uploaded)

if df is not None:
    # --- Extractie op basis van vaste posities ---
    # B = index 1; M/O/Q/S/U/W/Y/AA/AC/AE = 12/14/16/18/20/22/24/26/28/30
    if df.shape[1] < 31:
        st.error(
            "Het bestand heeft minder dan 31 kolommen. Verwacht: Naam in B en in-/uitcheckparen M–O, Q–S, U–W, Y–AA, AC–AE."
        )
    else:
        name_series = df.iloc[:, 1].astype(str).str.strip()

        # Bereken minuten uit de gedefinieerde paren
        pair_minutes = []
        for (c_in, c_out) in CHECK_PAIRS:
            # beveiliging als column out of range is
            if c_in >= df.shape[1] or c_out >= df.shape[1]:
                # maak een nul-serie met juiste index
                zero_series = pd.Series(0.0, index=df.index)
                pair_minutes.append(zero_series)
                continue
            in_s = pd.to_datetime(df.iloc[:, c_in], errors="coerce")
            out_s = pd.to_datetime(df.iloc[:, c_out], errors="coerce")
            delta = (out_s - in_s).dt.total_seconds() / 60.0
            # alleen tellen als beide geldig en out > in; anders 0
            delta = delta.mask(in_s.isna() | out_s.isna() | (delta < 0), 0.0)
            pair_minutes.append(delta.fillna(0.0))

        if pair_minutes:
            minutes_sum = pd.concat(pair_minutes, axis=1).sum(axis=1)
        else:
            minutes_sum = pd.Series(0.0, index=df.index)

        per_student = pd.DataFrame({
            "Naam": name_series,
            "minutes": minutes_sum
        })
        # Filter lege/NA namen
        per_student = per_student[per_student["Naam"].notna() & (per_student["Naam"].str.len() > 0)]

        per_student["Uren (min)"] = per_student["minutes"].fillna(0)
        per_student["Uren"] = per_student["Uren (min)"].apply(hhmm_from_minutes)

        # Weeklabel o.b.v. uploadmoment
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

        # Outer join op Naam, behoud bestaande Coach
        if cum.empty or list(cum.columns) == ["Naam", "Coach"]:
            merged = pd.merge(new_week_df, cum[["Naam", "Coach"]], on="Naam", how="left")
        else:
            merged = pd.merge(cum, new_week_df, on="Naam", how="outer")

        # Kolomvolgorde: Naam, Coach, daarna weekkolommen
        wk_cols = [c for c in merged.columns if c not in ["Naam", "Coach"]]
        merged = merged[["Naam", "Coach"] + wk_cols]

        merged.sort_values("Naam", inplace=True, kind="stable")
        merged.reset_index(drop=True, inplace=True)

        st.session_state.cumulative = merged

        # Persist (atomair)
        try:
            with tempfile.NamedTemporaryFile("w", delete=False, dir=str(DATA_DIR), suffix=".csv") as tmp:
                merged.to_csv(tmp.name, index=False)
                tmp_name = tmp.name
            os.replace(tmp_name, DATA_FILE)
        except Exception as e:
            st.warning(f"Kon niet naar bestand schrijven: {e}")

        st.success(f"Kolom voor {week_label} toegevoegd en opgeslagen.")

# ---------------------------------
# Weergave + styling + coach-editor
# ---------------------------------
if not st.session_state.cumulative.empty:
    st.subheader("1) Overzicht (per week)")

    def style_df(df_in: pd.DataFrame):
        week_cols = [c for c in df_in.columns if isinstance(c, str) and c.startswith("W") and "-" in c]
        styler = df_in.style
        for c in week_cols:
            styler = styler.applymap(color_threshold, subset=pd.IndexSlice[:, [c]])
        return styler

    df_show = st.session_state.cumulative.copy()

    # Filter op coach indien gekozen
    selected = st.session_state.get("_coach_filter", [])
    if selected:
        df_show = df_show[df_show["Coach"].isin(selected)]

    # Kolomvolgorde borgen
    fixed_cols = ["Naam", "Coach"]
    other_cols = [c for c in df_show.columns if c not in fixed_cols]
    df_show = df_show[fixed_cols + other_cols]

    styled = style_df(df_show.copy())
    st.dataframe(styled, use_container_width=True, height=520)

    st.caption(f"Groen = ≥ {STUDENT_THRESHOLD_HOURS} uur, Rood = minder dan {STUDENT_THRESHOLD_HOURS} uur.")

    # --- Coach-editor ---
    with st.expander("Coach toewijzen/bewerken"):
        edit_df = st.data_editor(
            st.session_state.cumulative[["Naam", "Coach"]].copy().sort_values("Naam"),
            num_rows="dynamic",
            use_container_width=True,
            key="coach_editor",
        )
        if isinstance(edit_df, pd.DataFrame):
            base = st.session_state.cumulative.copy()
            base = base.drop(columns=["Coach"], errors="ignore").merge(edit_df, on="Naam", how="left")
            wk_cols = [c for c in base.columns if c not in ["Naam", "Coach"]]
            base = base[["Naam", "Coach"] + wk_cols]

            if not base.equals(st.session_state.cumulative):
                st.session_state.cumulative = base
                try:
                    with tempfile.NamedTemporaryFile("w", delete=False, dir=str(DATA_DIR), suffix=".csv") as tmp:
                        base.to_csv(tmp.name, index=False)
                        tmp_name = tmp.name
                    os.replace(tmp_name, DATA_FILE)
                except Exception as e:
                    st.warning(f"Kon wijzigingen niet opslaan: {e}")
                st.success("Coach-gegevens bijgewerkt en opgeslagen.")

    # --- PDF export ---
    with st.expander("📄 PDF export"):
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet

        pdf_file = DATA_DIR / "weekuren_export.pdf"
        df_export = df_show.fillna("")
        data = [df_export.columns.tolist()] + df_export.values.tolist()

        doc = SimpleDocTemplate(str(pdf_file), pagesize=landscape(A4))
        table = Table(data, repeatRows=1)
        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e0e0e0')),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
            ('FONT', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ])
        table.setStyle(style)
        story = [Paragraph("Weekuren-overzicht", getSampleStyleSheet()['Heading2']), table]
        doc.build(story)

        with open(pdf_file, 'rb') as f:
            pdf_bytes = f.read()

        st.download_button(
            label="📥 Download PDF-overzicht",
            data=pdf_bytes,
            file_name="weekuren_overzicht.pdf",
            mime="application/pdf",
        )
else:
    st.info("Nog geen data. Upload een CSV of Excel om te starten.")
