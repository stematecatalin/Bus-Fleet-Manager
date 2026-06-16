import json
import os
import re
import unicodedata
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import requests
from django.utils import timezone

from .models import Route, RouteSchedule, RouteStation, Station, Trip


OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5")

SUPPORTED_INTENTS = {
    "greeting",
    "search_route",
    "station_routes",
    "reservation_help",
    "ticket_help",
    "contact_help",
    "capabilities",
    "pricing_help",
    "payment_help",
    "boarding_help",
    "luggage_help",
    "cancellation_help",
    "delay_help",
    "account_help",
    "passenger_help",
    "accessibility_help",
    "station_help",
    "personal_trips",
    "complaint_help",
    "unknown",
}


def _normalize(value):
    value = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in value if not unicodedata.combining(char)).lower()


def _extract_json(content):
    content = content.strip().replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        return json.loads(match.group(0)) if match else None


def call_intent_agent(message_text):
    """Use Ollama only for intent/entity extraction, never for route facts."""
    station_names = list(Station.objects.values_list("name", flat=True))
    today = timezone.localdate()
    system_prompt = f"""
You are the intent classifier for AutoTrans, a Romanian bus booking website.
Return ONLY one JSON object. Do not answer the user directly.

Allowed intents: greeting, search_route, station_routes, reservation_help, ticket_help,
contact_help, capabilities, pricing_help, payment_help, boarding_help,
luggage_help, cancellation_help, delay_help, account_help, passenger_help,
accessibility_help, station_help, personal_trips, complaint_help, unknown.

JSON schema:
{{"intent":"unknown","departure":null,"arrival":null,"date":null,"time":null}}

Rules:
- Use search_route only when the user wants a bus route or schedule between TWO cities.
- Use station_routes when the user asks what buses/routes leave from a SINGLE city (e.g., "ce curse am din Bucuresti").
- Use personal_trips for questions about the user's own booking or next trip.
- Use pricing_help for ticket cost, fare or price questions.
- date must be YYYY-MM-DD or null.
- time must be HH:MM or null. For "acum", use the current local time.
- Today is {today.isoformat()}. Resolve Romanian words such as azi and maine.
- Match departure and arrival to these station names when possible:
  {json.dumps(station_names, ensure_ascii=False)}
- Preserve Romanian diacritics in station names.
"""
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message_text},
                ],
                "format": "json",
                "stream": False,
                "options": {"temperature": 0, "num_predict": 160},
            },
            timeout=20,
        )
        response.raise_for_status()
        result = _extract_json(response.json().get("message", {}).get("content", ""))
        if result and result.get("intent") in SUPPORTED_INTENTS:
            return result
    except (requests.RequestException, ValueError, TypeError):
        pass
    return None


def fallback_intent(message_text):
    """Deterministic fallback used when Ollama is unavailable or uncertain."""
    normalized = _normalize(message_text)

    if any(word in normalized for word in ("salut", "buna", "hello", "hey")):
        intent = "greeting"
    elif any(word in normalized for word in ("urmatoarea mea cursa", "cursa mea", "rezervarea mea")):
        intent = "personal_trips"
    elif any(word in normalized for word in ("cat costa", "pret", "tarif", "cost")):
        intent = "pricing_help"
    elif any(word in normalized for word in ("card", "plata", "platesc", "cvv")):
        intent = "payment_help"
    elif any(word in normalized for word in ("bagaj", "valiza", "geamantan")):
        intent = "luggage_help"
    elif any(word in normalized for word in ("anulez", "anulare", "ramburs", "refund")):
        intent = "cancellation_help"
    elif any(word in normalized for word in ("intarzi", "nu a venit", "anulata cursa")):
        intent = "delay_help"
    elif any(word in normalized for word in ("imbarc", "urc", "valid", "scanner")):
        intent = "boarding_help"
    elif any(word in normalized for word in ("cont", "parola", "autentific", "login")):
        intent = "account_help"
    elif any(word in normalized for word in ("pasager", "mai multe bilete", "copil")):
        intent = "passenger_help"
    elif any(word in normalized for word in ("dizabil", "accesibil", "scaun rulant")):
        intent = "accessibility_help"
    elif any(word in normalized for word in ("statie", "autogara", "de unde pleaca", "ce curse am din", "curse din", "plecari din")):
        intent = "station_help"
    elif any(word in normalized for word in ("reclam", "sesizare", "nemultumit")):
        intent = "complaint_help"
    elif any(word in normalized for word in ("rezerv", "cumpar")):
        intent = "reservation_help"
    elif any(word in normalized for word in ("bilet", "qr", "descarc", "rezervarile mele")):
        intent = "ticket_help"
    elif any(word in normalized for word in ("contact", "telefon", "email", "operator")):
        intent = "contact_help"
    elif any(word in normalized for word in ("ce poti", "ajuta", "capabil")):
        intent = "capabilities"
    else:
        intent = "search_route"

    matches = []
    for station_name in Station.objects.values_list("name", flat=True):
        normalized_station = _normalize(station_name)
        city_alias = normalized_station.split("(", 1)[0].strip()
        matched_text = normalized_station if normalized_station in normalized else city_alias
        index = normalized.find(matched_text)
        if index >= 0:
            matches.append((index, station_name))
    matches.sort()

    route_question = any(
        phrase in normalized
        for phrase in ("autobuz", "cursa", "ruta", "ajung", "plec", "orar", "cat costa", "pret", "tarif")
    )
    if len(matches) >= 2 and route_question:
        intent = "search_route"
    elif len(matches) == 1 and intent in ("search_route", "station_help", "unknown"):
        intent = "station_routes"

    search_date = timezone.localdate()
    if "maine" in normalized:
        search_date += timedelta(days=1)
    iso_match = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", message_text)
    ro_match = re.search(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b", message_text)
    try:
        if iso_match:
            search_date = date.fromisoformat(iso_match.group(0))
        elif ro_match:
            search_date = date(int(ro_match.group(3)), int(ro_match.group(2)), int(ro_match.group(1)))
    except ValueError:
        pass

    requested_time = None
    time_match = re.search(r"\b(?:ora|la)?\s*(\d{1,2})[:.]([0-5]\d)\b", normalized)
    if time_match:
        hour = int(time_match.group(1))
        if hour <= 23:
            requested_time = f"{hour:02d}:{int(time_match.group(2)):02d}"
    else:
        hour_match = re.search(r"\b(?:ora|la ora|dupa ora|după ora)\s+(\d{1,2})\b", normalized)
        if hour_match:
            hour = int(hour_match.group(1))
            if hour <= 23:
                requested_time = f"{hour:02d}:00"
    if not requested_time and "acum" in normalized:
        requested_time = timezone.localtime().strftime("%H:%M")

    return {
        "intent": intent,
        "departure": matches[0][1] if len(matches) >= 1 else None,
        "arrival": matches[1][1] if len(matches) >= 2 else None,
        "date": search_date.isoformat(),
        "time": requested_time,
    }


def resolve_search_date(date_value):
    if not date_value:
        return timezone.localdate()
    if date_value == "today":
        return timezone.localdate()
    if date_value == "tomorrow":
        return timezone.localdate() + timedelta(days=1)
    try:
        return date.fromisoformat(date_value)
    except (TypeError, ValueError):
        return timezone.localdate()


def resolve_search_time(time_value):
    if not time_value:
        return None
    try:
        return time.fromisoformat(time_value)
    except (TypeError, ValueError):
        return None


def _find_station(name):
    if not name:
        return None
    exact = Station.objects.filter(name__iexact=name).first()
    if exact:
        return exact
    normalized_name = _normalize(name)
    return next(
        (station for station in Station.objects.all() if normalized_name in _normalize(station.name)),
        None,
    )


def _build_leg(schedule, departure_stop, arrival_stop, search_date):
    route_start = timezone.make_aware(datetime.combine(search_date, schedule.departure_time))
    departure_at = route_start + departure_stop.time_from_start
    arrival_at = route_start + arrival_stop.time_from_start
    distance = abs(arrival_stop.distance_from_start - departure_stop.distance_from_start)
    price = Decimal(str(distance)) * Decimal("0.5")
    trip, _ = Trip.objects.get_or_create(schedule=schedule, date=search_date)
    return {
        "dep_id": departure_stop.station_id,
        "arr_id": arrival_stop.station_id,
        "dep_name": departure_stop.station.name,
        "arr_name": arrival_stop.station.name,
        "departure_at": departure_at,
        "arrival_at": arrival_at,
        "distance_km": distance,
        "price": price,
        "link": (
            f"/rute/{trip.id}/?dep={departure_stop.station_id}"
            f"&arr={arrival_stop.station_id}"
        ),
    }


def _legs_between(departure, arrival, search_date, earliest_at=None):
    legs = []
    schedules = RouteSchedule.objects.filter(
        day_of_week=search_date.weekday(),
        route__stations__station=departure,
    ).select_related("route").distinct()

    for schedule in schedules:
        stops = list(
            RouteStation.objects.filter(route=schedule.route)
            .select_related("station")
            .order_by("order")
        )
        departure_stop = next((stop for stop in stops if stop.station_id == departure.id), None)
        arrival_stop = next((stop for stop in stops if stop.station_id == arrival.id), None)
        if not departure_stop or not arrival_stop or arrival_stop.order <= departure_stop.order:
            continue
        leg = _build_leg(schedule, departure_stop, arrival_stop, search_date)
        if earliest_at and leg["departure_at"] < earliest_at:
            continue
        legs.append(leg)

    return sorted(legs, key=lambda leg: leg["departure_at"])


def find_valid_journeys(departure_name, arrival_name, search_date, requested_time=None, ignore_now=False):
    departure = _find_station(departure_name)
    if not departure:
        return []

    now_local = timezone.localtime()
    earliest_at = timezone.make_aware(
        datetime.combine(search_date, requested_time or time.min)
    )
    if search_date == now_local.date() and not ignore_now:
        earliest_at = max(earliest_at, now_local)


    # Dacă avem și destinație, căutăm rute directe și cu transfer
    if arrival_name:
        arrival = _find_station(arrival_name)
        if not arrival:
            return []

        journeys = [
            {"legs": [leg], "departure_at": leg["departure_at"], "arrival_at": leg["arrival_at"]}
            for leg in _legs_between(departure, arrival, search_date, earliest_at)
        ]

        transfer_stations = Station.objects.filter(
            routestation__route__stations__station=departure
        ).exclude(id__in=(departure.id, arrival.id)).distinct()
        for transfer in transfer_stations:
            first_legs = _legs_between(departure, transfer, search_date, earliest_at)
            for first_leg in first_legs:
                connection_at = first_leg["arrival_at"] + timedelta(minutes=15)
                for second_leg in _legs_between(transfer, arrival, search_date, connection_at):
                    journeys.append({
                        "legs": [first_leg, second_leg],
                        "departure_at": first_leg["departure_at"],
                        "arrival_at": second_leg["arrival_at"],
                    })

        journeys.sort(key=lambda journey: (journey["arrival_at"], len(journey["legs"])))
        return journeys[:5]
    else:
        # Doar plecare - returnăm toate rutele care pleacă din această stație către destinația lor finală
        journeys = []
        routes_from_station = Route.objects.filter(stations__station=departure).distinct()
        for route in routes_from_station:
            last_stop = route.stations.all().order_by("-order").first()
            if last_stop and last_stop.station_id != departure.id:
                schedules = RouteSchedule.objects.filter(route=route, day_of_week=search_date.weekday())
                for sched in schedules:
                    stops = list(route.stations.all().order_by("order"))
                    dep_stop = next(s for s in stops if s.station_id == departure.id)
                    leg = _build_leg(sched, dep_stop, last_stop, search_date)
                    if leg["departure_at"] >= earliest_at:
                        journeys.append({
                            "legs": [leg],
                            "departure_at": leg["departure_at"],
                            "arrival_at": leg["arrival_at"]
                        })
        journeys.sort(key=lambda j: j["departure_at"])
        return journeys[:5]


def build_route_reply(journeys, departure, arrival, search_date, requested_time=None):
    if not departure:
        return (
            "Spune-mi stația de plecare. De exemplu: "
            "**Ce curse am din București?**"
        )
    
    time_note = f" după ora **{requested_time.strftime('%H:%M')}**" if requested_time else ""
    date_str = search_date.strftime('%d.%m.%Y')
    
    if not journeys:
        if arrival:
            return (
                f"Nu am găsit curse disponibile din **{departure}** în **{arrival}** "
                f"pentru **{date_str}**{time_note}. Poți încerca o altă oră sau dată."
            )
        else:
            return (
                f"Nu am găsit nicio cursă care să plece din **{departure}** "
                f"pentru **{date_str}**{time_note}."
            )

    variant_word = "variantă" if len(journeys) == 1 else "variante"
    if arrival:
        reply = f"Am găsit {len(journeys)} {variant_word} pentru ruta **{departure}** → **{arrival}**:"
    else:
        reply = f"Am găsit {len(journeys)} {variant_word} care pleacă din **{departure}** pe **{date_str}**:"

    for index, journey in enumerate(journeys, start=1):
        legs = journey["legs"]
        duration = journey["arrival_at"] - journey["departure_at"]
        hours, remainder = divmod(int(duration.total_seconds()), 3600)
        minutes = remainder // 60
        
        if arrival:
            transfer_text = "Direct" if len(legs) == 1 else f"Transfer în {legs[0]['arr_name']}"
        else:
            transfer_text = f"Către {legs[-1]['arr_name']}"
            
        total_price = sum((leg["price"] for leg in legs), Decimal("0"))
        reply += (
            f"\n\n**{index}. {transfer_text}** ({hours}h {minutes:02d}m) · "
            f"**{total_price:.2f} RON** · **{date_str}**"
        )
        for leg_index, leg in enumerate(legs, start=1):
            label = "Cursa" if len(legs) == 1 else f"Segmentul {leg_index}"
            reply += (
                f"\n- {label}: **{leg['departure_at'].strftime('%H:%M')}** {leg['dep_name']} → "
                f"**{leg['arrival_at'].strftime('%H:%M')}** {leg['arr_name']} "
                f"[Vezi și rezervă]({leg['link']})"
            )
    return reply


def _serialize_journeys(journeys):
    return [
        {
            "departure_time": journey["departure_at"].strftime("%H:%M"),
            "arrival_time": journey["arrival_at"].strftime("%H:%M"),
            "duration_minutes": int(
                (journey["arrival_at"] - journey["departure_at"]).total_seconds() // 60
            ),
            "date": journey["departure_at"].strftime("%d.%m.%Y"),
            "total_price": f"{sum((leg['price'] for leg in journey['legs']), Decimal('0')):.2f}",
            "transfer_count": len(journey["legs"]) - 1,
            "transfer_station": (
                journey["legs"][0]["arr_name"] if len(journey["legs"]) > 1 else None
            ),
            "legs": [
                {
                    "departure_name": leg["dep_name"],
                    "arrival_name": leg["arr_name"],
                    "departure_time": leg["departure_at"].strftime("%H:%M"),
                    "departure_date": leg["departure_at"].strftime("%d.%m.%Y"),
                    "arrival_time": leg["arrival_at"].strftime("%H:%M"),
                    "arrival_date": leg["arrival_at"].strftime("%d.%m.%Y"),
                    "price": f"{leg['price']:.2f}",
                    "distance_km": f"{leg['distance_km']:.1f}",
                    "link": leg["link"],
                }
                for leg in journey["legs"]
            ],
        }
        for journey in journeys
    ]


def _is_price_only_question(message_text):
    normalized = _normalize(message_text)
    asks_price = any(phrase in normalized for phrase in ("cat costa", "pret", "tarif", "costul"))
    asks_schedule = any(
        phrase in normalized
        for phrase in ("la ce ora", "ce ore", "orar", "cand pleaca", "cum ajung", "ce curse")
    )
    return asks_price and not asks_schedule


def _build_price_reply(journeys, departure, arrival, search_date):
    if not departure or not arrival:
        return "Pentru a afla prețul, te rog să-mi spui atât punctul de plecare, cât și destinația."

    if not journeys:
        # Dacă nu am găsit călătorii pentru data curentă, încercăm să găsim prețul generic pe bază de distanță dacă stațiile există
        dep_obj = _find_station(departure)
        arr_obj = _find_station(arrival)
        if dep_obj and arr_obj:
            # Încercăm să găsim o rută care le conține direct
            rs_dep = RouteStation.objects.filter(station=dep_obj).first()
            rs_arr = RouteStation.objects.filter(station=arr_obj).first()
            if rs_dep and rs_arr and rs_dep.route_id == rs_arr.route_id and rs_arr.order > rs_dep.order:
                dist = abs(rs_arr.distance_from_start - rs_dep.distance_from_start)
                price = Decimal(str(dist)) * Decimal("0.5")
                return (
                    f"Prețul standard pentru cursa directă **{dep_obj.name}** → **{arr_obj.name}** "
                    f"este de aproximativ **{price:.2f} RON**. Tariful este calculat la **0,50 RON/km**."
                )
            
            # Încercăm să găsim un punct de transfer (căutare simplă pe 2 segmente)
            transfer_station = Station.objects.filter(
                routestation__route__stations__station=dep_obj
            ).filter(
                routestation__route__stations__station=arr_obj
            ).exclude(id__in=(dep_obj.id, arr_obj.id)).distinct().first()
            
            if transfer_station:
                # Calculăm distanța via transfer
                rs1_dep = RouteStation.objects.filter(station=dep_obj, route__stations__station=transfer_station).first()
                rs1_trans = RouteStation.objects.filter(station=transfer_station, route=rs1_dep.route).first()
                
                rs2_trans = RouteStation.objects.filter(station=transfer_station, route__stations__station=arr_obj).first()
                rs2_arr = RouteStation.objects.filter(station=arr_obj, route=rs2_trans.route).first()
                
                if rs1_dep and rs1_trans and rs2_trans and rs2_arr:
                    dist1 = abs(rs1_trans.distance_from_start - rs1_dep.distance_from_start)
                    dist2 = abs(rs2_arr.distance_from_start - rs2_trans.distance_from_start)
                    total_price = (Decimal(str(dist1)) + Decimal(str(dist2))) * Decimal("0.5")
                    return (
                        f"Prețul estimat pentru ruta **{dep_obj.name}** → **{arr_obj.name}** (cu transfer în **{transfer_station.name}**) "
                        f"este de aproximativ **{total_price:.2f} RON**. Tariful se compune din cele două segmente calculate la **0,50 RON/km**."
                    )
        
        return (
            f"Nu am găsit informații despre preț pentru ruta **{departure}** → **{arrival}**. "
            "Asigură-te că stațiile sunt corecte."
        )

    prices = sorted({
        sum((leg["price"] for leg in journey["legs"]), Decimal("0"))
        for journey in journeys
    })
    
    has_transfer = any(len(j["legs"]) > 1 for j in journeys)
    route_type = "cursa" if not has_transfer else "varianta (inclusiv cele cu transfer)"

    if len(prices) == 1:
        return (
            f"Biletul pentru {route_type} din **{departure}** în **{arrival}** costă "
            f"**{prices[0]:.2f} RON / pasager**. Tariful este calculat la **0,50 RON/km**."
        )

    formatted_prices = ", ".join(f"**{price:.2f} RON**" for price in prices)
    return (
        f"Pentru traseul din **{departure}** în **{arrival}**, am găsit {len(prices)} tarife diferite: "
        f"{formatted_prices} per pasager, în funcție de cursa și varianta aleasă."
    )


def _personal_trips_reply(user):
    if not user or not user.is_authenticated:
        return (
            "Pentru a vedea rezervările tale trebuie să fii autentificat. După conectare, "
            "le găsești în [Rezervările mele](/rezervarile-mele/)."
        )

    next_ticket = (
        user.tickets.filter(trip__date__gte=timezone.localdate())
        .select_related(
            "trip__schedule__route", "start_station", "end_station"
        )
        .order_by("trip__date", "trip__schedule__departure_time")
        .first()
    )
    if not next_ticket:
        return (
            "Nu ai nicio călătorie viitoare în acest moment. "
            "Poți [căuta o rută](/rute/) sau consulta [Rezervările mele](/rezervarile-mele/)."
        )

    departure_time = next_ticket.get_departure_time().strftime("%H:%M")
    departure = next_ticket.start_station.name if next_ticket.start_station else "prima stație"
    arrival = next_ticket.end_station.name if next_ticket.end_station else "destinația finală"
    return (
        f"Următoarea ta călătorie este pe **{next_ticket.trip.date.strftime('%d.%m.%Y')}**, "
        f"la **{departure_time}**, din **{departure}** spre **{arrival}**. "
        "Biletul și codul QR sunt în [Rezervările mele](/rezervarile-mele/)."
    )


def build_assistant_response(message_text, user=None):
    fallback = fallback_intent(message_text)
    extraction = call_intent_agent(message_text) or fallback
    
    # Logică pentru a detecta dacă e o întrebare despre stație (doar plecare)
    if not extraction.get("arrival") and extraction.get("departure"):
        if extraction.get("intent") in ("search_route", "unknown"):
            extraction["intent"] = "station_routes"

    # Aliniere cu fallback dacă Ollama e nesigur
    if extraction.get("intent") == "unknown" and fallback.get("intent") != "unknown":
        extraction["intent"] = fallback["intent"]
    
    for field in ("departure", "arrival", "date", "time"):
        if not extraction.get(field) and fallback.get(field):
            extraction[field] = fallback[field]
            
    intent = extraction.get("intent", "unknown")
    departure_name = extraction.get("departure")
    arrival_name = extraction.get("arrival")
    search_date = resolve_search_date(extraction.get("date"))
    requested_time = resolve_search_time(extraction.get("time"))

    static_replies = {
        "greeting": "Bună! Sunt asistentul AutoTrans. Te pot ajuta să găsești o cursă, să rezervi sau să descarci un bilet.",
        "reservation_help": "Caută o rută, deschide cursa dorită și apasă **Rezervă**. Pentru finalizarea rezervării trebuie să fii autentificat.",
        "ticket_help": "Biletele tale sunt în pagina [Rezervările mele](/rezervarile-mele/), de unde poți descărca PDF-ul cu codul QR.",
        "contact_help": "Ne poți contacta la **+40 712 345 678**, la **contact@autotrans.ro** sau prin pagina [Contact](/contact/).",
        "capabilities": "Pot căuta rute directe sau cu transfer, verifica orare, explica prețul, plata, rezervarea, îmbarcarea, biletele QR și rezervările tale. Pentru politici speciale te trimit către echipa AutoTrans.",
        "pricing_help": "Prețul este calculat în funcție de distanța parcursă: **0,50 RON/km pentru fiecare pasager**. Spune-mi plecarea și destinația pentru a-ți calcula costul exact.",
        "payment_help": "Plata cu cardul este simulată în acest proiect. După alegerea cursei completezi pasagerii și datele cardului, iar sistemul generează biletele. Nu introduce date bancare reale în versiunea demonstrativă.",
        "boarding_help": "La îmbarcare prezintă biletul PDF și codul QR. Șoferul îl scanează și validează biletul o singură dată. Recomand să fii în stație cu aproximativ **10-15 minute înainte**.",
        "luggage_help": "Aplicația nu definește încă o politică oficială pentru bagaje. Pentru dimensiuni, costuri suplimentare sau obiecte speciale, verifică direct cu echipa la [Contact](/contact/) înainte de plecare.",
        "cancellation_help": "Momentan aplicația nu oferă anulare sau rambursare automată din cont. Trimite numărul rezervării prin pagina [Contact](/contact/) pentru verificarea situației.",
        "delay_help": "Aplicația afișează orarul planificat, dar nu urmărește încă întârzierile în timp real. Pentru o cursă întârziată sau anulată contactează echipa la **+40 712 345 678**.",
        "account_help": "Contul este creat cu adresa de email. Autentificarea este necesară pentru cumpărarea și consultarea biletelor. Parola poate fi resetată din pagina de autentificare.",
        "passenger_help": "Poți adăuga mai mulți pasageri în aceeași comandă. Pentru fiecare nume introdus se generează un bilet separat, iar totalul este recalculat automat.",
        "accessibility_help": "Aplicația nu conține încă informații certe despre accesul pentru scaun rulant sau asistența specială a fiecărui autobuz. Confirmă disponibilitatea înainte de rezervare prin [Contact](/contact/).",
        "station_help": "Stația exactă de plecare și cea de sosire apar în rezultatul căutării, în detaliile cursei și pe bilet. Spune-mi traseul și data dacă vrei să le caut acum.",
        "complaint_help": "Pentru o sesizare, folosește formularul [Contact](/contact/) și menționează data, ruta și numărul biletului. Echipa va putea identifica mai ușor cursa.",
        "unknown": "Întrebarea ta pare să țină de o situație pentru care aplicația nu are informații oficiale. Nu vreau să inventez un răspuns: poți cere confirmarea echipei la [Contact](/contact/), **+40 712 345 678** sau **contact@autotrans.ro**.",
    }

    if intent == "personal_trips":
        return {"text": _personal_trips_reply(user), "journeys": []}
    
    # Pre-calculate journeys for route or price queries
    is_price_q = _is_price_only_question(message_text) or (intent == "pricing_help" and departure_name and arrival_name)
    journeys = find_valid_journeys(departure_name, arrival_name, search_date, requested_time, ignore_now=is_price_q)

    # Priority for price inquiries
    if is_price_q:
        return {
            "text": _build_price_reply(journeys, departure_name, arrival_name, search_date),
            "journeys": _serialize_journeys(journeys) if journeys else [],
        }

    if intent in static_replies:
        return {"text": static_replies[intent], "journeys": []}
        
    return {
        "text": build_route_reply(journeys, departure_name, arrival_name, search_date, requested_time),
        "journeys": _serialize_journeys(journeys),
    }


def build_assistant_reply(message_text, user=None):
    return build_assistant_response(message_text, user=user)["text"]
