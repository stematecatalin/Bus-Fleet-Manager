from django.shortcuts import render, redirect, get_object_or_404
import json
from .models import Station, Route, RouteStation, Ticket
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
    
    # ... (grupare bilete neschimbată)
    from datetime import timedelta
    five_min_ago = main_ticket.purchase_date - timedelta(minutes=5)
    five_min_later = main_ticket.purchase_date + timedelta(minutes=5)
    
    tickets = Ticket.objects.filter(
        client=request.user, 
        route=main_ticket.route,
        purchase_date__range=(five_min_ago, five_min_later)
    ).order_by('id')

    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    PAGE_WIDTH, PAGE_HEIGHT = A4

    SITE_GREEN = colors.HexColor("#198754")

    def draw_single_ticket(canvas_obj, ticket, y_offset):
        # Generăm o semnătură de securitate (HMAC) pentru a preveni falsificarea
        security_token = f"{ticket.id}-{ticket.passenger_name}-{ticket.route.id}-{settings.SECRET_KEY}"
        signature = hashlib.sha256(security_token.encode()).hexdigest()[:12].upper()
        
        t_width = PAGE_WIDTH - 20*mm
        t_height = (PAGE_HEIGHT / 2) - 10*mm
        x_start = 10*mm
        y_start = y_offset + 5*mm

        # Card
        canvas_obj.setStrokeColor(colors.lightgrey)
        canvas_obj.setFillColor(colors.white)
        canvas_obj.roundRect(x_start, y_start, t_width, t_height, 3*mm, fill=1, stroke=1)

        # Header Verde
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

        # Linie Separatoare Verticală
        canvas_obj.setDash(1, 2)
        canvas_obj.setStrokeColor(colors.grey)
        canvas_obj.line(x_start + t_width - 65*mm, y_start + 10*mm, x_start + t_width - 65*mm, y_start + t_height - 30*mm)
        canvas_obj.setDash()

        # Detalii Stânga
        canvas_obj.setFillColor(colors.black)
        
        # Pasager
        canvas_obj.setFont(FONT_NAME, 8)
        canvas_obj.setFillColor(colors.grey)
        canvas_obj.drawString(x_start + 10*mm, y_start + t_height - 35*mm, "PASAGER")
        canvas_obj.setFillColor(colors.black)
        canvas_obj.setFont(FONT_BOLD, 14)
        canvas_obj.drawString(x_start + 10*mm, y_start + t_height - 42*mm, ticket.passenger_name.upper())

        # Stații
        dep_st = ticket.route.stations.first()
        arr_st = ticket.route.stations.last()
        dep_name = dep_st.station.name if dep_st else "---"
        arr_name = arr_st.station.name if arr_st else "---"

        canvas_obj.setFont(FONT_NAME, 8)
        canvas_obj.setFillColor(colors.grey)
        canvas_obj.drawString(x_start + 10*mm, y_start + t_height - 55*mm, "PLECARE")
        canvas_obj.setFillColor(colors.black)
        canvas_obj.setFont(FONT_BOLD, 11)
        canvas_obj.drawString(x_start + 10*mm, y_start + t_height - 61*mm, dep_name)

        canvas_obj.setFont(FONT_NAME, 8)
        canvas_obj.setFillColor(colors.grey)
        canvas_obj.drawString(x_start + 10*mm, y_start + t_height - 73*mm, "SOSIRE")
        canvas_obj.setFillColor(colors.black)
        canvas_obj.setFont(FONT_BOLD, 11)
        canvas_obj.drawString(x_start + 10*mm, y_start + t_height - 79*mm, arr_name)

        # Dată și Cursă
        canvas_obj.setFont(FONT_NAME, 8)
        canvas_obj.setFillColor(colors.grey)
        canvas_obj.drawString(x_start + 10*mm, y_start + t_height - 92*mm, "DATA ȘI ORA PLECARE")
        canvas_obj.drawString(x_start + 65*mm, y_start + t_height - 92*mm, "CURSA")

        canvas_obj.setFillColor(colors.black)
        canvas_obj.setFont(FONT_BOLD, 11)
        canvas_obj.drawString(x_start + 10*mm, y_start + t_height - 98*mm, ticket.route.departure_time.strftime('%d.%m.%Y | %H:%M'))
        canvas_obj.drawString(x_start + 65*mm, y_start + t_height - 98*mm, f"NR. {ticket.route.id}")

        # Preț și Cod Verificare
        canvas_obj.setFont(FONT_BOLD, 16)
        canvas_obj.setFillColor(SITE_GREEN)
        canvas_obj.drawString(x_start + 10*mm, y_start + 12*mm, f"PREȚ: {ticket.price} RON")
        
        canvas_obj.setFont(FONT_NAME, 7)
        canvas_obj.setFillColor(colors.grey)
        canvas_obj.drawString(x_start + 10*mm, y_start + 8*mm, f"COD VERIFICARE: {signature}")

        # QR Code (Centrat pe Y)
        # QR-ul conține acum și semnătura digitală (signature) pentru securitate
        qr_data = f"AutoTrans|TID:{ticket.id}|RID:{ticket.route.id}|NAME:{ticket.passenger_name}|SIG:{signature}"
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
        
        canvas_obj.setFont(FONT_NAME, 7)
        canvas_obj.setFillColor(colors.grey)
        canvas_obj.drawCentredString(x_start + t_width - 33*mm, qr_y - 4*mm, "SCANARE VALIDARE")


    # Desenăm biletele (2 pe pagină)
    for i, t in enumerate(tickets):
        if i > 0 and i % 2 == 0:
            p.showPage()
        
        # Desenăm linia de tăiere la mijlocul paginii (doar la primul bilet de pe pagină)
        if i % 2 == 0:
            p.setDash(3, 3)
            p.setStrokeColor(colors.darkgrey)
            p.setLineWidth(0.2*mm)
            p.line(0, PAGE_HEIGHT / 2, PAGE_WIDTH, PAGE_HEIGHT / 2)
            p.setDash() # Resetăm stilul liniei pentru bilet
            
        y_pos = (PAGE_HEIGHT / 2) if (i % 2 == 0) else 0
        draw_single_ticket(p, t, y_pos)

    p.showPage() # Ne asigurăm că pagina curentă este finalizată
    p.save()
    
    buffer.seek(0)
    pdf_data = buffer.getvalue()
    buffer.close()
    
    response = HttpResponse(pdf_data, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Rezervare_AutoTrans_{main_ticket.id}.pdf"'
    return response

@login_required
def checkout(request, route_id):
    route = get_object_or_404(Route, id=route_id)
    
    # Validare: Nu poți cumpăra bilet pentru o cursă care a plecat deja
    if route.departure_time < timezone.now():
        messages.error(request, "Această cursă a plecat deja. Nu mai puteți cumpăra bilete.")
        return redirect('route_detail', route_id=route.id)

    if not route.bus or route.bus.status != 'active':
        messages.error(request, "Autobuzul pentru această rută nu este disponibil.")
        return redirect('route_detail', route_id=route.id)

    price_per_ticket = Decimal(route.total_distance) * Decimal('0.5')
    
    context = {
        'route': route,
        'price_per_ticket': price_per_ticket,
    }
    return render(request, "core/checkout.html", context)

@login_required
def process_payment(request, route_id):
    if request.method == "POST":
        route = get_object_or_404(Route, id=route_id)
        
        passenger_names = request.POST.getlist('passenger_names[]')
        price_per_ticket = Decimal(route.total_distance) * Decimal('0.5')
        
        if not passenger_names:
            messages.error(request, "Trebuie să introduceți cel puțin un nume de pasager.")
            return redirect('checkout', route_id=route.id)

        # Verificăm capacitatea rămasă (opțional, dar bine de avut)
        # sold_tickets = Ticket.objects.filter(route=route).count()
        # if sold_tickets + len(passenger_names) > route.bus.capacity:
        #     messages.error(request, "Nu mai sunt suficiente locuri disponibile.")
        #     return redirect('checkout', route_id=route.id)

        for name in passenger_names:
            if name.strip():
                Ticket.objects.create(
                    client=request.user,
                    route=route,
                    passenger_name=name.strip(),
                    price=price_per_ticket
                )
        
        messages.success(request, f"Plata a fost efectuată cu succes pentru {len(passenger_names)} bilete!")
        return redirect('my_reservations')
    
    return redirect('route_search')

@login_required
def driver_dashboard(request):
    # Verificăm dacă utilizatorul este șofer
    if not hasattr(request.user, 'employee') or request.user.employee.position != 'driver':
        messages.error(request, "Acces refuzat. Pagina este destinată exclusiv șoferilor.")
        return redirect('index')
    
    driver = request.user.employee
    # Luăm rutele alocate șoferului
    assigned_routes = Route.objects.filter(driver=driver).order_by('departure_time')
    
    # Statistici simple
    total_assigned = assigned_routes.count()
    
    context = {
        'driver': driver,
        'assigned_routes': assigned_routes,
        'total_assigned': total_assigned,
    }
    return render(request, "core/driver_dashboard.html", context)

@login_required
def ticket_scanner(request):
    # Verificăm dacă utilizatorul este șofer
    if not hasattr(request.user, 'employee') or request.user.employee.position != 'driver':
        messages.error(request, "Acces refuzat. Doar șoferii pot accesa scannerul.")
        return redirect('index')
    return render(request, "core/scanner.html")

from django.utils import timezone

@login_required
def my_reservations(request):
    tickets = Ticket.objects.filter(client=request.user).order_by('-purchase_date')
    return render(request, "core/my_reservations.html", {
        'tickets': tickets,
        'now': timezone.now()
    })

@login_required
def validate_ticket_api(request):
    if request.method == "POST":
        import json
        data = json.loads(request.body)
        qr_content = data.get('qr_content', '')
        
        # Formatul nostru: AutoTrans|TID:1|RID:1|NAME:ION|SIG:XXXX
        try:
            parts = qr_content.split('|')
            if parts[0] != "AutoTrans":
                return JsonResponse({'success': False, 'message': 'Cod QR invalid (nu este un bilet AutoTrans).'})
            
            ticket_id = int(parts[1].split(':')[1])
            passenger_name = parts[3].split(':')[1]
            signature_provided = parts[4].split(':')[1]
            
            ticket = Ticket.objects.get(id=ticket_id)
            
            # Verificăm semnătura de securitate
            security_token = f"{ticket.id}-{ticket.passenger_name}-{ticket.route.id}-{settings.SECRET_KEY}"
            expected_signature = hashlib.sha256(security_token.encode()).hexdigest()[:12].upper()
            
            if signature_provided != expected_signature:
                return JsonResponse({'success': False, 'message': 'Semnătură de securitate invalidă! Biletul ar putea fi fals.'})
            
            if ticket.is_boarded:
                return JsonResponse({'success': False, 'message': f'Atenție! Pasagerul {ticket.passenger_name} este deja îmbarcat.'})
            
            # Totul e ok, bifăm îmbarcarea
            ticket.is_boarded = True
            ticket.save()
            
            return JsonResponse({
                'success': True, 
                'message': f'Validat cu succes: {ticket.passenger_name}',
                'passenger': ticket.passenger_name,
                'route_id': ticket.route.id
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Eroare la procesarea codului: {str(e)}'})
            
    return JsonResponse({'success': False, 'message': 'Metodă nepermisă.'})

def index(request):
    route_id = request.GET.get('route_id')
    if route_id:
        ruta_obj = Route.objects.filter(id=route_id).first()
    else:
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
    now = timezone.now()
    
    if departure and arrival:
        # Filtrăm doar rutele care au plecarea după momentul actual
        routes_with_departure = RouteStation.objects.filter(
            station_id=departure,
            route__departure_time__gte=now
        )
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

def route_detail(request, route_id):
    route = get_object_or_404(Route, id=route_id)
    stations = RouteStation.objects.filter(route=route).order_by('order')
    
    context = {
        'route': route,
        'stations': stations,
        'now': timezone.now(),
    }
    return render(request, "core/route_detail.html", context)
