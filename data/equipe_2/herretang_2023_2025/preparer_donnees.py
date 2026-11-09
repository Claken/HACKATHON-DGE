"""Extraction reproductible : un canal piéton IN, calendrier officiel et météo horaire."""
import collections
import csv
import datetime as dt
import io
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent
WORK = ROOT.parent
SOURCES = ROOT / 'sources'
PARIS = ZoneInfo('Europe/Paris')
UTC = dt.timezone.utc
CHANNEL = '353347292'
DAYS = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche']


def read_json(path):
    return json.loads(path.read_text())


def write_csv(path, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter=';')
        writer.writeheader()
        writer.writerows(rows)


def build():
    holidays = read_json(SOURCES / 'jours_feries_metropole.json')
    school = read_json(SOURCES / 'vacances_grenoble.json')
    assert len(school['results']) == school['total_count'], 'Pagination calendrier incomplète'
    periods = []
    for record in school['results']:
        if record['population'] not in ['-', 'Élèves']:
            continue
        start = dt.datetime.fromisoformat(record['start_date']).astimezone(PARIS).date()
        end = dt.datetime.fromisoformat(record['end_date']).astimezone(PARIS).date()
        periods.append((start, end, record['description']))
    weather = read_json(SOURCES / 'meteo_horaire_openmeteo.json')
    hourly = weather['hourly']
    by_end = {
        stamp: (hourly['precipitation'][i], hourly['snowfall'][i])
        for i, stamp in enumerate(hourly['time'])
    }
    assert len(by_end) == len(hourly['time']), 'Doublons météo'
    source_rows = {}
    counts = collections.Counter()
    source_total = 0
    metadata = []
    for year in [2023, 2024, 2025]:
        archive = WORK / 'donnees_sspcloud/Fréquentation/DONNEES brutes ecocompteurs ENS' / f'export-transport-data-gouv-fr_CG38Environnement_{year}.zip'
        with ZipFile(archive) as zipped:
            for name in ['sites.csv', 'channels.csv']:
                data = list(csv.DictReader(io.TextIOWrapper(zipped.open(name), encoding='utf-8-sig')))
                chosen = [r for r in data if r.get('channel_id') == CHANNEL] if name == 'channels.csv' else [r for r in data if r.get('site_id') == '100040825']
                metadata.append({'annee': year, 'fichier': name, 'lignes': chosen})
            for row in csv.DictReader(io.TextIOWrapper(zipped.open('measures.csv'), encoding='utf-8-sig')):
                if row['channel_id'] != CHANNEL:
                    continue
                start = dt.datetime.fromisoformat(row['start_datetime']).astimezone(UTC)
                end = dt.datetime.fromisoformat(row['end_datetime']).astimezone(UTC)
                assert end - start == dt.timedelta(hours=1), 'Créneau non horaire'
                assert start not in source_rows, 'Doublon de créneau'
                source_rows[start] = row
                counts[year] += 1
                try:
                    number = float(row['count'])
                except ValueError:
                    continue
                if math.isfinite(number) and number >= 0:
                    source_total += number

    start = dt.datetime(2023, 1, 1, tzinfo=PARIS).astimezone(UTC)
    stop = dt.datetime(2026, 1, 1, tzinfo=PARIS).astimezone(UTC)
    traffic, meteo, anomalies = [], [], []
    while start < stop:
        end = start + dt.timedelta(hours=1)
        local = start.astimezone(PARIS)
        day = local.date()
        key = start.isoformat().replace('+00:00', 'Z')
        row = source_rows.get(start)
        quality, value = 'valide', ''
        if row is None or row['count'] == '':
            quality = 'manquante'
        else:
            try:
                number = float(row['count'])
                if not math.isfinite(number) or number < 0 or not number.is_integer():
                    quality = 'invalide'
                else:
                    value = int(number)
            except ValueError:
                quality = 'invalide'
        if quality != 'valide':
            anomalies.append({'debut_utc': key, 'valeur_source': row['count'] if row else None, 'qualite': quality})
        names = sorted({name for first, last, name in periods if first <= day < last})
        common = dict(debut_utc=key, debut_local=local.isoformat(), date=day.isoformat(), heure=local.hour)
        traffic.append(dict(
            **common, fin_local=end.astimezone(PARIS).isoformat(),
            jour_semaine=DAYS[day.weekday()], weekend=int(day.weekday() >= 5),
            jour_ferie=int(day.isoformat() in holidays), nom_jour_ferie=holidays.get(day.isoformat(), ''),
            vacances_scolaires_zone_a=int(bool(names)), nom_vacances=' / '.join(names),
            passages_entrants=value, qualite_frequentation=quality,
        ))
        # Open-Meteo étiquette les cumuls avec la FIN de l'heure précédente.
        rain, snow = by_end[int(end.timestamp())]
        assert rain is not None and snow is not None and rain >= 0 and snow >= 0
        meteo.append(dict(**common, precipitations_mm=rain, precipitation_oui_non=int(rain > 0), neige_tombee_cm=snow, neige_oui_non=int(snow > 0)))
        start = end

    assert len(traffic) == len(meteo) == 26304
    assert len(source_rows) == 26304
    assert len({r['debut_utc'] for r in traffic}) == len(traffic)
    assert [r['debut_utc'] for r in traffic] == [r['debut_utc'] for r in meteo]
    assert sum(r['passages_entrants'] for r in traffic if r['passages_entrants'] != '') == source_total
    assert len({r['date'] for r in traffic}) == 1096
    write_csv(ROOT / 'frequentation_herretang_2023_2025.csv', traffic)
    write_csv(ROOT / 'meteo_herretang_2023_2025.csv', meteo)
    (SOURCES / 'metadata_compteur.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
    report = dict(
        canal=CHANNEL, site='100040825', lignes_par_fichier=len(traffic), jours=1096,
        lignes_sources_par_annee=dict(counts), passages_valides_total=int(source_total),
        qualite=dict(collections.Counter(r['qualite_frequentation'] for r in traffic)),
        anomalies=anomalies, correspondance_meteo_complete=True,
        meteo_latitude_retournee=weather['latitude'], meteo_longitude_retournee=weather['longitude'],
        calendrier='Grenoble, zone A, élèves ; date de début incluse et reprise exclue',
    )
    (ROOT / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    build()
