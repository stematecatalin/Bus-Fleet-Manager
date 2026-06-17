import random
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import (
    Bus,
    ChatMessage,
    ContactMessage,
    Employee,
    Route,
    RouteSchedule,
    RouteStation,
    Station,
    Ticket,
    Trip,
    User,
)


class Command(BaseCommand):
    help = "Resetează datele demo, păstrează un admin și generează o flotă realistă."

    def add_arguments(self, parser):
        parser.add_argument("--admin-email", default="admin@autotrans.ro")
        parser.add_argument("--admin-password", default="adminpassword")
        parser.add_argument("--driver-password", default="soferpassword")
        parser.add_argument("--days", type=int, default=14)

    @transaction.atomic
    def handle(self, *args, **options):
        admin_email = options["admin_email"]
        days = max(7, min(options["days"], 31))
        admin_user, _ = User.objects.get_or_create(
            email=admin_email,
            defaults={
                "first_name": "Admin",
                "last_name": "AutoTrans",
                "phone_number": "0700000000",
            },
        )

        admin_user.set_password(options["admin_password"])
        admin_user.is_staff = True
        admin_user.is_superuser = True
        admin_user.save(update_fields=["password", "is_staff", "is_superuser"])

        self._clear_operational_data(admin_user)
        stations = self._create_stations()
        routes = self._create_routes(stations)
        buses = self._create_buses()
        drivers = self._create_drivers(options["driver_password"])
        trips = self._create_trips(routes, buses, drivers, days)
        self._create_tickets(trips, admin_user)
        scenarios = self._inject_agent_scenarios(trips, buses, drivers)

        self.stdout.write(self.style.SUCCESS("Baza demo realistă a fost generată."))
        self.stdout.write(f"Admin păstrat: {admin_user.email}")
        self.stdout.write(
            f"{len(stations)} stații, {len(routes)} rute, {len(buses)} autobuze, "
            f"{len(drivers)} șoferi, {len(trips)} curse și {Ticket.objects.count()} bilete."
        )
        for scenario in scenarios:
            self.stdout.write(f"- {scenario}")

    def _clear_operational_data(self, admin_user):
        Ticket.objects.all().delete()
        Trip.objects.all().delete()
        RouteSchedule.objects.all().delete()
        RouteStation.objects.all().delete()
        Route.objects.all().delete()
        Station.objects.all().delete()
        Bus.objects.all().delete()
        Employee.objects.all().delete()
        ChatMessage.objects.all().delete()
        ContactMessage.objects.all().delete()
        User.objects.exclude(id=admin_user.id).delete()

    def _create_stations(self):
        station_data = [
            ("Alexandria (Centru)", 43.9686, 25.3333),
            ("București (Autogara Rahova)", 44.3951, 26.0428),
            ("Turnu Măgurele (Port)", 43.7469, 24.8685),
            ("Roșiorii de Vede", 44.1111, 24.9928),
            ("Pitești (Autogara Sud)", 44.8565, 24.8697),
            ("Slatina (Centru)", 44.4297, 24.3643),
            ("Craiova (Autogara Nord)", 44.3302, 23.7949),
            ("Giurgiu (Autogară)", 43.9037, 25.9699),
            ("Brașov (Autogara 2)", 45.6579, 25.6012),
        ]
        return {
            name: Station.objects.create(name=name, latitude=lat, longitude=lon)
            for name, lat, lon in station_data
        }

    def _create_routes(self, stations):
        route_specs = [
            ("Alexandria - București", 92, 105, [
                ("Alexandria (Centru)", 0, 0),
                ("București (Autogara Rahova)", 105, 92),
            ], [time(6, 30), time(10, 0), time(12, 0), time(16, 30)], Decimal("42.00")),
            ("București - Alexandria", 92, 105, [
                ("București (Autogara Rahova)", 0, 0),
                ("Alexandria (Centru)", 105, 92),
            ], [time(7, 0), time(13, 30), time(18, 30)], Decimal("42.00")),
            ("Alexandria - Turnu Măgurele", 49, 90, [
                ("Alexandria (Centru)", 0, 0),
                ("Turnu Măgurele (Port)", 90, 49),
            ], [time(6, 30), time(14, 0)], Decimal("25.00")),
            ("Turnu Măgurele - Alexandria", 49, 90, [
                ("Turnu Măgurele (Port)", 0, 0),
                ("Alexandria (Centru)", 90, 49),
            ], [time(9, 0), time(17, 0)], Decimal("25.00")),
            ("Alexandria - Pitești", 111, 150, [
                ("Alexandria (Centru)", 0, 0),
                ("Roșiorii de Vede", 45, 35),
                ("Pitești (Autogara Sud)", 150, 111),
            ], [time(8, 0), time(15, 30)], Decimal("55.00")),
            ("Pitești - Alexandria", 111, 150, [
                ("Pitești (Autogara Sud)", 0, 0),
                ("Roșiorii de Vede", 105, 76),
                ("Alexandria (Centru)", 150, 111),
            ], [time(7, 30), time(16, 0)], Decimal("55.00")),
            ("București - Craiova", 230, 240, [
                ("București (Autogara Rahova)", 0, 0),
                ("Slatina (Centru)", 150, 150),
                ("Craiova (Autogara Nord)", 240, 230),
            ], [time(8, 0), time(16, 0)], Decimal("85.00")),
            ("Craiova - București", 230, 240, [
                ("Craiova (Autogara Nord)", 0, 0),
                ("Slatina (Centru)", 90, 80),
                ("București (Autogara Rahova)", 240, 230),
            ], [time(7, 0), time(15, 30)], Decimal("85.00")),
            ("București - Giurgiu", 65, 75, [
                ("București (Autogara Rahova)", 0, 0),
                ("Giurgiu (Autogară)", 75, 65),
            ], [time(7, 30), time(12, 30), time(18, 0)], Decimal("32.00")),
            ("București - Brașov", 170, 180, [
                ("București (Autogara Rahova)", 0, 0),
                ("Brașov (Autogara 2)", 180, 170),
            ], [time(6, 0), time(14, 30)], Decimal("72.00")),
        ]
        result = []
        for name, distance, minutes, stops, departures, price in route_specs:
            route = Route.objects.create(
                name=name,
                total_distance=distance,
                duration=timedelta(minutes=minutes),
            )
            for order, (station_name, offset, station_distance) in enumerate(stops, start=1):
                RouteStation.objects.create(
                    route=route,
                    station=stations[station_name],
                    order=order,
                    time_from_start=timedelta(minutes=offset),
                    distance_from_start=station_distance,
                )
            route.demo_departures = departures
            route.demo_price = price
            result.append(route)
        return result

    def _create_buses(self):
        specs = [
            ("WDBBUS00000000001", "Mercedes", "Sprinter", "TR-10-ATR", 19, "active"),
            ("WDBBUS00000000002", "Iveco", "Daily", "TR-11-ATR", 22, "active"),
            ("WDBBUS00000000003", "Isuzu", "Novo", "TR-12-ATR", 29, "active"),
            ("WDBBUS00000000004", "Otokar", "Navigo", "TR-13-ATR", 35, "active"),
            ("WDBBUS00000000005", "Mercedes", "Tourismo", "B-40-ATR", 49, "active"),
            ("WDBBUS00000000006", "Setra", "S 415", "B-41-ATR", 53, "active"),
            ("WDBBUS00000000007", "MAN", "Lion's Coach", "B-42-ATR", 55, "active"),
            ("WDBBUS00000000008", "Volvo", "9700", "B-43-ATR", 51, "active"),
            ("WDBBUS00000000009", "Scania", "Touring", "B-90-SRV", 49, "service"),
            ("WDBBUS00000000010", "Neoplan", "Tourliner", "B-91-DEF", 52, "defective"),
        ]
        return [
            Bus.objects.create(
                vin=vin, brand=brand, model=model, license_plate=plate,
                capacity=capacity, status=status,
            )
            for vin, brand, model, plate, capacity, status in specs
        ]

    def _create_drivers(self, driver_password):
        names = [
            ("Andrei", "Popescu", 4.9), ("Mihai", "Ionescu", 4.8),
            ("Cristian", "Dumitru", 4.7), ("Sorin", "Marin", 4.6),
            ("Daniel", "Stan", 4.8), ("Radu", "Georgescu", 4.5),
            ("Florin", "Tudor", 4.7), ("Adrian", "Matei", 4.6),
            ("Nicolae", "Preda", 4.4), ("Vlad", "Enache", 4.9),
            ("Marian", "Stoica", 4.3), ("Lucian", "Ilie", 4.5),
        ]
        drivers = []
        for index, (first_name, last_name, rating) in enumerate(names, start=1):
            user = User.objects.create_user(
                email=f"sofer{index}@autotrans.demo",
                password=driver_password,
                first_name=first_name,
                last_name=last_name,
                phone_number=f"0720{index:06d}",
            )
            drivers.append(Employee.objects.create(
                user=user,
                cnp=f"18001010000{index:02d}",
                position="driver",
                hire_date=date(2017 + index % 6, (index % 12) + 1, 1),
                salary=Decimal("5200.00") + index * 85,
                rating=rating,
                license_number=f"TR-{1000 + index}",
                status="active" if index <= 10 else ("vacation" if index == 11 else "medical_leave"),
            ))
        return drivers

    def _create_trips(self, routes, buses, drivers, days):
        active_buses = [bus for bus in buses if bus.status == "active"]
        active_drivers = [driver for driver in drivers if driver.status == "active"]
        start_date = timezone.localdate()
        bus_daily = defaultdict(list)
        driver_daily = defaultdict(list)
        trips = []

        for day_offset in range(days):
            trip_date = start_date + timedelta(days=day_offset)
            day_specs = []
            for route in routes:
                for departure in route.demo_departures:
                    day_specs.append((departure, route))
            day_specs.sort(key=lambda item: item[0])
            for departure, route in day_specs:
                schedule, _ = RouteSchedule.objects.get_or_create(
                    route=route,
                    day_of_week=trip_date.weekday(),
                    departure_time=departure,
                )
                start = datetime.combine(trip_date, departure)
                end = start + route.duration
                bus = self._pick_resource(active_buses, bus_daily, trip_date, start, end)
                driver = self._pick_driver(active_drivers, driver_daily, trip_date, start, end, route.duration)
                trip = Trip.objects.create(
                    schedule=schedule,
                    date=trip_date,
                    bus=bus,
                    driver=driver,
                    status="scheduled",
                )
                bus_daily[(bus.id, trip_date)].append((start, end, route.duration))
                driver_daily[(driver.id, trip_date)].append((start, end, route.duration))
                trip.demo_price = route.demo_price
                trips.append(trip)
        return trips

    def _pick_resource(self, resources, assignments, trip_date, start, end):
        valid = []
        for resource in resources:
            daily = assignments[(resource.id, trip_date)]
            if not any(start < assigned_end and assigned_start < end for assigned_start, assigned_end, _ in daily):
                valid.append((len(daily), resource.capacity, resource))
        if not valid:
            raise CommandError("Flota demo nu are suficiente autobuze pentru orarul generat.")
        return min(valid, key=lambda item: (item[0], item[1]))[2]

    def _pick_driver(self, drivers, assignments, trip_date, start, end, duration):
        valid = []
        for driver in drivers:
            daily = assignments[(driver.id, trip_date)]
            total = sum((item[2] for item in daily), timedelta())
            overlap = any(start < assigned_end and assigned_start < end for assigned_start, assigned_end, _ in daily)
            if not overlap and total + duration <= timedelta(hours=8):
                valid.append((total, len(daily), -driver.rating, driver))
        if not valid:
            raise CommandError("Nu există suficienți șoferi pentru orarul demo generat.")
        return min(valid, key=lambda item: (item[0], item[1], item[2]))[3]

    def _create_tickets(self, trips, admin_user):
        rng = random.Random(20260615)
        passenger_names = [
            "Ana Popa", "Maria Dinu", "Ioana Radu", "Elena Matei", "Marius Stan",
            "George Pavel", "Diana Tudor", "Alexandru Marin", "Irina Ene", "Paul Preda",
            "Cristina Ilie", "Robert Stoica", "Bianca Neagu", "Vasile Dumitru",
        ]
        tickets = []
        for index, trip in enumerate(trips):
            route_stations = list(trip.schedule.route.stations.select_related("station"))
            capacity = trip.bus.capacity
            pattern = index % 10
            if pattern in (0, 1):
                count = rng.randint(1, max(2, int(capacity * 0.16)))
            elif pattern == 2:
                count = rng.randint(int(capacity * 0.82), int(capacity * 0.94))
            else:
                count = rng.randint(max(3, int(capacity * 0.35)), max(4, int(capacity * 0.72)))
            for ticket_index in range(count):
                start_index = rng.randrange(0, max(1, len(route_stations) - 1))
                end_index = rng.randrange(start_index + 1, len(route_stations))
                tickets.append(Ticket(
                    client=admin_user,
                    trip=trip,
                    start_station=route_stations[start_index].station,
                    end_station=route_stations[end_index].station,
                    passenger_name=passenger_names[(index + ticket_index) % len(passenger_names)],
                    price=trip.demo_price,
                    is_boarded=False,
                ))
        Ticket.objects.bulk_create(tickets, batch_size=500)

    def _inject_agent_scenarios(self, trips, buses, drivers):
        future = sorted(
            [trip for trip in trips if trip.date > timezone.localdate()],
            key=lambda trip: (trip.date, trip.schedule.departure_time, trip.id),
        )
        by_date = defaultdict(list)
        for trip in future:
            by_date[trip.date].append(trip)
        dates = sorted(by_date)
        if len(dates) < 5:
            raise CommandError("Sunt necesare cel puțin 5 zile viitoare pentru scenariile demo.")

        scenarios = []
        service_bus = next(bus for bus in buses if bus.status == "service")
        defective_bus = next(bus for bus in buses if bus.status == "defective")
        vacation_driver = next(driver for driver in drivers if driver.status == "vacation")
        medical_driver = next(driver for driver in drivers if driver.status == "medical_leave")

        service_trip = by_date[dates[0]][-1]
        service_trip.bus = service_bus
        service_trip.save(update_fields=["bus"])
        scenarios.append(f"autobuz în service pe cursa #{service_trip.id}")

        missing_bus_trip = by_date[dates[1]][-1]
        missing_bus_trip.bus = defective_bus
        missing_bus_trip.save(update_fields=["bus"])
        scenarios.append(f"autobuz defect pe cursa #{missing_bus_trip.id}")

        overlap_candidates = by_date[dates[2]][:]
        conflict_pair = self._first_overlapping_pair(overlap_candidates)
        conflict_pair[1].bus = conflict_pair[0].bus
        conflict_pair[1].save(update_fields=["bus"])
        scenarios.append(
            f"conflict de autobuz între cursele #{conflict_pair[0].id} și #{conflict_pair[1].id}"
        )

        unavailable_driver_trip = by_date[dates[0]][-2]
        unavailable_driver_trip.driver = vacation_driver
        unavailable_driver_trip.save(update_fields=["driver"])
        scenarios.append(f"șofer în concediu pe cursa #{unavailable_driver_trip.id}")

        missing_driver_trip = by_date[dates[1]][-2]
        missing_driver_trip.driver = medical_driver
        missing_driver_trip.save(update_fields=["driver"])
        scenarios.append(f"șofer în concediu medical pe cursa #{missing_driver_trip.id}")

        driver_conflict_trips = self._overlapping_group(by_date[dates[3]], size=3)
        conflict_driver = drivers[0]
        for trip in driver_conflict_trips:
            trip.driver = conflict_driver
            trip.save(update_fields=["driver"])
        scenarios.append(
            "conflict multiplu de șofer pe cursele "
            + ", ".join(f"#{trip.id}" for trip in driver_conflict_trips)
        )

        long_trips = [
            trip for trip in by_date[dates[4]]
            if trip.schedule.route.duration >= timedelta(hours=3)
        ][:3]
        hours_driver = drivers[1]
        for trip in long_trips:
            trip.driver = hours_driver
            trip.save(update_fields=["driver"])
        scenarios.append(
            f"program de peste 8 ore pentru {hours_driver.user.first_name} {hours_driver.user.last_name}"
        )

        merge_route_trips = [
            trip for trip in by_date[dates[5]]
            if trip.schedule.route.name == "Alexandria - București"
            and trip.schedule.departure_time in (time(10, 0), time(12, 0))
        ]
        for trip in merge_route_trips:
            excess_ticket_ids = list(
                trip.tickets.order_by("id").values_list("id", flat=True)[3:]
            )
            Ticket.objects.filter(id__in=excess_ticket_ids).delete()
        scenarios.append(
            "două curse apropiate și slab ocupate pentru testarea combinării: "
            + ", ".join(f"#{trip.id}" for trip in merge_route_trips)
        )
        return scenarios

    def _first_overlapping_pair(self, trips):
        for index, first in enumerate(trips):
            first_start = datetime.combine(first.date, first.schedule.departure_time)
            first_end = first_start + first.schedule.route.duration
            for second in trips[index + 1:]:
                second_start = datetime.combine(second.date, second.schedule.departure_time)
                second_end = second_start + second.schedule.route.duration
                if first_start < second_end and second_start < first_end:
                    return first, second
        raise CommandError("Nu am găsit două curse suprapuse pentru scenariul demo.")

    def _overlapping_group(self, trips, size):
        for anchor in trips:
            anchor_start = datetime.combine(anchor.date, anchor.schedule.departure_time)
            anchor_end = anchor_start + anchor.schedule.route.duration
            group = []
            for trip in trips:
                start = datetime.combine(trip.date, trip.schedule.departure_time)
                end = start + trip.schedule.route.duration
                if anchor_start < end and start < anchor_end:
                    group.append(trip)
                if len(group) == size:
                    return group
        raise CommandError("Nu am găsit suficiente curse suprapuse pentru scenariul demo.")
