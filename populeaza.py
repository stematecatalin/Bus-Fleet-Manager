import os
import django
from datetime import date, datetime, time, timedelta
from django.utils import timezone


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Bus_Fleet_Manager.settings')
django.setup()

from core.models import User, Employee, Bus, Station, Route, RouteStation, RouteSchedule, Trip, Ticket

def populate():
    # Curățăm datele vechi
    Ticket.objects.all().delete()
    Trip.objects.all().delete()
    RouteSchedule.objects.all().delete()
    RouteStation.objects.all().delete()
    Route.objects.all().delete()
    Employee.objects.all().delete()
    User.objects.all().delete()
    Bus.objects.all().delete()
    Station.objects.all().delete()

    print("--- Pasul 1: Creăm utilizatori ---")
    
    # Superuser
    admin_user = User.objects.create_superuser(
        email="admin@autotrans.ro",
        password="adminpassword",
        first_name="Admin",
        last_name="System",
        phone_number="0000000000"
    )

    # Angajati
    soferi_data = [
        ("rmihalache@autotrans.ro", "Radu", "Mihalache", "0741724491", "1800507411235", "B0099221"),
        ("mirceadumitrache@autotrans.ro", "Mircea", "Dumitrache", "0762784699", "1850202424568", "B1122334"),
        ("vasilerece@autotrans.ro", "Vasile", "Rece", "0788716637", "1921215127891", "B5566778"),
        ("tomoescumarius@autotrans.ro", "Marius", "Tomoescu", "0725811364", "1980430351112", "CJ4581375"),
    ]

    soferi = []
    for email, fn, ln, ph, cnp, lic in soferi_data:
        u = User.objects.create_user(email=email, password="password123", first_name=fn, last_name=ln, phone_number=ph)
        e = Employee.objects.create(user=u, cnp=cnp, position="driver", hire_date=date(2020, 1, 1), salary=4000, status="active", license_number=lic)
        soferi.append(e)

    # Autobuze
    buses = [
        Bus.objects.create(vin="VIN1", brand="Mercedes-Benz", model="Citaro", license_plate="B-01-ATT", capacity=70, status="active"),
        Bus.objects.create(vin="VIN2", brand="Volvo", model="9700", license_plate="B-02-ATT", capacity=50, status="active"),
        Bus.objects.create(vin="VIN3", brand="Scania", model="Touring", license_plate="B-03-ATT", capacity=55, status="active"),
    ]

    # Stații
    st_buc = Station.objects.create(name="București (Autogara Rahova)", latitude=44.3951, longitude=26.0428)
    st_alex = Station.objects.create(name="Alexandria (Centru)", latitude=43.9686, longitude=25.3333)
    st_turnu = Station.objects.create(name="Turnu Măgurele (Port)", latitude=43.7486, longitude=24.8703)
    st_pitesti = Station.objects.create(name="Pitești (Autogara Sud)", latitude=44.8565, longitude=24.8697)

    print("--- Pasul 2: Creăm Rute (Șabloane) ---")
    
    r1 = Route.objects.create(name="București - Turnu Măgurele", total_distance=150.0, duration=timedelta(hours=3))
    r2 = Route.objects.create(name="Turnu Măgurele - București", total_distance=150.0, duration=timedelta(hours=3))
    
    # Stații pe rută
    RouteStation.objects.create(route=r1, station=st_buc, order=1, time_from_start=timedelta(0))
    RouteStation.objects.create(route=r1, station=st_alex, order=2, time_from_start=timedelta(hours=1, minutes=30))
    RouteStation.objects.create(route=r1, station=st_turnu, order=3, time_from_start=timedelta(hours=3))

    RouteStation.objects.create(route=r2, station=st_turnu, order=1, time_from_start=timedelta(0))
    RouteStation.objects.create(route=r2, station=st_alex, order=2, time_from_start=timedelta(hours=1, minutes=30))
    RouteStation.objects.create(route=r2, station=st_buc, order=3, time_from_start=timedelta(hours=3))

    print("--- Pasul 3: Creăm Orare (Schedules) ---")
    
    # R1 zilnic la 08:00 și 14:00
    schedules = []
    for day in range(7):
        schedules.append(RouteSchedule.objects.create(route=r1, day_of_week=day, departure_time=time(8, 0)))
        schedules.append(RouteSchedule.objects.create(route=r1, day_of_week=day, departure_time=time(14, 0)))
        schedules.append(RouteSchedule.objects.create(route=r2, day_of_week=day, departure_time=time(11, 0)))
        schedules.append(RouteSchedule.objects.create(route=r2, day_of_week=day, departure_time=time(18, 0)))

    print("--- Pasul 4: Generăm Curse (Trips) pentru azi și mâine ---")
    
    today = timezone.now().date()
    tomorrow = today + timedelta(days=1)
    
    for d in [today, tomorrow]:
        day_scheds = RouteSchedule.objects.filter(day_of_week=d.weekday())
        for s in day_scheds:
            Trip.objects.create(
                schedule=s,
                date=d,
                bus=buses[0] if s.route == r1 else buses[1],
                driver=soferi[0] if s.route == r1 else soferi[1],
                status='scheduled'
            )

    print("--- Pasul 5: Creăm bilete de test ---")
    
    client1 = User.objects.create_user(email="client@test.ro", password="password123", first_name="Ion", last_name="Client")
    
    # Luăm prima cursă de azi
    trip1 = Trip.objects.filter(date=today).first()
    if trip1:
        Ticket.objects.create(
            client=client1,
            trip=trip1,
            passenger_name="Ion Client",
            price=Decimal("75.00")
        )

    print("--- POPULARE REUȘITĂ! ---")
    print(f"Superuser: admin@autotrans.ro / adminpassword")

from decimal import Decimal

if __name__ == '__main__':
    populate()