import os
import django
from datetime import date, time, timedelta
from django.utils import timezone
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Bus_Fleet_Manager.settings')
django.setup()

from core.models import User, Employee, Bus, Station, Route, RouteStation, RouteSchedule, Trip

def add_routes():
    print("--- Adăugăm rute noi ---")
    
    # Recuperăm stațiile existente
    st_buc = Station.objects.get(name="București (Autogara Rahova)")
    st_alex = Station.objects.get(name="Alexandria (Centru)")
    st_rosiori = Station.objects.get(name="Roșiorii de Vede")
    st_pitesti = Station.objects.get(name="Pitești (Autogara Sud)")
    st_slatina = Station.objects.get(name="Slatina (Centru)")
    st_craiova = Station.objects.get(name="Craiova (Autogara Nord)")
    
    # Recuperăm șoferi și autobuze
    soferi = list(Employee.objects.filter(position="driver"))
    buses = list(Bus.objects.filter(status="active"))

    # --- RUTA 3: Alexandria -> Roșiorii -> Pitești ---
    r3 = Route.objects.create(name="Alexandria - Pitești", total_distance=110.0, duration=timedelta(hours=2, minutes=30))
    RouteStation.objects.create(route=r3, station=st_alex, order=1, time_from_start=timedelta(0), distance_from_start=0)
    RouteStation.objects.create(route=r3, station=st_rosiori, order=2, time_from_start=timedelta(minutes=45), distance_from_start=35)
    RouteStation.objects.create(route=r3, station=st_pitesti, order=3, time_from_start=timedelta(hours=2, minutes=30), distance_from_start=110)

    # --- RUTA 4: București -> Slatina -> Craiova ---
    r4 = Route.objects.create(name="București - Craiova", total_distance=230.0, duration=timedelta(hours=4))
    RouteStation.objects.create(route=r4, station=st_buc, order=1, time_from_start=timedelta(0), distance_from_start=0)
    RouteStation.objects.create(route=r4, station=st_slatina, order=2, time_from_start=timedelta(hours=2, minutes=30), distance_from_start=150)
    RouteStation.objects.create(route=r4, station=st_craiova, order=3, time_from_start=timedelta(hours=4), distance_from_start=230)

    print("--- Generăm Orare și Curse ---")
    today = timezone.now().date()
    
    for r in [r3, r4]:
        # Orare zilnice la 09:00 și 16:00
        for day in range(7):
            s1 = RouteSchedule.objects.create(route=r, day_of_week=day, departure_time=time(9, 0))
            s2 = RouteSchedule.objects.create(route=r, day_of_week=day, departure_time=time(16, 0))
            
            # Generăm curse pentru fiecare zi din săptămâna viitoare
            current_date = today + timedelta(days=(day - today.weekday()) % 7)
            if current_date < today: current_date += timedelta(days=7)
            
            for s in [s1, s2]:
                Trip.objects.create(
                    schedule=s,
                    date=current_date,
                    bus=buses[2 % len(buses)] if r == r3 else buses[1 % len(buses)],
                    driver=soferi[2 % len(soferi)] if r == r3 else soferi[3 % len(soferi)],
                    status='scheduled'
                )

    print("--- RUTE ADĂUGATE CU SUCCES! ---")

if __name__ == '__main__':
    add_routes()
