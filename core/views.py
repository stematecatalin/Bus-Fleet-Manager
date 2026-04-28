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
    assigned_trips = Trip.objects.filter(driver=driver).order_by('date', 'schedule__departure_time')
    return render(request, "core/driver_dashboard.html", {'driver': driver, 'assigned_trips': assigned_trips})

@login_required
def ticket_scanner(request):
    if not hasattr(request.user, 'employee') or request.user.employee.position != 'driver':
        messages.error(request, "Acces refuzat.")
        return redirect('index')
    return render(request, "core/scanner.html")

@login_required
def my_reservations(request):
    tickets = Ticket.objects.filter(client=request.user).order_by('-purchase_date')
    return render(request, "core/my_reservations.html", {'tickets': tickets, 'now': timezone.now()})

@login_required
def validate_ticket_api(request):
    if request.method == "POST":
        data = json.loads(request.body)
        qr_content = data.get('qr_content', '')
        try:
            parts = qr_content.split('|')
            if parts[0] != "AutoTrans": return JsonResponse({'success': False, 'message': 'Cod QR invalid.'})
            ticket_id = int(parts[1].split(':')[1])
            ticket = Ticket.objects.get(id=ticket_id)
            if ticket.is_boarded: return JsonResponse({'success': False, 'message': f'Deja îmbarcat: {ticket.passenger_name}'})
            ticket.is_boarded = True
            ticket.save()
            return JsonResponse({'success': True, 'message': f'Validat: {ticket.passenger_name}'})
        except Exception as e: return JsonResponse({'success': False, 'message': f'Eroare: {str(e)}'})
    return JsonResponse({'success': False, 'message': 'Metodă nepermisă.'})

def index(request):
    route_id = request.GET.get('route_id')
    ruta_obj = Route.objects.filter(id=route_id).first() if route_id else Route.objects.first()
    statii_data = []
    if ruta_obj:
        for rs in RouteStation.objects.filter(route=ruta_obj).order_by('order'):
            statii_data.append({"id": rs.station.id, "nume": rs.station.name, "lat": rs.station.latitude, "lng": rs.station.longitude})
    return render(request, "core/index.html", {'statii_json': json.dumps(statii_data), 'ruta_obj': ruta_obj})

def route_search(request):
    departure_id = request.GET.get('departure')
    arrival_id = request.GET.get('arrival')
    search_date_str = request.GET.get('date')
    results = []
    now = timezone.now()
    if departure_id and arrival_id and search_date_str:
        try:
            search_date = datetime.strptime(search_date_str, '%Y-%m-%d').date()
            schedules = RouteSchedule.objects.filter(day_of_week=search_date.weekday())
            for sched in schedules:
                rs_dep = RouteStation.objects.filter(route=sched.route, station_id=departure_id).first()
                if rs_dep:
                    rs_arr = RouteStation.objects.filter(route=sched.route, station_id=arrival_id, order__gt=rs_dep.order).first()
                    if rs_arr:
                        start_dt = datetime.combine(search_date, sched.departure_time)
                        dep_time_dt = start_dt + rs_dep.time_from_start
                        arr_time_dt = start_dt + rs_arr.time_from_start
                        if dep_time_dt > now.replace(tzinfo=None):
                            trip, _ = Trip.objects.get_or_create(schedule=sched, date=search_date)
                            results.append({'trip': trip, 'departure_time': dep_time_dt, 'arrival_time': arr_time_dt, 'dep_id': departure_id, 'arr_id': arrival_id})
        except ValueError: pass
    return render(request, "core/rute.html", {'stations': Station.objects.all(), 'results': results, 'departure': departure_id, 'arrival': arrival_id, 'date': search_date_str})

def get_arrival_counts(request):
    departure_id = request.GET.get('departure_id')
    counts = {}
    if departure_id:
        for rs_dep in RouteStation.objects.filter(station_id=departure_id):
            for ls in RouteStation.objects.filter(route=rs_dep.route, order__gt=rs_dep.order):
                counts[ls.station_id] = counts.get(ls.station_id, 0) + 1
    return JsonResponse(counts)

def route_detail(request, trip_id):
    trip = get_object_or_404(Trip, id=trip_id)
    dep_id = request.GET.get('dep')
    arr_id = request.GET.get('arr')
    start_dt = datetime.combine(trip.date, trip.schedule.departure_time)
    station_details = []
    for rs in RouteStation.objects.filter(route=trip.schedule.route).order_by('order'):
        station_details.append({'station': rs.station, 'time': start_dt + rs.time_from_start})
    return render(request, "core/route_detail.html", {'trip': trip, 'stations': station_details, 'now': timezone.now(), 'dep_id': dep_id, 'arr_id': arr_id})
