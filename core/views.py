from django.shortcuts import render
import json
from .models import Station, Route, RouteStation
from django.db.models import Q
from django.http import JsonResponse

def index(request):
    # ... (codul anterior neschimbat)
    ruta_obj = Route.objects.first()
    statii_data = []
    if ruta_obj:
        route_stations = RouteStation.objects.filter(route=ruta_obj).order_by('order')
        for rs in route_stations:
            statii_data.append({
                "id": rs.station.id,
                "nume": rs.station.name,
                "lat": rs.station.latitude,
                "lng": rs.station.longitude
            })
    context = {
        'statii_json': json.dumps(statii_data),
        'ruta_obj': ruta_obj
    }
    return render(request, "core/index.html", context)

def route_search(request):
    departure = request.GET.get('departure')
    arrival = request.GET.get('arrival')
    
    routes_found = []
    
    if departure and arrival:
        routes_with_departure = RouteStation.objects.filter(station_id=departure)
        for rs_dep in routes_with_departure:
            rs_arr = RouteStation.objects.filter(
                route=rs_dep.route, 
                station_id=arrival, 
                order__gt=rs_dep.order
            ).first()
            if rs_arr:
                routes_found.append({
                    'route': rs_dep.route,
                    'departure_time': rs_dep.departure_time,
                    'arrival_time': rs_arr.departure_time,
                })

    stations = Station.objects.all()
    context = {
        'stations': stations,
        'routes': routes_found,
        'departure': departure,
        'arrival': arrival,
    }
    return render(request, "core/rute.html", context)

def get_arrival_counts(request):
    departure_id = request.GET.get('departure_id')
    counts = {}
    if departure_id:
        # Găsim toate aparițiile stației de plecare în rute
        rs_deps = RouteStation.objects.filter(station_id=departure_id)
        for rs_dep in rs_deps:
            # Pentru fiecare rută care trece prin plecare, vedem ce stații urmează
            later_stations = RouteStation.objects.filter(
                route=rs_dep.route,
                order__gt=rs_dep.order
            )
            for ls in later_stations:
                sid = ls.station_id
                counts[sid] = counts.get(sid, 0) + 1
    return JsonResponse(counts)
