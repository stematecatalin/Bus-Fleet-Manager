import os
import django
from datetime import date, datetime, time, timedelta
from django.utils import timezone
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Bus_Fleet_Manager.settings')
django.setup()

from core.models import User, Employee, Bus, Station, Route, RouteStation, RouteSchedule, Trip, Ticket
try:
    from allauth.account.models import EmailAddress
except ImportError:
    EmailAddress = None

def create_verified_user(email, password, first_name, last_name, phone_number, is_superuser=False):
    if is_superuser:
        user = User.objects.create_superuser(
            email=email, password=password, first_name=first_name, 
            last_name=last_name, phone_number=phone_number
        )
    else:
        user = User.objects.create_user(
            email=email, password=password, first_name=first_name, 
            last_name=last_name, phone_number=phone_number
        )
    
    if EmailAddress:
        EmailAddress.objects.create(
            user=user,
            email=email,
            verified=True,
            primary=True
        )
    return user

def populate():
    # Curățăm datele vechi
    if EmailAddress:
        EmailAddress.objects.all().delete()
    Ticket.objects.all().delete()
    Trip.objects.all().delete()
    RouteSchedule.objects.all().delete()
    RouteStation.objects.all().delete()
    Route.objects.all().delete()
    Employee.objects.all().delete()
    User.objects.all().delete()
    Bus.objects.all().delete()
    Station.objects.all().delete()

    print("--- Pasul 1: Creăm utilizatori verificați ---")
    
    # Superuser
    admin_u = create_verified_user(
        email="admin@autotrans.ro",
        password="adminpassword",
        first_name="Admin",
        last_name="System",
        phone_number="0000000000",
        is_superuser=True
    )

    # Șofer Test
    sofer_u = create_verified_user(
        email="rmihalache@autotrans.ro", 
        password="password123", 
        first_name="Radu", 
        last_name="Mihalache", 
        phone_number="0741724491"
    )
    sofer = Employee.objects.create(
        user=sofer_u, 
        cnp="1800507411235", 
        position="driver", 
        hire_date=date(2020, 1, 1), 
        salary=4000, 
        status="active", 
        license_number="B0099221"
    )

    # Autobuze
    bus1 = Bus.objects.create(vin="VIN1", brand="Mercedes-Benz", model="Citaro", license_plate="B-01-ATT", capacity=70, status="active")
    bus2 = Bus.objects.create(vin="VIN2", brand="Volvo", model="9700", license_plate="B-02-ATT", capacity=50, status="active")

    # Stații
    st_buc = Station.objects.create(name="București (Autogara Rahova)", latitude=44.3951, longitude=26.0428)
    st_alex = Station.objects.create(name="Alexandria (Centru)", latitude=43.9686, longitude=25.3333)
    st_turnu = Station.objects.create(name="Turnu Măgurele (Port)", latitude=43.7486, longitude=24.8703)

    print("--- Pasul 2: Creăm Rute ---")
    r1 = Route.objects.create(name="București - Turnu Măgurele", total_distance=150.0, duration=timedelta(hours=3))
    r2 = Route.objects.create(name="Turnu Măgurele - București", total_distance=150.0, duration=timedelta(hours=3))
    
    for r, start, mid, end in [(r1, st_buc, st_alex, st_turnu), (r2, st_turnu, st_alex, st_buc)]:
        RouteStation.objects.create(route=r, station=start, order=1, time_from_start=timedelta(0), distance_from_start=0)
        RouteStation.objects.create(route=r, station=mid, order=2, time_from_start=timedelta(hours=1, minutes=30), distance_from_start=85)
        RouteStation.objects.create(route=r, station=end, order=3, time_from_start=timedelta(hours=3), distance_from_start=150)

    print("--- Pasul 3: Creăm Orare Dense ---")
    departure_times = [
        (r1, time(5, 0)),    (r2, time(8, 30)),
        (r1, time(12, 0)),   (r2, time(15, 30)),
        (r1, time(19, 0)),   (r2, time(20, 0)),
        (r1, time(21, 0)),   (r2, time(22, 0)),
        (r1, time(22, 30)),  (r2, time(23, 0)),
        (r1, time(23, 30)),  (r2, time(23, 55)),
    ]

    for day in range(7):
        for route, dep_time in departure_times:
            RouteSchedule.objects.get_or_create(route=route, day_of_week=day, departure_time=dep_time)

    print("--- Pasul 4: Generăm Curse ---")
    today = timezone.now().date()
    for i in range(7):
        current_date = today + timedelta(days=i)
        day_scheds = RouteSchedule.objects.filter(day_of_week=current_date.weekday())
        for s in day_scheds:
            trip = Trip.objects.create(
                schedule=s,
                date=current_date,
                bus=bus1 if s.route == r1 else bus2,
                driver=sofer,
                status='scheduled'
            )
            if current_date == today:
                Ticket.objects.create(
                    client=sofer_u, trip=trip, passenger_name="Ion Popescu", 
                    price=Decimal('42.50'), start_station=s.route.stations.first().station,
                    end_station=s.route.stations.last().station
                )
    print("--- POPULARE REUȘITĂ (CONTURI VERIFICATE)! ---")

if __name__ == '__main__':
    populate()
