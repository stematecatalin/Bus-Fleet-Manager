import json
import os
from collections import defaultdict
from datetime import datetime, time, timedelta

import requests
from django.core import signing
from django.db.models import Count
from django.utils import timezone

from .models import Bus, Employee, Trip


OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
FLEET_AGENT_MODEL = os.getenv("FLEET_AGENT_MODEL", "mistral-nemo")
MAX_DRIVER_HOURS_PER_DAY = 8
LOW_OCCUPANCY_MERGE_THRESHOLD = 30
MAX_MERGE_DEPARTURE_GAP = timedelta(hours=3)
MERGE_PLAN_SALT = "fleet-merge-plan"
BUS_REALLOCATION_PLAN_SALT = "fleet-bus-reallocation-plan"
DRIVER_REALLOCATION_PLAN_SALT = "fleet-driver-reallocation-plan"


def _trip_window(trip):
    start = timezone.make_aware(
        datetime.combine(trip.date, trip.schedule.departure_time)
    )
    return start, start + trip.schedule.route.duration


def _overlaps(first, second):
    first_start, first_end = _trip_window(first)
    second_start, second_end = _trip_window(second)
    return first_start < second_end and second_start < first_end


def _planned_window(trip_date, departure_time, duration):
    start = timezone.make_aware(datetime.combine(trip_date, departure_time))
    return start, start + duration


def _window_overlaps(first_window, second_window):
    first_start, first_end = first_window
    second_start, second_end = second_window
    return first_start < second_end and second_start < first_end


def validate_planned_trip_resources(
    trip,
    *,
    bus,
    driver,
    departure_time=None,
    ticket_count=None,
    excluded_trip_ids=None,
    validate_driver=True,
):
    excluded_trip_ids = set(excluded_trip_ids or ())
    excluded_trip_ids.add(trip.id)
    departure_time = departure_time or trip.schedule.departure_time
    ticket_count = trip.tickets.count() if ticket_count is None else ticket_count
    planned_window = _planned_window(
        trip.date, departure_time, trip.schedule.route.duration
    )

    if not bus or bus.status != "active":
        raise ValueError("Autobuzul planificat nu mai este activ.")
    if bus.capacity < max(ticket_count, 1):
        raise ValueError("Autobuzul planificat nu are suficientă capacitate.")
    bus_assignments = (
        Trip.objects.filter(
            bus=bus,
            date=trip.date,
            status__in=("scheduled", "active"),
        )
        .exclude(id__in=excluded_trip_ids)
        .select_related("schedule__route")
    )
    for assignment in bus_assignments:
        if _window_overlaps(planned_window, _trip_window(assignment)):
            raise ValueError(
                f"Autobuzul {bus.license_plate} ar intra în conflict cu cursa #{assignment.id}."
            )

    if not validate_driver:
        return True
    if not driver or driver.position != "driver" or driver.status != "active":
        raise ValueError("Șoferul planificat nu mai este activ.")
    driver_assignments = list(
        Trip.objects.filter(
            driver=driver,
            date=trip.date,
            status__in=("scheduled", "active"),
        )
        .exclude(id__in=excluded_trip_ids)
        .select_related("schedule__route")
    )
    for assignment in driver_assignments:
        if _window_overlaps(planned_window, _trip_window(assignment)):
            driver_name = _driver_payload(driver)["name"]
            raise ValueError(
                f"{driver_name} ar intra în conflict cu cursa #{assignment.id}."
            )
    total_duration = sum(
        (assignment.schedule.route.duration for assignment in driver_assignments),
        trip.schedule.route.duration,
    )
    if total_duration > timedelta(hours=MAX_DRIVER_HOURS_PER_DAY):
        driver_name = _driver_payload(driver)["name"]
        raise ValueError(
            f"{driver_name} ar depăși limita de {MAX_DRIVER_HOURS_PER_DAY} ore în acea zi."
        )
    return True


def _find_safe_merge_resources(keep_trip, cancel_trip, proposed_time, combined_tickets):
    excluded_ids = {keep_trip.id, cancel_trip.id}
    buses = Bus.objects.filter(
        status="active", capacity__gte=max(combined_tickets, 1)
    ).order_by("capacity", "license_plate")
    preferred_drivers = []
    for driver in (keep_trip.driver, cancel_trip.driver):
        if driver and driver.id not in {item.id for item in preferred_drivers}:
            preferred_drivers.append(driver)
    preferred_ids = {driver.id for driver in preferred_drivers}
    preferred_drivers.extend(
        Employee.objects.filter(position="driver", status="active")
        .exclude(id__in=preferred_ids)
        .select_related("user")
        .order_by("-rating", "id")
    )
    errors = []
    for bus in buses:
        for driver in preferred_drivers:
            try:
                validate_planned_trip_resources(
                    keep_trip,
                    bus=bus,
                    driver=driver,
                    departure_time=proposed_time,
                    ticket_count=combined_tickets,
                    excluded_trip_ids=excluded_ids,
                )
                return bus, driver
            except ValueError as exc:
                errors.append(str(exc))
    detail = errors[-1] if errors else "Nu există resurse active pentru cursa combinată."
    raise ValueError(
        "Combinarea ar afecta programul existent. "
        f"{detail}"
    )


def _bus_payload(bus):
    if not bus:
        return None
    return {
        "id": bus.id,
        "label": f"{bus.brand} {bus.model}",
        "license_plate": bus.license_plate,
        "capacity": bus.capacity,
        "status": bus.status,
    }


def _driver_payload(driver):
    if not driver:
        return None
    full_name = f"{driver.user.first_name} {driver.user.last_name}".strip()
    return {
        "id": driver.id,
        "name": full_name or driver.user.email,
        "status": driver.status,
    }


def _merge_candidate_data(first, second, active_buses=None):
    active_buses = active_buses or list(Bus.objects.filter(status="active").order_by("capacity"))
    if first.id == second.id:
        raise ValueError("Selectează două curse diferite.")
    if first.date != second.date or first.schedule.route_id != second.schedule.route_id:
        raise ValueError("Cursele trebuie să fie pe aceeași rută și în aceeași zi.")
    if first.status != "scheduled" or second.status != "scheduled":
        raise ValueError("Pot fi combinate doar curse programate.")

    now = timezone.localtime()
    first_start, _ = _trip_window(first)
    second_start, _ = _trip_window(second)
    if first_start <= now or second_start <= now:
        raise ValueError("Pot fi combinate doar curse care nu au plecat încă.")
    if abs(second_start - first_start) > MAX_MERGE_DEPARTURE_GAP:
        raise ValueError("Cursele sunt prea îndepărtate ca oră pentru combinare.")

    first_tickets = first.tickets.count()
    second_tickets = second.tickets.count()
    combined_tickets = first_tickets + second_tickets
    recommended_bus = next(
        (bus for bus in active_buses if bus.capacity >= max(combined_tickets, 1)),
        None,
    )
    if not recommended_bus:
        raise ValueError("Nu există un autobuz activ cu suficientă capacitate.")

    return {
        "combined_tickets": combined_tickets,
        "recommended_bus": recommended_bus,
        "trips": [
            {
                "id": first.id,
                "departure_time": first.schedule.departure_time.strftime("%H:%M"),
                "tickets": first_tickets,
                "bus": _bus_payload(first.bus),
                "driver": _driver_payload(first.driver),
            },
            {
                "id": second.id,
                "departure_time": second.schedule.departure_time.strftime("%H:%M"),
                "tickets": second_tickets,
                "bus": _bus_payload(second.bus),
                "driver": _driver_payload(second.driver),
            },
        ],
    }


def _deterministic_departure_time(first, second, first_tickets, second_tickets):
    first_start, _ = _trip_window(first)
    second_start, _ = _trip_window(second)
    first_weight = max(first_tickets, 1)
    second_weight = max(second_tickets, 1)
    weighted_timestamp = (
        first_start.timestamp() * first_weight + second_start.timestamp() * second_weight
    ) / (first_weight + second_weight)
    proposed = datetime.fromtimestamp(weighted_timestamp, tz=first_start.tzinfo)
    rounded_minute = int(round(proposed.minute / 5) * 5)
    if rounded_minute == 60:
        proposed = proposed.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    else:
        proposed = proposed.replace(minute=rounded_minute, second=0, microsecond=0)
    lower, upper = sorted((first_start, second_start))
    if upper - lower >= timedelta(minutes=10):
        lower += timedelta(minutes=5)
        upper -= timedelta(minutes=5)
    return max(lower, min(proposed, upper)).strftime("%H:%M")


def validate_proposed_departure_time(first, second, value):
    try:
        proposed_time = time.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError("Ora propusă nu are formatul HH:MM.")
    proposed = timezone.make_aware(datetime.combine(first.date, proposed_time))
    first_start, _ = _trip_window(first)
    second_start, _ = _trip_window(second)
    lower, upper = sorted((first_start, second_start))
    if not lower <= proposed <= upper:
        raise ValueError("Ora propusă trebuie să fie între plecările celor două curse.")
    return proposed_time


def generate_merge_plan(first, second):
    candidate = _merge_candidate_data(first, second)
    trips = candidate["trips"]
    deterministic_keep = sorted(
        trips,
        key=lambda trip: (-trip["tickets"], trip["departure_time"], trip["id"]),
    )[0]["id"]
    keep_trip_id = deterministic_keep
    rationale = (
        "Se păstrează cursa cu cele mai multe rezervări, iar ora este apropiată de "
        "grupul cu cei mai mulți pasageri pentru a reduce modificarea programului."
    )
    proposed_departure_time = _deterministic_departure_time(
        first, second, trips[0]["tickets"], trips[1]["tickets"]
    )
    model = "analiză deterministă"

    prompt = {
        "route": first.schedule.route.name,
        "date": first.date.isoformat(),
        "combined_tickets": candidate["combined_tickets"],
        "recommended_bus": _bus_payload(candidate["recommended_bus"]),
        "trips": trips,
    }
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": FLEET_AGENT_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Răspunde în limba română. Alege ce cursă trebuie păstrată și propune "
                            "o oră de plecare strict între cele două ore existente, nu una dintre "
                            "orele originale. Minimizează schimbarea "
                            "pentru grupul cu cei mai mulți pasageri. Returnează exclusiv JSON cu "
                            "schema {\"keep_trip_id\": 1, \"proposed_departure_time\": "
                            "\"09:30\", \"rationale\": \"explicație scurtă în română\"}."
                        ),
                    },
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
                "format": "json",
                "stream": False,
                "options": {"temperature": 0, "num_ctx": 2048, "num_predict": 160},
            },
            timeout=60,
        )
        response.raise_for_status()
        result = json.loads(response.json().get("message", {}).get("content", "{}"))
        proposed_id = int(result.get("keep_trip_id"))
        if proposed_id in {first.id, second.id}:
            keep_trip_id = proposed_id
            ai_time = str(result.get("proposed_departure_time", "")).strip()
            validate_proposed_departure_time(first, second, ai_time)
            original_times = {
                first.schedule.departure_time.strftime("%H:%M"),
                second.schedule.departure_time.strftime("%H:%M"),
            }
            if len(original_times) > 1 and ai_time in original_times:
                raise ValueError("Ora AI trebuie să fie între cele două plecări originale.")
            proposed_departure_time = ai_time
            rationale = str(result.get("rationale", "")).strip() or rationale
            model = FLEET_AGENT_MODEL
    except (requests.RequestException, ValueError, TypeError, json.JSONDecodeError):
        pass

    cancel_trip_id = second.id if keep_trip_id == first.id else first.id
    keep_trip = first if keep_trip_id == first.id else second
    cancel_trip = second if cancel_trip_id == second.id else first
    if proposed_departure_time == cancel_trip.schedule.departure_time.strftime("%H:%M"):
        proposed_departure_time = _deterministic_departure_time(
            first, second, trips[0]["tickets"], trips[1]["tickets"]
        )
    if proposed_departure_time == cancel_trip.schedule.departure_time.strftime("%H:%M"):
        proposed_departure_time = keep_trip.schedule.departure_time.strftime("%H:%M")
    proposed_time = validate_proposed_departure_time(first, second, proposed_departure_time)
    recommended_bus, recommended_driver = _find_safe_merge_resources(
        keep_trip,
        cancel_trip,
        proposed_time,
        candidate["combined_tickets"],
    )
    token = signing.dumps(
        {
            "keep_trip_id": keep_trip_id,
            "cancel_trip_id": cancel_trip_id,
            "bus_id": recommended_bus.id,
            "driver_id": recommended_driver.id,
            "proposed_departure_time": proposed_departure_time,
            "source": "ai" if model == FLEET_AGENT_MODEL else "fallback",
            "model": model,
            "rationale": rationale,
            "original_state": {
                str(keep_trip.id): {
                    "bus_id": keep_trip.bus_id,
                    "driver_id": keep_trip.driver_id,
                    "schedule_id": keep_trip.schedule_id,
                    "status": keep_trip.status,
                },
                str(cancel_trip.id): {
                    "bus_id": cancel_trip.bus_id,
                    "driver_id": cancel_trip.driver_id,
                    "schedule_id": cancel_trip.schedule_id,
                    "status": cancel_trip.status,
                },
            },
        },
        salt=MERGE_PLAN_SALT,
    )
    return {
        "token": token,
        "model": model,
        "rationale": rationale,
        "keep_trip": {
            "id": keep_trip.id,
            "departure_time": keep_trip.schedule.departure_time.strftime("%H:%M"),
            "tickets": keep_trip.tickets.count(),
        },
        "cancel_trip": {
            "id": cancel_trip.id,
            "departure_time": cancel_trip.schedule.departure_time.strftime("%H:%M"),
            "tickets": cancel_trip.tickets.count(),
        },
        "recommended_bus": _bus_payload(recommended_bus),
        "recommended_driver": _driver_payload(recommended_driver),
        "combined_tickets": candidate["combined_tickets"],
        "proposed_departure_time": proposed_departure_time,
    }


def decode_merge_plan(token):
    return signing.loads(token, salt=MERGE_PLAN_SALT, max_age=900)


def _bus_has_conflict(bus, trip):
    assignments = (
        Trip.objects.filter(
            bus=bus,
            date=trip.date,
            status__in=("scheduled", "active"),
        )
        .exclude(id=trip.id)
        .select_related("schedule__route")
    )
    return any(_overlaps(trip, assignment) for assignment in assignments)


def get_bus_reallocation_candidates(trip):
    if trip.status not in ("scheduled", "active"):
        raise ValueError("Pot fi realocate doar curse programate sau active.")
    trip_start, _ = _trip_window(trip)
    if trip.status == "scheduled" and trip_start <= timezone.localtime():
        raise ValueError("Cursa a plecat deja și nu mai poate fi realocată.")

    ticket_count = trip.tickets.count()
    candidates = []
    buses = Bus.objects.filter(
        status="active", capacity__gte=max(ticket_count, 1)
    ).order_by("capacity", "license_plate")
    for bus in buses:
        if bus.id == trip.bus_id or _bus_has_conflict(bus, trip):
            continue
        daily_assignments = Trip.objects.filter(
            bus=bus,
            date=trip.date,
            status__in=("scheduled", "active"),
        ).exclude(id=trip.id).count()
        candidates.append({
            "bus": bus,
            "ticket_count": ticket_count,
            "capacity_slack": bus.capacity - ticket_count,
            "daily_assignments": daily_assignments,
        })
    return sorted(
        candidates,
        key=lambda item: (
            item["capacity_slack"],
            item["daily_assignments"],
            item["bus"].license_plate,
        ),
    )


def generate_bus_reallocation_plan(trip_ids):
    try:
        requested_ids = list(dict.fromkeys(int(trip_id) for trip_id in trip_ids))
    except (TypeError, ValueError):
        raise ValueError("Lista curselor este invalidă.")
    if not requested_ids:
        raise ValueError("Nu a fost selectată nicio cursă pentru realocare.")

    trips = list(
        Trip.objects.filter(id__in=requested_ids)
        .select_related("schedule__route", "bus", "driver__user")
        .order_by("date", "schedule__departure_time", "id")
    )
    if len(trips) != len(requested_ids):
        raise ValueError("Una dintre curse nu mai există.")

    options = []
    errors = []
    for trip in trips:
        try:
            candidates = get_bus_reallocation_candidates(trip)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        for candidate in candidates[:5]:
            options.append({
                "trip": trip,
                **candidate,
            })
    if not options:
        detail = errors[0] if errors else "Nu există niciun autobuz activ, liber și cu suficientă capacitate."
        raise ValueError(detail)

    options.sort(key=lambda item: (
        item["capacity_slack"],
        item["daily_assignments"],
        item["trip"].date,
        item["trip"].schedule.departure_time,
    ))
    selected = options[0]
    rationale = (
        "Autobuzul ales este activ, nu are curse suprapuse și este cea mai apropiată "
        "variantă ca număr de locuri, astfel încât capacitatea flotei rămâne bine distribuită."
    )
    model = "analiză deterministă"
    prompt_options = [{
        "trip_id": option["trip"].id,
        "route": option["trip"].schedule.route.name,
        "date": option["trip"].date.isoformat(),
        "departure_time": option["trip"].schedule.departure_time.strftime("%H:%M"),
        "tickets": option["ticket_count"],
        "bus": _bus_payload(option["bus"]),
        "capacity_slack": option["capacity_slack"],
        "other_assignments_that_day": option["daily_assignments"],
    } for option in options[:12]]

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": FLEET_AGENT_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Răspunde în limba română. Alege exclusiv una dintre combinațiile "
                            "cursă-autobuz primite. Preferă capacitatea apropiată de cerere și "
                            "autobuzul cu mai puține alocări în ziua respectivă. Returnează exclusiv "
                            "JSON cu schema {\"trip_id\": 1, \"bus_id\": 2, "
                            "\"rationale\": \"explicație scurtă în română\"}."
                        ),
                    },
                    {"role": "user", "content": json.dumps(prompt_options, ensure_ascii=False)},
                ],
                "format": "json",
                "stream": False,
                "options": {"temperature": 0, "num_ctx": 2048, "num_predict": 140},
            },
            timeout=60,
        )
        response.raise_for_status()
        result = json.loads(response.json().get("message", {}).get("content", "{}"))
        proposed_pair = (int(result.get("trip_id")), int(result.get("bus_id")))
        matching_option = next(
            (option for option in options if (
                option["trip"].id, option["bus"].id
            ) == proposed_pair),
            None,
        )
        if matching_option:
            selected = matching_option
            rationale = str(result.get("rationale", "")).strip() or rationale
            model = FLEET_AGENT_MODEL
    except (requests.RequestException, ValueError, TypeError, json.JSONDecodeError):
        pass

    trip = selected["trip"]
    bus = selected["bus"]
    token = signing.dumps({
        "trip_id": trip.id,
        "bus_id": bus.id,
        "original_bus_id": trip.bus_id,
        "source": "ai" if model == FLEET_AGENT_MODEL else "fallback",
        "model": model,
        "rationale": rationale,
    }, salt=BUS_REALLOCATION_PLAN_SALT)
    return {
        "token": token,
        "model": model,
        "rationale": rationale,
        "trip": {
            "id": trip.id,
            "route": trip.schedule.route.name,
            "date": trip.date.isoformat(),
            "departure_time": trip.schedule.departure_time.strftime("%H:%M"),
            "tickets": selected["ticket_count"],
        },
        "current_bus": _bus_payload(trip.bus),
        "recommended_bus": _bus_payload(bus),
    }


def decode_bus_reallocation_plan(token):
    return signing.loads(token, salt=BUS_REALLOCATION_PLAN_SALT, max_age=900)


def _driver_external_assignments(driver, dates, excluded_trip_ids):
    return list(
        Trip.objects.filter(
            driver=driver,
            date__in=dates,
            status__in=("scheduled", "active"),
        )
        .exclude(id__in=excluded_trip_ids)
        .select_related("schedule__route")
    )


def validate_driver_distribution(trips, assignments):
    trip_ids = {trip.id for trip in trips}
    if set(assignments) != trip_ids:
        raise ValueError("Planul nu conține toate cursele selectate.")
    drivers = {
        driver.id: driver
        for driver in Employee.objects.filter(
            id__in=set(assignments.values()), position="driver", status="active"
        ).select_related("user")
    }
    if len(drivers) != len(set(assignments.values())):
        raise ValueError("Unul dintre șoferii recomandați nu mai este activ.")

    dates = {trip.date for trip in trips}
    grouped = defaultdict(list)
    for driver in drivers.values():
        for external_trip in _driver_external_assignments(driver, dates, trip_ids):
            grouped[(driver.id, external_trip.date)].append(external_trip)
    for trip in trips:
        grouped[(assignments[trip.id], trip.date)].append(trip)

    for (driver_id, work_date), daily_trips in grouped.items():
        total_duration = sum(
            (trip.schedule.route.duration for trip in daily_trips), timedelta()
        )
        if total_duration > timedelta(hours=MAX_DRIVER_HOURS_PER_DAY):
            driver_name = _driver_payload(drivers[driver_id])["name"]
            raise ValueError(
                f"{driver_name} ar depăși {MAX_DRIVER_HOURS_PER_DAY} ore în {work_date:%d.%m.%Y}."
            )
        for index, first in enumerate(daily_trips):
            for second in daily_trips[index + 1:]:
                if _overlaps(first, second):
                    driver_name = _driver_payload(drivers[driver_id])["name"]
                    raise ValueError(
                        f"{driver_name} ar avea curse suprapuse în {work_date:%d.%m.%Y}."
                    )
    return drivers


def _find_driver_distribution(trips):
    trip_ids = {trip.id for trip in trips}
    dates = {trip.date for trip in trips}
    drivers = list(
        Employee.objects.filter(position="driver", status="active")
        .select_related("user")
        .order_by("-rating", "id")
    )
    if not drivers:
        raise ValueError("Nu există niciun șofer activ disponibil.")

    external = {}
    base_hours = {}
    static_candidates = {}
    for driver in drivers:
        assignments = _driver_external_assignments(driver, dates, trip_ids)
        for work_date in dates:
            daily = [trip for trip in assignments if trip.date == work_date]
            external[(driver.id, work_date)] = daily
            base_hours[(driver.id, work_date)] = sum(
                (trip.schedule.route.duration for trip in daily), timedelta()
            )

    for trip in trips:
        candidates = []
        for driver in drivers:
            key = (driver.id, trip.date)
            if base_hours[key] + trip.schedule.route.duration > timedelta(
                hours=MAX_DRIVER_HOURS_PER_DAY
            ):
                continue
            if any(_overlaps(trip, other) for other in external[key]):
                continue
            candidates.append(driver)
        if not candidates:
            raise ValueError(
                f"Nu există un șofer eligibil pentru cursa #{trip.id}, fără suprapuneri și sub 8 ore."
            )
        static_candidates[trip.id] = candidates

    ordered_trips = sorted(
        trips,
        key=lambda trip: (
            len(static_candidates[trip.id]),
            trip.date,
            trip.schedule.departure_time,
            -trip.schedule.route.duration.total_seconds(),
        ),
    )
    planned_trips = defaultdict(list)
    planned_hours = defaultdict(timedelta)
    current = {}
    best = {"score": None, "assignments": None}
    visited = 0

    def search(index, changed_count):
        nonlocal visited
        visited += 1
        if visited > 25000:
            return
        if best["score"] is not None and changed_count > best["score"][0]:
            return
        if index == len(ordered_trips):
            workloads = [
                (base_hours[(driver.id, work_date)] + planned_hours[(driver.id, work_date)]).total_seconds()
                for driver in drivers for work_date in dates
            ]
            score = (changed_count, sum(hours * hours for hours in workloads))
            if best["score"] is None or score < best["score"]:
                best["score"] = score
                best["assignments"] = current.copy()
            return

        trip = ordered_trips[index]
        ranked_drivers = sorted(
            static_candidates[trip.id],
            key=lambda driver: (
                driver.id != trip.driver_id,
                base_hours[(driver.id, trip.date)] + planned_hours[(driver.id, trip.date)],
                -driver.rating,
                driver.id,
            ),
        )
        for driver in ranked_drivers:
            key = (driver.id, trip.date)
            if planned_hours[key] + base_hours[key] + trip.schedule.route.duration > timedelta(
                hours=MAX_DRIVER_HOURS_PER_DAY
            ):
                continue
            if any(_overlaps(trip, other) for other in planned_trips[key]):
                continue
            current[trip.id] = driver.id
            planned_trips[key].append(trip)
            planned_hours[key] += trip.schedule.route.duration
            search(index + 1, changed_count + (driver.id != trip.driver_id))
            planned_hours[key] -= trip.schedule.route.duration
            planned_trips[key].pop()
            current.pop(trip.id, None)

    search(0, 0)
    if not best["assignments"]:
        raise ValueError(
            "Nu am găsit o distribuție completă fără suprapuneri și fără depășirea limitei de 8 ore."
        )
    validate_driver_distribution(trips, best["assignments"])
    return best["assignments"]


def _driver_agent_context(trips):
    trip_ids = {trip.id for trip in trips}
    dates = {trip.date for trip in trips}
    drivers = list(
        Employee.objects.filter(position="driver", status="active")
        .select_related("user")
        .order_by("-rating", "id")
    )
    external_by_driver = {
        driver.id: _driver_external_assignments(driver, dates, trip_ids)
        for driver in drivers
    }
    trip_rows = []
    for trip in trips:
        eligible_driver_ids = []
        for driver in drivers:
            daily = [
                assignment for assignment in external_by_driver[driver.id]
                if assignment.date == trip.date
            ]
            total_duration = sum(
                (assignment.schedule.route.duration for assignment in daily),
                timedelta(),
            )
            if total_duration + trip.schedule.route.duration > timedelta(
                hours=MAX_DRIVER_HOURS_PER_DAY
            ):
                continue
            if any(_overlaps(trip, assignment) for assignment in daily):
                continue
            eligible_driver_ids.append(driver.id)
        trip_rows.append({
            "trip_id": trip.id,
            "route": trip.schedule.route.name,
            "date": trip.date.isoformat(),
            "departure_time": trip.schedule.departure_time.strftime("%H:%M"),
            "arrival_time": _trip_window(trip)[1].strftime("%H:%M"),
            "duration_hours": round(trip.schedule.route.duration.total_seconds() / 3600, 1),
            "current_driver_id": trip.driver_id,
            "eligible_driver_ids": eligible_driver_ids,
        })
    return {
        "rules": {
            "maximum_daily_hours": MAX_DRIVER_HOURS_PER_DAY,
            "no_overlapping_trips": True,
            "assign_every_trip": True,
            "prefer_fewer_changes": True,
            "balance_workload": True,
        },
        "allowed_driver_ids": [driver.id for driver in drivers],
        "trips_to_assign": trip_rows,
        "active_drivers": [{
            **_driver_payload(driver),
            "existing_assignments": [{
                "trip_id": assignment.id,
                "date": assignment.date.isoformat(),
                "departure_time": assignment.schedule.departure_time.strftime("%H:%M"),
                "arrival_time": _trip_window(assignment)[1].strftime("%H:%M"),
                "duration_hours": round(
                    assignment.schedule.route.duration.total_seconds() / 3600, 1
                ),
            } for assignment in external_by_driver[driver.id]],
        } for driver in drivers],
    }


def _parse_driver_agent_plan(result, trips):
    raw_assignments = result.get("assignments")
    if not isinstance(raw_assignments, list):
        raise ValueError("Răspunsul AI nu conține lista assignments.")
    assignments = {}
    for item in raw_assignments:
        if not isinstance(item, dict):
            raise ValueError("O alocare AI are format invalid.")
        trip_id = int(item.get("trip_id"))
        driver_id = int(item.get("driver_id"))
        if trip_id in assignments:
            raise ValueError(f"Cursa #{trip_id} apare de mai multe ori în planul AI.")
        assignments[trip_id] = driver_id
    validate_driver_distribution(trips, assignments)
    return assignments


def _ask_driver_agent_for_distribution(trips, max_attempts=3):
    required_trip_ids = [trip.id for trip in trips]
    context = _driver_agent_context(trips)
    allowed_driver_ids = context["allowed_driver_ids"]
    messages = [{
        "role": "system",
        "content": (
            "Ești un agent AI dispecer pentru o companie de transport. Generează tu planul complet "
            "de alocare a șoferilor, folosind exclusiv cursele și șoferii primiți. Respectă toate "
            "regulile, păstrează cât mai multe alocări curente și echilibrează volumul de muncă. "
            "Returnează exclusiv JSON cu schema {\"assignments\": [{\"trip_id\": 1, "
            "\"driver_id\": 2}], \"rationale\": \"explicație scurtă în română\"}. "
            f"Trebuie să returnezi exact {len(required_trip_ids)} alocări pentru ID-urile "
            f"{required_trip_ids}. Fiecare dintre aceste curse trebuie să apară exact o dată, "
            f"fără alte ID-uri. Folosește doar driver_id din lista {allowed_driver_ids} și, "
            "pentru fiecare cursă, doar din eligible_driver_ids."
        ),
    }, {
        "role": "user",
        "content": json.dumps(context, ensure_ascii=False),
    }]
    last_error = None
    previous_content = "{}"
    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.post(
                OLLAMA_URL,
                json={
                    "model": FLEET_AGENT_MODEL,
                    "messages": messages,
                    "format": "json",
                    "stream": False,
                    "options": {"temperature": 0.1, "num_ctx": 2048, "num_predict": 400},
                },
                timeout=90,
            )
            response.raise_for_status()
            previous_content = response.json().get("message", {}).get("content", "{}")
            result = json.loads(previous_content)
            assignments = _parse_driver_agent_plan(result, trips)
            rationale = str(result.get("rationale", "")).strip() or (
                "Agentul a ales distribuția respectând disponibilitatea și programul șoferilor."
            )
            return assignments, rationale, attempt
        except requests.RequestException:
            raise
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            last_error = str(exc)
            messages.extend([{
                "role": "assistant",
                "content": previous_content,
            }, {
                "role": "user",
                "content": (
                    f"Planul a fost respins de validator: {last_error} "
                    f"Generează un plan complet corectat cu exact {len(required_trip_ids)} alocări "
                    f"pentru cursele {required_trip_ids}, în aceeași schemă JSON. Folosește numai "
                    f"driver_id din {allowed_driver_ids} și respectă eligible_driver_ids."
                ),
            }])
    response_preview = previous_content[:500].replace("\n", " ")
    raise ValueError(
        f"{last_error or 'Agentul nu a generat un plan valid.'} "
        f"Ultimul răspuns AI: {response_preview}"
    )


def generate_driver_reallocation_plan(trip_ids):
    try:
        requested_ids = list(dict.fromkeys(int(trip_id) for trip_id in trip_ids))
    except (TypeError, ValueError):
        raise ValueError("Lista curselor este invalidă.")
    if not requested_ids:
        raise ValueError("Nu a fost selectată nicio cursă pentru realocare.")
    trips = list(
        Trip.objects.filter(id__in=requested_ids)
        .select_related("schedule__route", "driver__user", "bus")
        .order_by("date", "schedule__departure_time", "id")
    )
    if len(trips) != len(requested_ids):
        raise ValueError("Una dintre curse nu mai există.")
    for trip in trips:
        trip_start, _ = _trip_window(trip)
        if trip.status != "scheduled" or trip_start <= timezone.localtime():
            raise ValueError("Pot fi realocate doar curse programate care nu au plecat încă.")

    fallback_reason = None
    try:
        assignments, agent_rationale, attempts = _ask_driver_agent_for_distribution(trips)
        plan_source = "ai"
    except (requests.RequestException, ValueError, TypeError, json.JSONDecodeError) as exc:
        assignments = _find_driver_distribution(trips)
        agent_rationale = ""
        attempts = 0
        plan_source = "fallback"
        fallback_reason = str(exc)
    drivers = {
        driver.id: driver
        for driver in Employee.objects.filter(id__in=set(assignments.values())).select_related("user")
    }
    rows = [{
        "trip_id": trip.id,
        "route": trip.schedule.route.name,
        "date": trip.date.isoformat(),
        "departure_time": trip.schedule.departure_time.strftime("%H:%M"),
        "duration_hours": round(trip.schedule.route.duration.total_seconds() / 3600, 1),
        "current_driver": _driver_payload(trip.driver),
        "recommended_driver": _driver_payload(drivers[assignments[trip.id]]),
        "changed": trip.driver_id != assignments[trip.id],
    } for trip in trips]
    changed_count = sum(row["changed"] for row in rows)
    if plan_source == "ai":
        rationale = agent_rationale
        model = FLEET_AGENT_MODEL
    else:
        rationale = (
            "Modelul AI nu a furnizat un plan valid, astfel că sistemul de rezervă a calculat "
            "o distribuție fără suprapuneri și cu maximum 8 ore pe zi."
        )
        model = "planificator determinist de rezervă"

    token = signing.dumps({
        "assignments": assignments,
        "original_driver_ids": {trip.id: trip.driver_id for trip in trips},
        "source": plan_source,
        "model": model,
        "rationale": rationale,
    }, salt=DRIVER_REALLOCATION_PLAN_SALT)
    return {
        "token": token,
        "model": model,
        "source": plan_source,
        "attempts": attempts,
        "fallback_reason": fallback_reason,
        "rationale": rationale,
        "changed_count": changed_count,
        "assignments": rows,
    }


def decode_driver_reallocation_plan(token):
    return signing.loads(token, salt=DRIVER_REALLOCATION_PLAN_SALT, max_age=900)


def analyze_fleet(start_date=None, days=14):
    start_date = start_date or timezone.localdate()
    end_date = start_date + timedelta(days=max(1, min(days, 31)) - 1)
    trips = list(
        Trip.objects.filter(date__range=(start_date, end_date))
        .select_related("schedule__route", "bus", "driver__user")
        .annotate(ticket_count=Count("tickets"))
        .order_by("date", "schedule__departure_time", "id")
    )
    active_buses = list(Bus.objects.filter(status="active").order_by("capacity"))

    issues = []
    opportunities = []
    trip_rows = []
    resource_trips = defaultdict(list)

    for trip in trips:
        capacity = trip.bus.capacity if trip.bus else 0
        occupancy = round((trip.ticket_count / capacity) * 100, 1) if capacity else None
        recommended_bus = next(
            (bus for bus in active_buses if bus.capacity >= max(trip.ticket_count, 1)),
            None,
        )

        if not trip.bus:
            issues.append({
                "severity": "critical",
                "type": "missing_bus",
                "trip_id": trip.id,
                "title": "Cursă fără autobuz",
                "message": f"{trip.schedule.route.name} nu are autobuz alocat.",
            })
        elif trip.bus.status != "active":
            issues.append({
                "severity": "critical",
                "type": "unavailable_bus",
                "trip_id": trip.id,
                "title": "Autobuz indisponibil",
                "message": f"{trip.bus.license_plate} are statusul {trip.bus.get_status_display()}.",
            })

        if not trip.driver:
            issues.append({
                "severity": "critical",
                "type": "missing_driver",
                "trip_id": trip.id,
                "title": "Cursă fără șofer",
                "message": f"{trip.schedule.route.name} nu are șofer alocat.",
            })
        elif trip.driver.status != "active":
            issues.append({
                "severity": "critical",
                "type": "unavailable_driver",
                "trip_id": trip.id,
                "title": "Șofer indisponibil",
                "message": f"{_driver_payload(trip.driver)['name']} nu este activ.",
            })

        if occupancy is not None and occupancy >= 85:
            issues.append({
                "severity": "warning",
                "type": "high_occupancy",
                "trip_id": trip.id,
                "title": "Grad mare de ocupare",
                "message": f"Cursa are {trip.ticket_count}/{capacity} locuri rezervate ({occupancy}%).",
            })
        elif occupancy is not None and occupancy <= 20:
            issues.append({
                "severity": "info",
                "type": "low_occupancy",
                "trip_id": trip.id,
                "title": "Grad redus de ocupare",
                "message": f"Cursa are doar {trip.ticket_count}/{capacity} locuri rezervate ({occupancy}%).",
            })

        if trip.bus:
            resource_trips[("bus", trip.bus_id)].append(trip)
        if trip.driver:
            resource_trips[("driver", trip.driver_id)].append(trip)

        trip_rows.append({
            "id": trip.id,
            "route": trip.schedule.route.name,
            "date": trip.date.isoformat(),
            "departure_time": trip.schedule.departure_time.strftime("%H:%M"),
            "tickets": trip.ticket_count,
            "occupancy": occupancy,
            "bus": _bus_payload(trip.bus),
            "driver": _driver_payload(trip.driver),
            "recommended_bus": _bus_payload(recommended_bus),
        })

    for (resource_type, resource_id), assigned_trips in resource_trips.items():
        trips_by_date = defaultdict(list)
        for trip in assigned_trips:
            trips_by_date[trip.date].append(trip)

        for conflict_date, daily_trips in trips_by_date.items():
            first_trip = daily_trips[0]

            if resource_type == "driver":
                total_duration = sum(
                    (trip.schedule.route.duration for trip in daily_trips),
                    timedelta(),
                )
                total_hours = round(total_duration.total_seconds() / 3600, 1)
                if total_hours > MAX_DRIVER_HOURS_PER_DAY:
                    driver_name = _driver_payload(first_trip.driver)["name"]
                    issues.append({
                        "severity": "warning",
                        "type": "driver_daily_hours",
                        "trip_id": daily_trips[0].id,
                        "trip_ids": [trip.id for trip in daily_trips],
                        "affected_count": len(daily_trips),
                        "resource_id": resource_id,
                        "title": "Prag zilnic de condus depășit",
                        "message": (
                            f"{driver_name} are {total_hours:g} ore de curse alocate în "
                            f"{conflict_date:%d.%m.%Y}, peste pragul operațional de "
                            f"{MAX_DRIVER_HOURS_PER_DAY} ore. Verifică pauzele și realocarea."
                        ),
                    })

            conflicting_ids = set()
            for index, first in enumerate(daily_trips):
                for second in daily_trips[index + 1:]:
                    if _overlaps(first, second):
                        conflicting_ids.update((first.id, second.id))

            if not conflicting_ids:
                continue

            if resource_type == "bus":
                resource_name = first_trip.bus.license_plate
                title = "Conflict de autobuz"
            else:
                resource_name = _driver_payload(first_trip.driver)["name"]
                title = "Conflict de șofer"
            sorted_ids = sorted(conflicting_ids)
            trip_labels = ", ".join(f"#{trip_id}" for trip_id in sorted_ids)
            issues.append({
                "severity": "critical",
                "type": f"{resource_type}_conflict",
                "trip_id": sorted_ids[0],
                "trip_ids": sorted_ids,
                "affected_count": len(sorted_ids),
                "resource_id": resource_id,
                "title": title,
                "message": (
                    f"{resource_name} are alocări suprapuse în {conflict_date:%d.%m.%Y} "
                    f"pentru cursele {trip_labels}."
                ),
            })

    merge_groups = defaultdict(list)
    for trip in trips:
        if trip.status != "scheduled":
            continue
        trip_start, _ = _trip_window(trip)
        if trip_start <= timezone.localtime():
            continue
        capacity = trip.bus.capacity if trip.bus else 0
        occupancy = (trip.ticket_count / capacity) * 100 if capacity else None
        if occupancy is not None and occupancy <= LOW_OCCUPANCY_MERGE_THRESHOLD:
            merge_groups[(trip.date, trip.schedule.route_id)].append(trip)

    used_trip_ids = set()
    largest_active_capacity = max((bus.capacity for bus in active_buses), default=0)
    for (merge_date, route_id), candidate_trips in merge_groups.items():
        candidate_trips.sort(key=lambda trip: trip.schedule.departure_time)
        for index, first in enumerate(candidate_trips):
            if first.id in used_trip_ids:
                continue
            first_start, _ = _trip_window(first)
            for second in candidate_trips[index + 1:]:
                if second.id in used_trip_ids:
                    continue
                second_start, _ = _trip_window(second)
                gap = second_start - first_start
                if gap > MAX_MERGE_DEPARTURE_GAP:
                    break
                combined_tickets = first.ticket_count + second.ticket_count
                recommended_bus = next(
                    (bus for bus in active_buses if bus.capacity >= max(combined_tickets, 1)),
                    None,
                )
                if not recommended_bus or combined_tickets > largest_active_capacity:
                    continue
                passenger_label = "pasager" if combined_tickets == 1 else "pasageri"
                opportunities.append({
                    "type": "merge_low_occupancy",
                    "title": "Combinare posibilă a două curse",
                    "trip_id": first.id,
                    "trip_ids": [first.id, second.id],
                    "route": first.schedule.route.name,
                    "date": merge_date.isoformat(),
                    "departure_times": [
                        first.schedule.departure_time.strftime("%H:%M"),
                        second.schedule.departure_time.strftime("%H:%M"),
                    ],
                    "combined_tickets": combined_tickets,
                    "recommended_bus": _bus_payload(recommended_bus),
                    "message": (
                        f"Cursele #{first.id} ({first.schedule.departure_time:%H:%M}) și "
                        f"#{second.id} ({second.schedule.departure_time:%H:%M}) au împreună "
                        f"{combined_tickets} {passenger_label}. Pot fi evaluate pentru combinare cu "
                        f"{recommended_bus.license_plate} ({recommended_bus.capacity} locuri)."
                    ),
                })
                used_trip_ids.update((first.id, second.id))
                break

    severity_order = {"critical": 0, "warning": 1, "info": 2}
    issues.sort(key=lambda item: (severity_order[item["severity"]], item["trip_id"]))
    counts = {
        "critical": sum(issue["severity"] == "critical" for issue in issues),
        "warning": sum(issue["severity"] == "warning" for issue in issues),
        "info": sum(issue["severity"] == "info" for issue in issues),
    }
    assigned_bus_ids = {trip.bus_id for trip in trips if trip.bus_id}
    assigned_driver_ids = {trip.driver_id for trip in trips if trip.driver_id}
    issue_groups = {
        "conflicts": [issue for issue in issues if issue["type"].endswith("_conflict")],
        "driver_hours": [issue for issue in issues if issue["type"] == "driver_daily_hours"],
        "resources": [
            issue for issue in issues
            if issue["type"] in {
                "missing_bus", "unavailable_bus", "missing_driver", "unavailable_driver"
            }
        ],
        "occupancy": [
            issue for issue in issues
            if issue["type"] in {"high_occupancy", "low_occupancy"}
        ],
    }

    return {
        "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
        "summary": {
            "trips": len(trips),
            "tickets": sum(trip.ticket_count for trip in trips),
            "active_buses": len(active_buses),
            "available_buses": sum(bus.id not in assigned_bus_ids for bus in active_buses),
            "active_drivers": Employee.objects.filter(position="driver", status="active").count(),
            "assigned_drivers": len(assigned_driver_ids),
            "opportunities": len(opportunities),
            **counts,
        },
        "issues": issues,
        "issue_groups": issue_groups,
        "opportunities": opportunities,
        "trips": trip_rows,
    }


def deterministic_advice(analysis):
    issues = analysis["issues"]
    opportunities = analysis.get("opportunities", [])
    if not issues and not opportunities:
        return (
            "Nu am detectat probleme pentru perioada analizată. Alocările pot fi păstrate "
            "și monitorizate pe măsură ce apar rezervări noi. Orice modificare rămâne "
            "confirmată manual de manager."
        )

    critical = [issue for issue in issues if issue["severity"] == "critical"]
    warnings = [issue for issue in issues if issue["severity"] == "warning"]
    lines = []
    if critical:
        lines.append(f"Prioritatea imediată este rezolvarea celor {len(critical)} probleme critice.")
        lines.extend(f"• {issue['title']}: {issue['message']}" for issue in critical[:3])
    if warnings:
        lines.append(f"Apoi verifică cele {len(warnings)} curse cu risc operațional sau ocupare mare.")
        lines.extend(f"• {issue['title']}: {issue['message']}" for issue in warnings[:2])
    if opportunities:
        lines.append(f"Există {len(opportunities)} oportunități de optimizare care merită simulate.")
        lines.extend(f"• {item['title']}: {item['message']}" for item in opportunities[:2])
    lines.append("Orice schimbare de autobuz sau șofer trebuie confirmată manual de manager.")
    return "\n".join(lines)


def ask_fleet_agent(question, analysis):
    system_prompt = """
Ești agentul AutoTrans pentru optimizarea flotei. Răspunzi în limba română.
Folosește exclusiv datele JSON primite. Nu inventa autobuze, șoferi, curse sau cifre.
Prioritizează alertele operaționale, nu frecvența sau popularitatea rutelor:
1) conflicte și resurse indisponibile, 2) resurse lipsă, 3) ocupare mare,
4) depășirea pragului zilnic de 8 ore, 5) oportunitățile de combinare a curselor
slab ocupate. Menționează cursele și resursele din alerte. Oferă recomandări
scurte, explicate și spune clar că managerul trebuie să confirme manual orice modificare.
"""
    relevant_trips = [
        trip for trip in analysis["trips"]
        if not trip["bus"] or not trip["driver"] or (trip["occupancy"] or 0) >= 85
    ][:12]
    compact_analysis = {
        "period": analysis["period"],
        "summary": analysis["summary"],
        "priority_issues": [
            {
                "severity": issue["severity"],
                "type": issue["type"],
                "trip_id": issue["trip_id"],
                "trip_ids": issue.get("trip_ids", [issue["trip_id"]]),
                "title": issue["title"],
                "message": issue["message"],
            }
            for issue in analysis["issues"][:12]
        ],
        "optimization_opportunities": analysis.get("opportunities", [])[:8],
        "relevant_trips": relevant_trips,
    }
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": FLEET_AGENT_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"DATE:\n{json.dumps(compact_analysis, ensure_ascii=False)}\n\nÎNTREBARE:\n{question}"},
                ],
                "stream": False,
                "options": {"temperature": 0.1, "num_ctx": 4096, "num_predict": 350},
            },
            timeout=90,
        )
        response.raise_for_status()
        answer = response.json().get("message", {}).get("content", "").strip()
        if answer:
            return {"answer": answer, "model": FLEET_AGENT_MODEL, "fallback": False}
    except (requests.RequestException, ValueError, TypeError):
        pass
    return {
        "answer": deterministic_advice(analysis),
        "model": "analiză deterministă",
        "fallback": True,
    }
