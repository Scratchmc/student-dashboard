
# 📊 Student Aanwezigheid Dashboard

Dit project bevat een Streamlit-dashboard dat automatisch studentaanwezigheid visualiseert op basis van wekelijkse Excel-exporten uit het programma OneTap.

---

## 🚀 Functionaliteit
- Upload eenvoudig je wekelijkse Excel-bestand
- Dashboard toont per student:
  - Naam
  - Totaal aantal uur aanwezig deze week
  - Verschil in minuten t.o.v. 16 uur
  - Totaal aantal minuten aanwezig over alle weken

---

## 🛠️ Installatie
1. Zorg dat Python geïnstalleerd is
2. Installeer Streamlit:
```bash
pip install streamlit
```

---

## ▶️ Gebruik
1. Clone deze repository:
```bash
git clone https://github.com/jouwgebruikersnaam/student-dashboard.git
cd student-dashboard
```

2. Start het dashboard:
```bash
streamlit run dashboard.py
```

3. Upload je Excel-bestand via de interface

---

## 📁 Bestandseisen
- Bestand moet een Excel `.xlsx` zijn
- Moet kolommen bevatten met "Check In Time" en "Check Out Time"
- Naam van student moet in kolom "Name" staan

---

## 🌐 Online publiceren
Je kunt dit dashboard ook hosten via [Streamlit Cloud](https://streamlit.io/cloud):
1. Maak een GitHub-repository met dit project
2. Koppel deze aan Streamlit Cloud
3. Kies `dashboard.py` als hoofdbestand

---

## 📄 Licentie
MIT License
