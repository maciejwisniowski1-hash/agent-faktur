import streamlit as st
import pandas as pd
from pypdf import PdfReader
from difflib import SequenceMatcher
import re
from io import BytesIO

st.set_page_config(
    page_title="Agent Faktur T2",
    layout="wide"
)

TOLERANCJA_KWOTY = 0.02


def normalize(text):
    text = str(text).upper()
    text = re.sub(r"[^A-Z0-9 ]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def similarity(a, b):
    return SequenceMatcher(
        None,
        normalize(a),
        normalize(b)
    ).ratio()


def normalize_invoice_number(text):
    text = str(text).upper()

    for p in ["FAKTURA", "FV", "FS", "FA", "FK", "KOR"]:
        text = text.replace(p, "")

    return re.sub(
        r"[^A-Z0-9]",
        "",
        text
    )


def invoice_score(invoice_number, description):

    inv = normalize_invoice_number(
        invoice_number
    )

    desc = normalize_invoice_number(
        description
    )

    if not inv:
        return 0

    if inv in desc:
        return 100

    score = SequenceMatcher(
        None,
        inv,
        desc
    ).ratio()

    if score >= 0.95:
        return 90

    if score >= 0.85:
        return 70

    if score >= 0.70:
        return 40

    return 0


def score_payment(
    numer,
    nip,
    kontrahent,
    kwota_faktury,
    opis,
    kwota
):

    score = invoice_score(
        numer,
        opis
    )

    clean_nip = re.sub(
        r"\D",
        "",
        str(nip)
    )

    if clean_nip and clean_nip in opis:
        score += 50

    sim = similarity(
        kontrahent,
        opis
    )

    if sim >= 0.60:
        score += 30

    elif sim >= 0.45:
        score += 15

    if abs(
        kwota - kwota_faktury
    ) <= TOLERANCJA_KWOTY:

        score += 20

    ratio = abs(
        kwota - kwota_faktury
    ) / max(
        kwota_faktury,
        1
    )

    if ratio > 0.50:
        score -= 100

    return score


def status_platnosci(
    suma,
    kwota
):

    diff = round(
        suma - kwota,
        2
    )

    if suma == 0:
        return "BRAK PŁATNOŚCI"

    if abs(diff) <= 0.01:
        return "OPŁACONA"

    if suma < kwota:
        return "CZĘŚCIOWO OPŁACONA"

    return "NADPŁATA"


st.title("📊 Agent Faktur T2")

st.write(
    "Wgraj plik Excel z fakturami oraz wyciąg PDF."
)

faktury_file = st.file_uploader(
    "Faktury Excel",
    type=["xlsx"]
)

wyciag_file = st.file_uploader(
    "Wyciąg PDF",
    type=["pdf"]
)

if st.button("🔍 ANALIZUJ"):

    if not faktury_file or not wyciag_file:

        st.error(
            "Wgraj oba pliki."
        )

    else:

        faktury = pd.read_excel(
            faktury_file
        )

        reader = PdfReader(
            wyciag_file
        )

        tekst_pdf = ""

        for page in reader.pages:

            page_text = page.extract_text()

            if page_text:
                tekst_pdf += page_text + "\n"

        platnosci = []

        for line in tekst_pdf.split("\n"):

            amounts = re.findall(
                r"(\d{1,3}(?:\.\d{3})*,\d{2})",
                line
            )

            if not amounts:
                continue

            try:

                kwota = float(
                    amounts[-1]
                    .replace(".", "")
                    .replace(",", ".")
                )

                platnosci.append({
                    "opis": line.upper(),
                    "kwota": kwota
                })

            except:
                pass

        wyniki = []

        for _, row in faktury.iterrows():

            numer = str(
                row["Numer dokumentu"]
            )

            kontr = str(
                row["Kontrahent"]
            )

            nip = str(
                row["NIP"]
            )

            kwf = float(
                row["Brutto"]
            )

            najlepsza_kwota = 0
            najlepszy_score = 0

            for p in platnosci:

                score = score_payment(
                    numer,
                    nip,
                    kontr,
                    kwf,
                    p["opis"],
                    p["kwota"]
                )

                kwota_ratio = min(
                    kwf,
                    p["kwota"]
                ) / max(
                    kwf,
                    p["kwota"]
                )

                if (
                    score > najlepszy_score
                    and kwota_ratio >= 0.50
                ):

                    najlepszy_score = score
                    najlepsza_kwota = p["kwota"]

            suma = round(
                najlepsza_kwota,
                2
            )

            wyniki.append({
                "Numer dokumentu": numer,
                "Kontrahent": kontr,
                "NIP": nip,
                "Kwota faktury": kwf,
                "Zapłacono": suma,
                "Różnica": round(
                    suma - kwf,
                    2
                ),
                "Status": status_platnosci(
                    suma,
                    kwf
                )
            })

        raport = pd.DataFrame(
            wyniki
        )

        st.dataframe(
            raport,
            use_container_width=True
        )

        output = BytesIO()

        with pd.ExcelWriter(
            output,
            engine="openpyxl"
        ) as writer:

            raport.to_excel(
                writer,
                sheet_name="Wszystkie",
                index=False
            )

        output.seek(0)

        st.download_button(
            "📥 Pobierz raport",
            data=output,
            file_name="raport_faktur.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
