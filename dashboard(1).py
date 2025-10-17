
import streamlit as st
import pandas as pd
from datetime import datetime

# Upload Excel-bestand
uploaded_file = st.file_uploader("Upload OneTap Excel-export", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file, engine="openpyxl")

    # Identificeer check-in en check-out kolommen
    checkin_cols = [col for col in df.columns if 'Check In Time' in col]
    checkout_cols = [col for col in df.columns if 'Check Out Time' in col]

    # Bereken totale minuten per student
    def calculate_minutes(row):
        total_minutes = 0
        for in_col, out_col in zip(checkin_cols, checkout_cols):
            check_in = row[in_col]
            check_out = row[out_col]
            try:
                if pd.notna(check_in) and pd.notna(check_out):
                    in_time = datetime.strptime(str(check_in), "%I:%M%p")
                    out_time = datetime.strptime(str(check_out), "%I:%M%p")
                    duration = (out_time - in_time).total_seconds() / 60
                    if duration > 0:
                        total_minutes += duration
            except:
                continue
        return total_minutes

    df['Total Minutes'] = df.apply(calculate_minutes, axis=1)
    df['Totaal uur deze week'] = df['Total Minutes'] / 60
    df['Verschil met 16 uur (minuten)'] = df['Total Minutes'] - (16 * 60)

    dashboard = df[['Name', 'Totaal uur deze week', 'Verschil met 16 uur (minuten)', 'Total Minutes']].copy()
    dashboard.rename(columns={'Total Minutes': 'Totaal minuten alle weken'}, inplace=True)

    st.title("Student Aanwezigheid Dashboard")
    st.write("Overzicht van aanwezigheid per student:")
    st.dataframe(dashboard)
