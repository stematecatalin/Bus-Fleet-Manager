from django.shortcuts import render, redirect, get_object_or_404
import json
from .models import Station, Route, RouteStation, Ticket, RouteSchedule, Trip
from django.db.models import Q
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from decimal import Decimal
import qrcode
import io
from django.http import HttpResponse
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import landscape, A6
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os
from django.utils import timezone
from datetime import datetime, timedelta

# Înregistrăm un font care suportă diacritice (Arial este standard pe Windows)
try:
    font_path = "C:\\Windows\\Fonts\\arial.ttf"
    if os.path.exists(font_path):
        pdfmetrics.registerFont(TTFont('Arial', font_path))
        pdfmetrics.registerFont(TTFont('Arial-Bold', "C:\\Windows\\Fonts\\arialbd.ttf"))
        FONT_NAME = 'Arial'
        FONT_BOLD = 'Arial-Bold'
    else:
        FONT_NAME = 'Helvetica'
        FONT_BOLD = 'Helvetica-Bold'
except:
    FONT_NAME = 'Helvetica'
    FONT_BOLD = 'Helvetica-Bold'

from reportlab.lib.pagesizes import A4

import hmac
import hashlib
from django.conf import settings
from .forms import ContactForm

def contact(request):
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Mesajul tău a fost trimis cu succes! Te vom contacta în cel mai scurt timp.")
            return redirect('contact')
    else:
        form = ContactForm()
    
    return render(request, "core/contact.html", {"form": form})


@login_required
def generate_ticket_pdf(request, ticket_id):
    # Luăm biletul principal
    main_ticket = get_object_or_404(Ticket, id=ticket_id, client=request.user)
    
    # Grupăm biletele cumpărate în aceeași sesiune
    five_min_ago = main_ticket.purchase_date - timedelta(minutes=5)
    five_min_later = main_ticket.purchase_date + timedelta(minutes=5)
    
    tickets = Ticket.objects.filter(
        client=request.user, 
        trip=main_ticket.trip,
        purchase_date__range=(five_min_ago, five_min_later)
    ).order_by('id')

    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    PAGE_WIDTH, PAGE_HEIGHT = A4

    SITE_GREEN = colors.HexColor("#198754")

    def draw_single_ticket(canvas_obj, ticket, y_offset):
        security_token = f"{ticket.id}-{ticket.passenger_name}-{ticket.trip.id}-{settings.SECRET_KEY}"
        signature = hashlib.sha256(security_token.encode()).hexdigest()[:12].upper()
        
        t_width = PAGE_WIDTH - 20*mm
        t_height = (PAGE_HEIGHT / 2) - 10*mm
        x_start = 10*mm
        y_start = y_offset + 5*mm

        # Card
        canvas_obj.setStrokeColor(colors.lightgrey)
        canvas_obj.setFillColor(colors.white)
        canvas_obj.roundRect(x_start, y_start, t_width, t_height, 3*mm, fill=1, stroke=1)

        # Header
        h_height = 22*mm
        canvas_obj.setFillColor(SITE_GREEN)
        canvas_obj.roundRect(x_start, y_start + t_height - h_height, t_width, h_height, 3*mm, fill=1, stroke=0)
        canvas_obj.rect(x_start, y_start + t_height - h_height, t_width, 10*mm, fill=1, stroke=0)

        canvas_obj.setFillColor(colors.white)
        canvas_obj.setFont(FONT_BOLD, 24)
        canvas_obj.drawString(x_start + 8*mm, y_start + t_height - 15*mm, "AutoTrans")
        
        canvas_obj.setFont(FONT_NAME, 9)
        canvas_obj.drawRightString(x_start + t_width - 8*mm, y_start + t_height - 9*mm, "DOCUMENT DE CĂLĂTORIE")
        canvas_obj.setFont(FONT_BOLD, 12)
        canvas_obj.drawRightString(x_start + t_width - 8*mm, y_start + t_height - 16*mm, f"Serie: AT-{ticket.id:06d}")

        # Detalii Stânga
        canvas_obj.setFillColor(colors.black)
        
        # Pasager
        canvas_obj.setFont(FONT_NAME, 8)
        canvas_obj.setFillColor(colors.grey)
        canvas_obj.drawString(x_start + 10*mm, y_start + t_height - 35*mm, "PASAGER")
        canvas_obj.setFillColor(colors.black)
        canvas_obj.setFont(FONT_BOLD, 14)
        canvas_obj.drawString(x_start + 10*mm, y_start + t_height - 42*mm, ticket.passenger_name.upper())

        # Stații și Ore
        route = ticket.trip.schedule.route
        start_rs = RouteStation.objects.filter(route=route, station=ticket.start_station).first()
        end_rs = RouteStation.objects.filter(route=route, station=ticket.end_station).first()
        
        dep_name = ticket.start_station.name if ticket.start_station else "---"
        arr_name = ticket.end_station.name if ticket.end_station else "---"
        
        start_dt = datetime.combine(ticket.trip.date, ticket.trip.schedule.departure_time)
        dep_time = start_dt + (start_rs.time_from_start if start_rs else timedelta(0))
        arr_time = start_dt + (end_rs.time_from_start if end_rs else route.duration)

        canvas_obj.setFont(FONT_NAME, 8)
        canvas_obj.setFillColor(colors.grey)
        canvas_obj.drawString(x_start + 10*mm, y_start + t_height - 55*mm, f"PLECARE ({dep_time.strftime('%H:%M')})")
        canvas_obj.setFillColor(colors.black)
        canvas_obj.setFont(FONT_BOLD, 11)
        canvas_obj.drawString(x_start + 10*mm, y_start + t_height - 61*mm, dep_name)

        canvas_obj.setFont(FONT_NAME, 8)
        canvas_obj.setFillColor(colors.grey)
        canvas_obj.drawString(x_start + 10*mm, y_start + t_height - 73*mm, f"SOSIRE ({arr_time.strftime('%H:%M')})")
        canvas_obj.setFillColor(colors.black)
        canvas_obj.setFont(FONT_BOLD, 11)
        canvas_obj.drawString(x_start + 10*mm, y_start + t_height - 79*mm, arr_name)

        # Dată și Cursă
        canvas_obj.setFont(FONT_NAME, 8)
        canvas_obj.setFillColor(colors.grey)
        canvas_obj.drawString(x_start + 10*mm, y_start + t_height - 92*mm, "DATA CĂLĂTORIEI")
        canvas_obj.drawString(x_start + 65*mm, y_start + t_height - 92*mm, "CURSA")

        canvas_obj.setFillColor(colors.black)
        canvas_obj.setFont(FONT_BOLD, 11)
        canvas_obj.drawString(x_start + 10*mm, y_start + t_height - 98*mm, ticket.trip.date.strftime('%d.%m.%Y'))
        canvas_obj.drawString(x_start + 65*mm, y_start + t_height - 98*mm, f"NR. {ticket.trip.id}")

        # Preț
        canvas_obj.setFont(FONT_BOLD, 16)
        canvas_obj.setFillColor(SITE_GREEN)
        canvas_obj.drawString(x_start + 10*mm, y_start + 12*mm, f"PREȚ: {ticket.price} RON")
        
        # QR Code
        qr_data = f"AutoTrans|TID:{ticket.id}|TRIP:{ticket.trip.id}|NAME:{ticket.passenger_name}|SIG:{signature}"
        qr = qrcode.QRCode(version=1, box_size=8, border=1)
        qr.add_data(qr_data)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white")
        qr_buffer = io.BytesIO()
        qr_img.save(qr_buffer, format='PNG')
        qr_buffer.seek(0)

        qr_size = 50*mm
        qr_y = y_start + (t_height - h_height) / 2 - qr_size / 2 + 5*mm
        canvas_obj.drawImage(ImageReader(qr_buffer), x_start + t_width - 58*mm, qr_y, width=qr_size, height=qr_size)

    for i, t in enumerate(tickets):
        if i > 0 and i % 2 == 0:
            p.showPage()
        if i % 2 == 0:
            p.setDash(3, 3)
            p.setStrokeColor(colors.darkgrey)
            p.line(0, PAGE_HEIGHT / 2, PAGE_WIDTH, PAGE_HEIGHT / 2)
            p.setDash()
        y_pos = (PAGE_HEIGHT / 2) if (i % 2 == 0) else 0
        draw_single_ticket(p, t, y_pos)

    p.showPage()
    p.save()
    buffer.seek(0)
    pdf_data = buffer.getvalue()
    buffer.close()
    
    response = HttpResponse(pdf_data, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Rezervare_AutoTrans_{main_ticket.id}.pdf"'
    return response

@login_required
def checkout(request, trip_id):
    trip = get_object_or_404(Trip, id=trip_id)
    dep_id = request.GET.get('dep')
    arr_id = request.GET.get('arr')
    
    start_station = get_object_or_404(Station, id=dep_id) if dep_id else None
    end_station = get_object_or_404(Station, id=arr_id) if arr_id else None
    
    # Calculăm prețul în funcție de distanță
    distance = trip.schedule.route.total_distance
    if start_station and end_station:
        rs_dep = RouteStation.objects.filter(route=trip.schedule.route, station=start_station).first()
        rs_arr = RouteStation.objects.filter(route=trip.schedule.route, station=end_station).first()
        if rs_dep and rs_arr:
            distance = abs(rs_arr.distance_from_start - rs_dep.distance_from_start)
    
    price_per_ticket = Decimal(distance) * Decimal('0.5')
    
    departure_dt = datetime.combine(trip.date, trip.schedule.departure_time)
    if start_station:
        rs_dep = RouteStation.objects.filter(route=trip.schedule.route, station=start_station).first()
        if rs_dep:
            departure_dt += rs_dep.time_from_start

    context = {
        'trip': trip,
        'price_per_ticket': price_per_ticket,
        'departure_dt': departure_dt,
        'start_station': start_station,
        'end_station': end_station
    }
    return render(request, "core/checkout.html", context)

@login_required
def process_payment(request, trip_id):
    if request.method == "POST":
        trip = get_object_or_404(Trip, id=trip_id)
        dep_id = request.POST.get('start_station_id')
        arr_id = request.POST.get('end_station_id')
        
        start_station = Station.objects.filter(id=dep_id).first() if dep_id else None
        end_station = Station.objects.filter(id=arr_id).first() if arr_id else None
        
        passenger_names = request.POST.getlist('passenger_names[]')
        
        # Recalculăm prețul pentru siguranță
        distance = trip.schedule.route.total_distance
        if start_station and end_station:
            rs_dep = RouteStation.objects.filter(route=trip.schedule.route, station=start_station).first()
            rs_arr = RouteStation.objects.filter(route=trip.schedule.route, station=end_station).first()
            if rs_dep and rs_arr:
                distance = abs(rs_arr.distance_from_start - rs_dep.distance_from_start)
        
        price_per_ticket = Decimal(distance) * Decimal('0.5')

        for name in passenger_names:
            if name.strip():
                Ticket.objects.create(
                    client=request.user,
                    trip=trip,
                    start_station=start_station,
                    end_station=end_station,
                    passenger_name=name.strip(),
                    price=price_per_ticket
                )
        
        messages.success(request, f"Plată reușită pentru {len(passenger_names)} bilete!")
        return redirect('my_reservations')
    return redirect('route_search')

@login_required
def driver_dashboard(request):
    if not hasattr(request.user, 'employee') or request.user.employee.position != 'driver':
        messages.error(request, "Acces refuzat.")
        return redirect('index')
    driver = request.user.employee
    now = timezone.now()
    
    assigned_trips = Trip.objects.filter(driver=driver).prefetch_related('tickets').order_by('date', 'schedule__departure_time')
    
    return render(request, "core/driver_dashboard.html", {
        'driver': driver, 
        'assigned_trips': assigned_trips,
        'today': now.date(),
        'now': now
    })

@login_required
def ticket_scanner(request):
    if not hasattr(request.user, 'employee') or request.user.employee.position != 'driver':
        messages.error(request, "Acces refuzat.")
        return redirect('index')
    
    trip_id = request.GET.get('trip_id')
    trip = get_object_or_404(Trip, id=trip_id, driver=request.user.employee) if trip_id else None
    
    return render(request, "core/scanner.html", {'trip': trip})


@login_required
def my_reservations(request):
    tickets = Ticket.objects.filter(client=request.user).order_by('-purchase_date')
    return render(request, "core/my_reservations.html", {'tickets': tickets, 'now': timezone.now()})

@login_required
def validate_ticket_api(request):
    if request.method == "POST":
        data = json.loads(request.body)
        qr_content = data.get('qr_content', '')
        current_trip_id = data.get('trip_id')

        try:
            parts = qr_content.split('|')
            if parts[0] != "AutoTrans": return JsonResponse({'success': False, 'message': 'Cod QR invalid.'})
            ticket_id = int(parts[1].split(':')[1])
            ticket = Ticket.objects.get(id=ticket_id)

            # Verificare dacă biletul aparține cursei selectate
            if current_trip_id and str(ticket.trip.id) != str(current_trip_id):
                return JsonResponse({
                    'success': False, 
                    'message': f'Biletul aparține cursei #{ticket.trip.id}, nu cursei curente.'
                })

            # Verificare dacă utilizatorul este șoferul desemnat pentru această cursă
            if not hasattr(request.user, 'employee') or request.user.employee.position != 'driver':
                return JsonResponse({'success': False, 'message': 'Doar șoferii pot valida bilete.'})
            
            if ticket.trip.driver != request.user.employee:
                return JsonResponse({'success': False, 'message': 'Nu sunteți șoferul desemnat pentru această cursă.'})

            if ticket.is_boarded: return JsonResponse({'success': False, 'message': f'Deja îmbarcat: {ticket.passenger_name}'})
            ticket.is_boarded = True
            ticket.save()
            return JsonResponse({
                'success': True, 
                'message': f'Validat: {ticket.passenger_name}',
                'passenger': ticket.passenger_name,
                'trip_id': ticket.trip.id
            })
        except Exception as e: return JsonResponse({'success': False, 'message': f'Eroare: {str(e)}'})
    return JsonResponse({'success': False, 'message': 'Metodă nepermisă.'})

def index(request):
    rute_active = Route.objects.prefetch_related('stations__station').all()
    toate_rutele_data = []
    
    # Folosim un dicționar pentru a grupa rutele care sunt dus-întors
    rute_unice = {}
    
    for ruta in rute_active:
        route_stations = ruta.stations.all().order_by('order')
        statii_ids = [rs.station.id for rs in route_stations if rs.station]
        
        if len(statii_ids) < 2:
            continue
            
        # Creăm o cheie canonică (secvența de ID-uri sau inversul ei, oricare e mai mică)
        statii_tuple = tuple(statii_ids)
        statii_tuple_rev = tuple(statii_ids[::-1])
        cheie_canonica = min(statii_tuple, statii_tuple_rev)
        
        if cheie_canonica in rute_unice:
            # Dacă am găsit și sensul opus, actualizăm numele cu o săgeată dublă
            ruta_existenta = rute_unice[cheie_canonica]
            if " - " in ruta_existenta["nume"] and " - " in ruta.name:
                p1 = ruta_existenta["nume"].split(" - ")
                p2 = ruta.name.split(" - ")
                if len(p1) == 2 and len(p2) == 2 and p1[0] == p2[1] and p1[1] == p2[0]:
                    ruta_existenta["nume"] = f"{p1[0]} ↔ {p1[1]}"
            continue

        statii_ruta = []
        for rs in route_stations:
            if rs.station:
                statii_ruta.append({
                    "nume": rs.station.name,
                    "lat": float(rs.station.latitude),
                    "lng": float(rs.station.longitude)
                })
        
        rute_unice[cheie_canonica] = {
            "id": ruta.id,
            "nume": ruta.name,
            "statii": statii_ruta
        }

    culori = ['#0d6efd', '#198754', '#dc3545', '#ffc107', '#6610f2', '#fd7e14', '#20c997', '#0dcaf0']
    
    for i, (cheie, data) in enumerate(rute_unice.items()):
        toate_rutele_data.append({
            "id": data["id"],
            "nume": data["nume"],
            "culoare": culori[i % len(culori)],
            "statii": data["statii"]
        })
            
    return render(request, "core/index.html", {
        'rute_json': json.dumps(toate_rutele_data),
    })

def route_search(request):
    departure_id = request.GET.get('departure')
    arrival_id = request.GET.get('arrival')
    search_date_str = request.GET.get('date')
    results = []
    
    # Obținem timpul local corect (Bucharest)
    now_local = timezone.localtime(timezone.now())
    
    if departure_id and arrival_id and search_date_str:
        try:
            search_date = datetime.strptime(search_date_str, '%Y-%m-%d').date()
            schedules = RouteSchedule.objects.filter(day_of_week=search_date.weekday())
            for sched in schedules:
                rs_dep = RouteStation.objects.filter(route=sched.route, station_id=departure_id).first()
                if rs_dep:
                    rs_arr = RouteStation.objects.filter(route=sched.route, station_id=arrival_id, order__gt=rs_dep.order).first()
                    if rs_arr:
                        # Combinăm data căutată cu ora plecării și adunăm timpul până la stația de îmbarcare
                        start_dt = datetime.combine(search_date, sched.departure_time)
                        # Facem timpul "aware" de timezone pentru a putea compara corect
                        start_dt_aware = timezone.make_aware(start_dt, timezone.get_current_timezone())
                        dep_time_dt = start_dt_aware + rs_dep.time_from_start
                        arr_time_dt = start_dt_aware + rs_arr.time_from_start
                        
                        # Filtrăm cursele care au plecat deja (comparăm aware cu aware)
                        if dep_time_dt > now_local:
                            trip, _ = Trip.objects.get_or_create(schedule=sched, date=search_date)
                            results.append({
                                'trip': trip, 
                                'departure_time': dep_time_dt, 
                                'arrival_time': arr_time_dt, 
                                'dep_id': departure_id, 
                                'arr_id': arrival_id,
                                'dep_name': rs_dep.station.name,
                                'arr_name': rs_arr.station.name
                            })

        except ValueError: pass
    dep_obj = Station.objects.filter(id=departure_id).first() if departure_id else None
    arr_obj = Station.objects.filter(id=arrival_id).first() if arrival_id else None

    return render(request, "core/rute.html", {
        'stations': Station.objects.all(), 
        'results': results, 
        'departure': departure_id, 
        'arrival': arrival_id, 
        'date': search_date_str,
        'dep_name_selected': dep_obj.name if dep_obj else '',
        'arr_name_selected': arr_obj.name if arr_obj else ''
    })

def get_arrival_counts(request):
    departure_id = request.GET.get('departure_id')
    arrival_id = request.GET.get('arrival_id')
    counts = {}
    
    if departure_id:
        for rs_dep in RouteStation.objects.filter(station_id=departure_id):
            for ls in RouteStation.objects.filter(route=rs_dep.route, order__gt=rs_dep.order):
                counts[ls.station_id] = counts.get(ls.station_id, 0) + 1
    elif arrival_id:
        for rs_arr in RouteStation.objects.filter(station_id=arrival_id):
            for fs in RouteStation.objects.filter(route=rs_arr.route, order__lt=rs_arr.order):
                counts[fs.station_id] = counts.get(fs.station_id, 0) + 1
                
    return JsonResponse(counts)

def route_detail(request, trip_id):
    trip = get_object_or_404(Trip, id=trip_id)
    dep_id = request.GET.get('dep')
    arr_id = request.GET.get('arr')
    
    dep_station = Station.objects.filter(id=dep_id).first() if dep_id else None
    arr_station = Station.objects.filter(id=arr_id).first() if arr_id else None
    
    start_dt = datetime.combine(trip.date, trip.schedule.departure_time)
    station_details = []
    
    dep_rs = None
    arr_rs = None
    
    for rs in RouteStation.objects.filter(route=trip.schedule.route).order_by('order'):
        is_dep = str(rs.station.id) == str(dep_id)
        is_arr = str(rs.station.id) == str(arr_id)
        
        if is_dep: dep_rs = rs
        if is_arr: arr_rs = rs
            
        station_details.append({
            'station': rs.station, 
            'time': start_dt + rs.time_from_start,
            'is_selected_dep': is_dep,
            'is_selected_arr': is_arr,
            'is_intermediate': rs.order > 1 and rs.order < RouteStation.objects.filter(route=trip.schedule.route).count()
        })
        
    context = {
        'trip': trip, 
        'stations': station_details, 
        'now': timezone.now(), 
        'dep_id': dep_id, 
        'arr_id': arr_id,
        'dep_station': dep_station,
        'arr_station': arr_station,
        'is_intermediate_pickup': dep_rs.order > 1 if dep_rs else False
    }
    return render(request, "core/route_detail.html", context)
