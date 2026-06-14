import json
import os
import re
import unicodedata
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import requests
from django.utils import timezone

from .models import RouteSchedule, RouteStation, Station, Trip


OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5")

SUPPORTED_INTENTS = {
    "greeting",
    "search_route",
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

Allowed intents: greeting, search_route, reservation_help, ticket_help,
contact_help, capabilities, pricing_help, payment_help, boarding_help,
luggage_help, cancellation_help, delay_help, account_help, passenger_help,
accessibility_help, station_help, personal_trips, complaint_help, unknown.

JSON schema:
{{"intent":"unknown","departure":null,"arrival":null,"date":null,"time":null}}

Rules:
- Use search_route only when the user wants a bus route or schedule.
- Use personal_trips for questions about the user's own booking or next trip.
- Use pricing_help for ticket cost, fare or price questions.
- Use boarding_help for QR validation, boarding time or boarding procedure.
- Use unknown only when none of the specific intents applies.
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
    elif any(word in normalized for word in ("statie", "autogara", "de unde pleaca")):
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
        for phrase in ("cursa", "ruta", "ajung", "plec", "orar", "cat costa", "pret", "tarif")
    )
    if len(matches) >= 2 and route_question:
        intent = "search_route"

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
    elif "acum" in normalized:
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


def find_valid_journeys(departure_name, arrival_name, search_date, requested_time=None):
    departure = _find_station(departure_name)
    arrival = _find_station(arrival_name)
    if not departure or not arrival:
        return []

    now_local = timezone.localtime()
    earliest_at = timezone.make_aware(
        datetime.combine(search_date, requested_time or time.min)
    )
    if search_date == now_local.date():
        earliest_at = max(earliest_at, now_local)

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
    return journeys[:3]


def build_route_reply(journeys, departure, arrival, search_date, requested_time=None):
    if not departure or not arrival:
        return (
            "Spune-mi stația de plecare și destinația. De exemplu: "
            "**Vreau mâine din Alexandria în București**."
        )
    time_note = f" după ora **{requested_time.strftime('%H:%M')}**" if requested_time else ""
    if not journeys:
        return (
            f"Nu am găsit curse disponibile din **{departure}** în **{arrival}** "
            f"pentru **{search_date.strftime('%d.%m.%Y')}**{time_note}, nici cu un transfer. "
            "Poți încerca o altă oră sau dată."
        )

    reply = f"Am găsit {len(journeys)} " + ("variantă" if len(journeys) == 1 else "variante") + ":"
    for index, journey in enumerate(journeys, start=1):
        legs = journey["legs"]
        duration = journey["arrival_at"] - journey["departure_at"]
        hours, remainder = divmod(int(duration.total_seconds()), 3600)
        minutes = remainder // 60
        transfer_text = "Direct" if len(legs) == 1 else f"Transfer în {legs[0]['arr_name']}"
        total_price = sum((leg["price"] for leg in legs), Decimal("0"))
        reply += (
            f"\n\n**{index}. {transfer_text}** ({hours}h {minutes:02d}m) · "
            f"**{total_price:.2f} RON** · **{search_date.strftime('%d.%m.%Y')}**"
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
    if not journeys:
        return (
            f"Nu am găsit o cursă disponibilă din **{departure}** în **{arrival}** "
            f"pentru **{search_date.strftime('%d.%m.%Y')}**."
        )

    direct_journeys = [journey for journey in journeys if len(journey["legs"]) == 1]
    relevant_journeys = direct_journeys or journeys
    prices = sorted({
        sum((leg["price"] for leg in journey["legs"]), Decimal("0"))
        for journey in relevant_journeys
    })
    route_type = "cursa directă" if direct_journeys else "varianta cu transfer"

    if len(prices) == 1:
        return (
            f"Biletul pentru {route_type} din **{departure}** în **{arrival}** costă "
            f"**{prices[0]:.2f} RON / pasager**. Tariful este calculat la **0,50 RON/km**."
        )

    formatted_prices = ", ".join(f"**{price:.2f} RON**" for price in prices)
    return (
        f"Pentru traseul din **{departure}** în **{arrival}**, tarifele disponibile sunt "
        f"{formatted_prices} per pasager, în funcție de variantă."
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
    if (
        fallback.get("intent") == "search_route"
        and fallback.get("departure")
        and fallback.get("arrival")
    ):
        extraction["intent"] = "search_route"
    if extraction.get("intent") == "unknown" and fallback.get("intent") != "search_route":
        extraction["intent"] = fallback["intent"]
    for field in ("departure", "arrival", "date", "time"):
        if not extraction.get(field) and fallback.get(field):
            extraction[field] = fallback[field]
    intent = extraction.get("intent", "unknown")

    static_replies = {
        "greeting": "Bună! Sunt asistentul AutoTrans. Te pot ajuta să găsești o cursă, să rezervi sau să descarci un bilet.",
        "reservation_help": "Caută o rută, deschide cursa dorită și apasă **Rezervă**. Pentru finalizarea rezervării trebuie să fii autentificat.",
        "ticket_help": "Biletele tale sunt în pagina [Rezervările mele](/rezervarile-mele/), de unde poți descărca PDF-ul cu codul QR.",
        "contact_help": "Ne poți contacta la **+40 712 345 678**, la **contact@autotrans.ro** sau prin pagina [Contact](/contact/).",
        "capabilities": "Pot căuta rute directe sau cu transfer, verifica orare, explica prețul, plata, rezervarea, îmbarcarea, biletele QR și rezervările tale. Pentru politici speciale te trimit către echipa AutoTrans.",
        "pricing_help": "Prețul este calculat în funcție de distanța parcursă: **0,50 RON/km pentru fiecare pasager**. Prețul exact apare înainte de confirmarea plății.",
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
    if intent in static_replies:
        return {"text": static_replies[intent], "journeys": []}

    search_date = resolve_search_date(extraction.get("date"))
    requested_time = resolve_search_time(extraction.get("time"))
    journeys = find_valid_journeys(
        extraction.get("departure"), extraction.get("arrival"), search_date, requested_time
    )
    if _is_price_only_question(message_text):
        return {
            "text": _build_price_reply(
                journeys,
                extraction.get("departure"),
                extraction.get("arrival"),
                search_date,
            ),
            "journeys": [],
        }
    return {
        "text": build_route_reply(
            journeys,
            extraction.get("departure"),
            extraction.get("arrival"),
            search_date,
            requested_time,
        ),
        "journeys": _serialize_journeys(journeys),
    }


def build_assistant_reply(message_text, user=None):
    return build_assistant_response(message_text, user=user)["text"]
