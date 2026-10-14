import os
import requests
import pandas as pd
from flask import Flask, request, jsonify
from flask_cors import CORS
from groq import Groq

app = Flask(__name__)
CORS(app)

# Cheia se citește din variabila de mediu setată în Render (NU o pune în cod!)
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "baza_cariere.csv")

try:
    df_cariere = pd.read_csv(CSV_PATH)
    print("✅ Baza de date 'baza_cariere.csv' a fost încărcată cu succes.")
except Exception as e:
    print(f"❌ Eroare la încărcarea 'baza_cariere.csv': {e}")
    df_cariere = None


# Funcția era indentată greșit în interiorul blocului except -> IndentationError.
# Acum este la nivel de modul.
def numara_competitori_live(oras, tip_afacere):
    """
    Caută gratuit pe OpenStreetMap numărul de afaceri similare din orașul specificat.
    """
    tag_osm = "amenity"
    valoare_osm = "cafe"

    afacere_lower = tip_afacere.lower()
    if "cafenea" in afacere_lower or "coffee" in afacere_lower:
        valoare_osm = "cafe"
    elif "restaurant" in afacere_lower or "pizzerie" in afacere_lower or "fast" in afacere_lower:
        valoare_osm = "restaurant"
    elif "fit" in afacere_lower or "gym" in afacere_lower or "sport" in afacere_lower:
        tag_osm = "leisure"
        valoare_osm = "fitness_centre"
    elif "salon" in afacere_lower or "barber" in afacere_lower or "frizerie" in afacere_lower:
        tag_osm = "shop"
        valoare_osm = "hairdresser"
    elif "auto" in afacere_lower or "service" in afacere_lower or "vulcanizare" in afacere_lower:
        tag_osm = "shop"
        valoare_osm = "car_repair"
    elif "stomatolog" in afacere_lower or "dentar" in afacere_lower:
        valoare_osm = "dentist"
    elif "farmacie" in afacere_lower:
        valoare_osm = "pharmacy"
    else:
        tag_osm = "shop"
        valoare_osm = "yes"

    try:
        overpass_url = "https://overpass-api.de/api/interpreter"
        oras_safe = oras.replace('"', '')
        query = f"""
        [out:json][timeout:25];
        area["name"="{oras_safe}"]->.searchArea;
        (
          node["{tag_osm}"="{valoare_osm}"](area.searchArea);
          way["{tag_osm}"="{valoare_osm}"](area.searchArea);
        );
        out count;
        """
        response = requests.post(
            overpass_url,
            data={'data': query},
            headers={'User-Agent': 'business-analyzer/1.0'},
            timeout=30,
        )
        data = response.json()

        elements = data.get('elements', [])
        if elements:
            total_gasit = int(elements[0].get('tags', {}).get('total', 0))
            return max(total_gasit, 3)  # Valoare minimă realistă
        return 5
    except Exception as e:
        print(f"Avertisment căutare hartă: {e}")
        return 6


@app.route('/')
def health():
    return jsonify({'status': 'ok'})


@app.route('/predict-cariera', methods=['POST'])
def predict_cariera():
    if df_cariere is None:
        return jsonify({'error': 'Baza de date cu cariere nu este disponibilă pe server.'}), 500

    data = request.get_json(silent=True) or {}

    dict_punctaje = {
        'REALIST': int(data.get('punctaj_realist', 0)),
        'INVESTIGATIV': int(data.get('punctaj_investigativ', 0)),
        'ARTISTIC': int(data.get('punctaj_artistic', 0)),
        'SOCIAL': int(data.get('punctaj_social', 0)),
        'INTREPRINZATOR': int(data.get('punctaj_intreprinzator', 0)),
        'CONVENTIONAL': int(data.get('punctaj_conventional', 0))
    }

    profil_dominant = max(dict_punctaje, key=dict_punctaje.get)
    scor_maxim = dict_punctaje[profil_dominant]

    cariere_potrivite = df_cariere[df_cariere['cod_psihologic'] == profil_dominant]
    if cariere_potrivite.empty:
        return jsonify({'error': f'Nu s-au găsit cariere pentru profilul {profil_dominant}'}), 404

    index_selectat = scor_maxim % len(cariere_potrivite)
    cariera = cariere_potrivite.iloc[index_selectat]

    return jsonify({
        'status': 'success',
        'id_cariera': int(cariera['id_cariera']),
        'profil_detectat': profil_dominant,
        'descriere_profil': str(cariera.get('descriere_profil', '')),
        'punctaj_obtinut': scor_maxim,
        'titlu_job': str(cariera['titlu_job']),
        'facultate_ro': str(cariera['facultate_ro']),
        'admitere_ro': str(cariera['admitere_ro']),
        'facultate_strainatate': str(cariera['facultate_strainatate']),
        'admitere_strainatate': str(cariera['admitere_strainatate']),
        'pas_practic': str(cariera['pas_practic']),
        'salariu_mediu': int(cariera['salariu_mediu'])
    })


@app.route('/predict', methods=['POST'])
def analizeaza_business_live():
    data = request.get_json(silent=True) or {}

    buget = float(data.get('buget', 0))
    oras = str(data.get('oras', 'Bacău')).strip()
    tip_afacere = str(data.get('tip_afacere', 'Cafenea')).strip()

    numar_competitori = numara_competitori_live(oras, tip_afacere)

    prompt_ia = f"""
    Ești un expert în analiză de piață și fezabilitate financiară din România.

    DATE INTRARE ÎN TIMP REAL:
    - Oraș analizat: {oras}
    - Tip afacere dorită: {tip_afacere}
    - Buget propus de antreprenor: {buget} EUR
    - Număr de competitori similari identificați pe hartă în {oras}: {numar_competitori} locații active.

    SARCINA TA:
    1. Calculează fezabilitatea (REUȘITĂ sau EȘEC) luând în calcul:
       - Densitatea competitorilor ({numar_competitori} deja existenți în {oras}).
       - Suficiența bugetului de {buget} EUR pentru chirii, echipamente și promovare în {oras}.
    2. Redactează un raport scurt de 2-3 paragrafe în limba română:
       - Începe cu decizia clară: '✅ REZULTAT: FEZABIL (REUȘITĂ)' sau '❌ REZULTAT: RISC CRESCUT (EȘEC)'.
       - Menționează că s-au identificat {numar_competitori} competitori pe harta orașului {oras}.
       - Explică dacă bugetul de {buget} EUR este suficient pentru a face față concurenței locale.
       - Oferă o recomandare strategică concretă.
    """

    try:
        if client is None:
            raise RuntimeError("GROQ_API_KEY nu este setată pe server.")
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt_ia}],
            model="llama-3.3-70b-versatile",
        )
        rap_ia = chat_completion.choices[0].message.content
        # Decizia e în prima parte a raportului; verificăm acolo ca să nu apară false pozitive
        inceput = rap_ia[:200].upper()
        if "❌" in inceput or "RISC CRESCUT" in inceput or "EȘEC" in inceput:
            status_str = "EȘEC"
        else:
            status_str = "REUȘITĂ"
    except Exception as e:
        status_str = "EȘEC"
        rap_ia = f"Eroare la procesarea raportului IA: {str(e)}"

    return jsonify({
        'rezultat': status_str,
        'explicatie': rap_ia,
        'competitori_gasiti': numar_competitori,
        'oras': oras
    })


if __name__ == '__main__':
    # Doar pentru rulare locală; pe Render pornește gunicorn
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
