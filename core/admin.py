from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import AIActionLog, User, Employee, Bus, Route, Ticket, Station, RouteStation, RouteSchedule, Trip
from django.utils.html import format_html
from django.urls import path, reverse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from datetime import datetime
import json

from django.http import JsonResponse
from django.core import signing
from django.db import transaction

from .fleet_optimizer import (
    _merge_candidate_data,
    analyze_fleet,
    ask_fleet_agent,
    decode_bus_reallocation_plan,
    decode_driver_reallocation_plan,
    decode_merge_plan,
    generate_bus_reallocation_plan,
    generate_driver_reallocation_plan,
    generate_merge_plan,
    get_bus_reallocation_candidates,
    validate_driver_distribution,
    validate_planned_trip_resources,
    validate_proposed_departure_time,
)


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('email', 'first_name', 'last_name', 'phone_number', 'is_staff', 'is_active')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'groups')
    search_fields = ('email', 'first_name', 'last_name', 'phone_number')
    ordering = ('email',)
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Date personale', {'fields': ('first_name', 'last_name', 'phone_number')}),
        ('Permisiuni', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'first_name', 'last_name', 'phone_number', 'is_staff',
                       'groups'),
        }),
    )


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('get_nume_complet', 'position', 'status', 'rating', 'license_number')
    list_filter = ('position', 'status')
    search_fields = ('user__email', 'cnp', 'user__first_name', 'user__last_name', 'license_number')
    list_editable = ('status',)
    autocomplete_fields = ('user',)

    def get_nume_complet(self, obj):
        return f"{obj.user.first_name} {obj.user.last_name}"

    get_nume_complet.short_description = 'Nume Angajat'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            return qs.exclude(position="manager")
        return qs


@admin.register(Bus)
class BusAdmin(admin.ModelAdmin):
    list_display = ('license_plate', 'brand', 'model', 'capacity', 'status', 'active_trip_count')
    search_fields = ('license_plate', 'brand', 'model', 'vin')
    list_filter = ('status', 'brand')
    actions = ['trimite_in_service', 'marcheaza_active']
    fieldsets = (
        ('Identitate Vehicul', {'fields': ('brand', 'model', 'license_plate', 'vin')}),
        ('Configurație și Stare', {'fields': ('capacity', 'status'), 'classes': ('collapse',)}),
    )

    @admin.action(description='🔧 Trimite în SERVICE')
    def trimite_in_service(self, request, queryset):
        queryset.update(status='service')

    @admin.action(description='✅ Marchează ACTIVE')
    def marcheaza_active(self, request, queryset):
        queryset.update(status='active')

    def active_trip_count(self, obj):
        return obj.trips.exclude(status__in=('cancelled', 'completed')).count()
    active_trip_count.short_description = 'Curse active'


@admin.register(Station)
class StationAdmin(admin.ModelAdmin):
    list_display = ('name', 'latitude', 'longitude')
    search_fields = ('name',)
    ordering = ('name',)
    
    # Adăugăm harta în pagina de editare/adăugare
    change_form_template = 'admin/core/station_change_form.html'
    
    fieldsets = (
        (None, {'fields': ('name',)}),
        ('Localizare pe Hartă', {
            'fields': (('latitude', 'longitude'),),
            'description': 'Faceți click pe hartă pentru a seta automat coordonatele stației.'
        }),
    )


class RouteStationInline(admin.TabularInline):
    model = RouteStation
    extra = 1
    autocomplete_fields = ('station',)


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = ('name', 'total_distance', 'duration', 'station_count', 'schedule_count', 'manage_schedule_link')
    search_fields = ('name',)
    inlines = [RouteStationInline]
    readonly_fields = ('schedule_button',)
    
    fieldsets = (
        (None, {'fields': ('name', 'total_distance')}),
        ('Planificare', {'fields': ('schedule_button',), 'description': 'Gestionați plecările săptămânale și durata rutei folosind grila de orar.'}),
    )

    def schedule_button(self, obj):
        if obj.pk:
            url = reverse('admin:route-edit-schedule', args=[obj.pk])
            return format_html('<a class="button" href="{}">⚙️ CONFIGURARE ORAR SĂPTĂMÂNAL</a>', url)
        return "Salvați ruta pentru a putea edita orarul."
    schedule_button.short_description = "Acțiune Orar"

    def manage_schedule_link(self, obj):
        return format_html('<a class="button" href="{}">⚙️ CONFIGURARE ORAR</a>', 
                           reverse('admin:route-edit-schedule', args=[obj.pk]))
    manage_schedule_link.short_description = 'Gestionare Program'

    def station_count(self, obj):
        return obj.stations.count()
    station_count.short_description = 'Stații'

    def schedule_count(self, obj):
        return obj.schedules.count()
    schedule_count.short_description = 'Orare'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<int:route_id>/edit-schedule/', self.admin_site.admin_view(self.edit_schedule), name='route-edit-schedule'),
        ]
        return custom_urls + urls

    def edit_schedule(self, request, route_id):
        route = get_object_or_404(Route, id=route_id)
        
        if request.method == "POST":
            action = request.POST.get('action')
            if action == "add":
                day = request.POST.get('day')
                t_str = request.POST.get('time')
                days_to_add = [int(day)] if day != "all" else range(7)
                
                if t_str:
                    try:
                        t_obj = datetime.strptime(t_str, '%H:%M').time()
                        for d in days_to_add:
                            RouteSchedule.objects.get_or_create(route=route, day_of_week=d, departure_time=t_obj)
                        messages.success(request, f"Plecarea de la ora {t_obj.strftime('%H:%M')} a fost adăugată.")
                    except ValueError:
                        messages.error(request, "Format oră invalid.")
            
            elif action == "delete":
                sched_id = request.POST.get('sched_id')
                RouteSchedule.objects.filter(id=sched_id, route=route).delete()
                messages.success(request, "Plecarea a fost ștearsă.")

            elif action == "update_duration":
                duration_mins = request.POST.get('duration_minutes')
                if duration_mins:
                    from datetime import timedelta
                    new_duration = timedelta(minutes=int(duration_mins))
                    route.duration = new_duration
                    route.save()
                    
                    # Actualizăm și timpul de sosire în ultima stație pentru ca orarul să se schimbe
                    last_station = route.stations.order_by('order').last()
                    if last_station:
                        last_station.time_from_start = new_duration
                        last_station.save()
                        
                    messages.success(request, f"Durata rutei a fost actualizată la {duration_mins} minute.")
                
            return redirect(reverse('admin:route-edit-schedule', args=[route.id]))

        days = [
            (0, 'Luni'), (1, 'Marți'), (2, 'Miercuri'), 
            (3, 'Joi'), (4, 'Vineri'), (5, 'Sâmbătă'), (6, 'Duminică')
        ]
        schedule_grid = {}
        for day_val, day_name in days:
            schedule_grid[day_val] = {
                'name': day_name,
                'times': RouteSchedule.objects.filter(route=route, day_of_week=day_val).order_by('departure_time')
            }

        context = {
            **self.admin_site.each_context(request),
            'title': f'Editor Orar: {route.name}',
            'route': route,
            'schedule_grid': schedule_grid,
            'opts': self.model._meta,
            'total_duration_seconds': route.duration.total_seconds(),
            'total_duration_minutes': int(route.duration.total_seconds() / 60),
        }
        return render(request, 'admin/core/route/edit_schedule.html', context)


@admin.register(RouteSchedule)
class RouteScheduleAdmin(admin.ModelAdmin):
    list_display = ('route', 'day_of_week', 'departure_time', 'get_full_info_display')
    list_filter = ('day_of_week', 'route')
    search_fields = ('route__name',)
    ordering = ('route__name', 'day_of_week', 'departure_time')
    autocomplete_fields = ('route',)

    def get_full_info_display(self, obj):
        return obj.get_full_info()
    get_full_info_display.short_description = 'Orar (Plecare - Sosire)'


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_route_name', 'date', 'departure_time', 'driver', 'bus', 'status', 'ticket_count', 'total_incasari')
    list_filter = ('status', 'date', 'schedule__route', 'bus__status', 'driver__status')
    search_fields = ('schedule__route__name', 'driver__user__last_name', 'bus__license_plate')
    autocomplete_fields = ('schedule', 'driver', 'bus')
    date_hierarchy = 'date'
    ordering = ('date', 'schedule__departure_time')

    def get_route_name(self, obj):
        return obj.schedule.route.name
    get_route_name.short_description = 'Rută'

    def departure_time(self, obj):
        return obj.schedule.departure_time
    departure_time.short_description = 'Ora Plecare'

    def total_incasari(self, obj):
        from .models import Ticket
        from django.db.models import Sum
        total = Ticket.objects.filter(trip=obj).aggregate(Sum('price'))['price__sum'] or 0
        return f"{total} RON"
    total_incasari.short_description = 'Încasări'

    def ticket_count(self, obj):
        return obj.tickets.count()
    ticket_count.short_description = 'Bilete'


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('id', 'passenger_name', 'get_nume_client', 'trip', 'price', 'purchase_date', 'is_boarded')
    list_filter = ('purchase_date', 'trip__schedule__route', 'is_boarded')
    search_fields = ('client__email', 'client__first_name', 'client__last_name', 'passenger_name', 'trip__schedule__route__name')
    autocomplete_fields = ('client', 'trip', 'start_station', 'end_station')
    date_hierarchy = 'purchase_date'

    def get_nume_client(self, obj):
        return f"{obj.client.first_name} {obj.client.last_name}"

    get_nume_client.short_description = 'Client'


@admin.register(RouteStation)
class RouteStationAdmin(admin.ModelAdmin):
    list_display = ('route', 'station', 'order', 'time_from_start', 'distance_from_start')
    list_filter = ('route',)
    search_fields = ('route__name', 'station__name')
    autocomplete_fields = ('route', 'station')


@admin.register(AIActionLog)
class AIActionLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'action_type', 'status_badge', 'source', 'model_name', 'created_by', 'trip_ids_display')
    list_filter = ('action_type', 'status', 'source', 'model_name', 'created_at')
    search_fields = ('summary', 'rationale', 'error_message', 'created_by__email')
    readonly_fields = (
        'created_at', 'created_by', 'action_type', 'status', 'source', 'model_name',
        'summary', 'rationale', 'related_trip_ids', 'plan_payload', 'error_message',
    )
    fieldsets = (
        ('Decizie', {'fields': ('created_at', 'created_by', 'action_type', 'status', 'source', 'model_name')}),
        ('Conținut plan', {'fields': ('summary', 'rationale', 'related_trip_ids', 'plan_payload')}),
        ('Diagnostic', {'fields': ('error_message',), 'classes': ('collapse',)}),
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def status_badge(self, obj):
        color = '#176047' if obj.status == 'applied' else '#a34141'
        return format_html('<strong style="color:{}">{}</strong>', color, obj.get_status_display())
    status_badge.short_description = 'Status'

    def trip_ids_display(self, obj):
        return ', '.join(f'#{trip_id}' for trip_id in obj.related_trip_ids)
    trip_ids_display.short_description = 'Curse'


def log_ai_action(request, *, action_type, status, summary, plan=None, trip_ids=None, error_message=''):
    plan = plan or {}
    AIActionLog.objects.create(
        action_type=action_type,
        status=status,
        source=plan.get('source', ''),
        model_name=plan.get('model', ''),
        summary=summary,
        rationale=plan.get('rationale', ''),
        plan_payload=plan,
        related_trip_ids=trip_ids or [],
        error_message=error_message,
        created_by=request.user if request.user.is_authenticated else None,
    )


def fleet_optimizer_admin(request):
    context = {
        **admin.site.each_context(request),
        'title': 'Agent AI pentru optimizarea flotei',
        'analysis': analyze_fleet(),
    }
    return render(request, 'admin/core/fleet_optimizer.html', context)


def fleet_optimizer_admin_chat(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Metodă nepermisă.'}, status=405)
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Cerere invalidă.'}, status=400)
    question = payload.get('question', '').strip()
    if not question:
        return JsonResponse({'success': False, 'error': 'Scrie o întrebare.'}, status=400)
    result = ask_fleet_agent(question, analyze_fleet())
    return JsonResponse({'success': True, **result})


def fleet_optimizer_generate_plan(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Metodă nepermisă.'}, status=405)
    try:
        payload = json.loads(request.body)
        first = Trip.objects.select_related('schedule__route', 'bus', 'driver__user').get(
            id=int(payload.get('first_trip_id'))
        )
        second = Trip.objects.select_related('schedule__route', 'bus', 'driver__user').get(
            id=int(payload.get('second_trip_id'))
        )
        plan = generate_merge_plan(first, second)
    except (json.JSONDecodeError, TypeError, ValueError, Trip.DoesNotExist) as exc:
        return JsonResponse({'success': False, 'error': str(exc) or 'Plan invalid.'}, status=400)
    return JsonResponse({'success': True, 'plan': plan})


def fleet_optimizer_apply_plan(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Metodă nepermisă.'}, status=405)
    plan = {}
    try:
        payload = json.loads(request.body)
        plan = decode_merge_plan(payload.get('token', ''))
    except (json.JSONDecodeError, signing.BadSignature, signing.SignatureExpired):
        return JsonResponse(
            {'success': False, 'error': 'Planul a expirat sau nu mai este valid. Generează-l din nou.'},
            status=400,
        )

    try:
        with transaction.atomic():
            trip_ids = [plan['keep_trip_id'], plan['cancel_trip_id']]
            locked_trips = {
                trip.id: trip
                for trip in Trip.objects.select_for_update()
                .select_related('schedule__route', 'bus', 'driver__user')
                .filter(id__in=trip_ids)
            }
            if len(locked_trips) != 2:
                raise ValueError('Una dintre curse nu mai există.')
            keep_trip = locked_trips[plan['keep_trip_id']]
            cancel_trip = locked_trips[plan['cancel_trip_id']]
            original_state = plan.get('original_state', {})
            for trip in (keep_trip, cancel_trip):
                expected = original_state.get(str(trip.id))
                current = {
                    'bus_id': trip.bus_id,
                    'driver_id': trip.driver_id,
                    'schedule_id': trip.schedule_id,
                    'status': trip.status,
                }
                if not expected or expected != current:
                    raise ValueError(
                        f'Cursa #{trip.id} s-a schimbat între timp. Generează un plan nou.'
                    )
            candidate = _merge_candidate_data(keep_trip, cancel_trip)

            bus = Bus.objects.select_for_update().filter(
                id=plan['bus_id'], status='active'
            ).first()
            if not bus or bus.capacity < candidate['combined_tickets']:
                raise ValueError('Autobuzul recomandat nu mai este disponibil sau nu are capacitate.')
            driver = Employee.objects.select_for_update().filter(
                id=plan['driver_id'], position='driver', status='active'
            ).select_related('user').first()
            if not driver:
                raise ValueError('Șoferul recomandat nu mai este disponibil.')

            proposed_time = validate_proposed_departure_time(
                keep_trip, cancel_trip, plan['proposed_departure_time']
            )
            if proposed_time == cancel_trip.schedule.departure_time:
                raise ValueError('Ora propusă aparține cursei anulate. Generează din nou planul.')
            target_schedule = keep_trip.schedule
            if proposed_time != keep_trip.schedule.departure_time:
                target_schedule, _ = RouteSchedule.objects.get_or_create(
                    route=keep_trip.schedule.route,
                    day_of_week=keep_trip.date.weekday(),
                    departure_time=proposed_time,
                )
                occupied = Trip.objects.filter(
                    schedule=target_schedule, date=keep_trip.date
                ).exclude(id__in=trip_ids).exists()
                if occupied:
                    raise ValueError('Există deja o cursă la ora propusă în aceeași zi.')

            validate_planned_trip_resources(
                keep_trip,
                bus=bus,
                driver=driver,
                departure_time=proposed_time,
                ticket_count=candidate['combined_tickets'],
                excluded_trip_ids=trip_ids,
            )
            moved_tickets = Ticket.objects.filter(trip=cancel_trip).update(trip=keep_trip)

            keep_trip.bus = bus
            keep_trip.driver = driver
            keep_trip.schedule = target_schedule
            keep_trip.save(update_fields=['bus', 'driver', 'schedule'])

            cancel_trip.status = 'cancelled'
            cancel_trip.bus = None
            cancel_trip.driver = None
            cancel_trip.save(update_fields=['status', 'bus', 'driver'])
    except (KeyError, TypeError, ValueError) as exc:
        log_ai_action(
            request,
            action_type='merge_trips',
            status='rejected',
            summary='Aplicare combinare curse respinsă',
            plan=plan,
            trip_ids=[plan.get('keep_trip_id'), plan.get('cancel_trip_id')] if plan else [],
            error_message=str(exc),
        )
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)

    log_ai_action(
        request,
        action_type='merge_trips',
        status='applied',
        summary=f'Cursa #{cancel_trip.id} a fost combinată cu #{keep_trip.id}',
        plan=plan,
        trip_ids=[keep_trip.id, cancel_trip.id],
    )
    return JsonResponse({
        'success': True,
        'message': (
            f'Cursa #{cancel_trip.id} a fost combinată cu #{keep_trip.id}. '
            f'{moved_tickets} bilete au fost mutate, plecarea a fost stabilită la '
            f'{proposed_time:%H:%M}, iar {bus.license_plate} a fost alocat.'
        ),
        'keep_trip_id': keep_trip.id,
    })


def fleet_optimizer_generate_reallocation_plan(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Metodă nepermisă.'}, status=405)
    try:
        payload = json.loads(request.body)
        trip_ids = payload.get('trip_ids', [])
        if isinstance(trip_ids, str):
            trip_ids = [value for value in trip_ids.split(',') if value]
        plan = generate_bus_reallocation_plan(trip_ids)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        return JsonResponse({'success': False, 'error': str(exc) or 'Plan invalid.'}, status=400)
    return JsonResponse({'success': True, 'plan': plan})


def fleet_optimizer_apply_reallocation_plan(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Metodă nepermisă.'}, status=405)
    plan = {}
    try:
        payload = json.loads(request.body)
        plan = decode_bus_reallocation_plan(payload.get('token', ''))
    except (json.JSONDecodeError, signing.BadSignature, signing.SignatureExpired):
        return JsonResponse({
            'success': False,
            'error': 'Planul a expirat sau nu mai este valid. Generează-l din nou.',
        }, status=400)

    try:
        with transaction.atomic():
            trip = (
                Trip.objects.select_for_update()
                .select_related('schedule__route', 'bus')
                .get(id=plan['trip_id'])
            )
            if trip.bus_id != plan.get('original_bus_id'):
                raise ValueError('Alocarea cursei s-a schimbat între timp. Generează un plan nou.')
            bus = Bus.objects.select_for_update().get(id=plan['bus_id'])
            valid_bus_ids = {
                candidate['bus'].id for candidate in get_bus_reallocation_candidates(trip)
            }
            if bus.id not in valid_bus_ids:
                raise ValueError(
                    'Autobuzul recomandat nu mai este activ, liber sau suficient de încăpător.'
                )
            validate_planned_trip_resources(
                trip,
                bus=bus,
                driver=trip.driver,
                excluded_trip_ids=[trip.id],
                validate_driver=False,
            )
            trip.bus = bus
            trip.save(update_fields=['bus'])
    except (KeyError, TypeError, ValueError, Trip.DoesNotExist, Bus.DoesNotExist) as exc:
        log_ai_action(
            request,
            action_type='bus_reallocation',
            status='rejected',
            summary='Aplicare realocare autobuz respinsă',
            plan=plan,
            trip_ids=[plan.get('trip_id')] if plan else [],
            error_message=str(exc),
        )
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)

    log_ai_action(
        request,
        action_type='bus_reallocation',
        status='applied',
        summary=f'Cursa #{trip.id} a fost realocată pe autobuzul {bus.license_plate}',
        plan=plan,
        trip_ids=[trip.id],
    )
    return JsonResponse({
        'success': True,
        'message': (
            f'Cursa #{trip.id} a fost realocată pe autobuzul {bus.license_plate}. '
            'Statusul, capacitatea și suprapunerile au fost reverificate înainte de salvare.'
        ),
        'trip_id': trip.id,
    })


def fleet_optimizer_generate_driver_plan(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Metodă nepermisă.'}, status=405)
    try:
        payload = json.loads(request.body)
        trip_ids = payload.get('trip_ids', [])
        if isinstance(trip_ids, str):
            trip_ids = [value for value in trip_ids.split(',') if value]
        plan = generate_driver_reallocation_plan(trip_ids)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        return JsonResponse({'success': False, 'error': str(exc) or 'Plan invalid.'}, status=400)
    return JsonResponse({'success': True, 'plan': plan})


def fleet_optimizer_apply_driver_plan(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Metodă nepermisă.'}, status=405)
    plan = {}
    assignments = {}
    try:
        payload = json.loads(request.body)
        plan = decode_driver_reallocation_plan(payload.get('token', ''))
        assignments = {int(trip_id): int(driver_id) for trip_id, driver_id in plan['assignments'].items()}
        original_driver_ids = {
            int(trip_id): driver_id
            for trip_id, driver_id in plan['original_driver_ids'].items()
        }
    except (json.JSONDecodeError, KeyError, TypeError, ValueError, signing.BadSignature, signing.SignatureExpired):
        return JsonResponse({
            'success': False,
            'error': 'Planul a expirat sau nu mai este valid. Generează-l din nou.',
        }, status=400)

    try:
        with transaction.atomic():
            trips = list(
                Trip.objects.select_for_update()
                .select_related('schedule__route', 'driver__user')
                .filter(id__in=assignments)
            )
            if len(trips) != len(assignments):
                raise ValueError('Una dintre curse nu mai există.')
            for trip in trips:
                if trip.driver_id != original_driver_ids.get(trip.id):
                    raise ValueError(
                        f'Alocarea cursei #{trip.id} s-a schimbat între timp. Generează un plan nou.'
                    )
            Employee.objects.select_for_update().filter(
                id__in=set(assignments.values())
            ).count()
            drivers = validate_driver_distribution(trips, assignments)
            changed_count = 0
            for trip in trips:
                driver = drivers[assignments[trip.id]]
                if trip.driver_id != driver.id:
                    trip.driver = driver
                    trip.save(update_fields=['driver'])
                    changed_count += 1
    except (TypeError, ValueError) as exc:
        log_ai_action(
            request,
            action_type='driver_reallocation',
            status='rejected',
            summary='Aplicare realocare șoferi respinsă',
            plan=plan,
            trip_ids=list(assignments.keys()),
            error_message=str(exc),
        )
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)

    log_ai_action(
        request,
        action_type='driver_reallocation',
        status='applied',
        summary=f'Plan aplicat: {changed_count} curse au primit alt șofer',
        plan=plan,
        trip_ids=list(assignments.keys()),
    )
    return JsonResponse({
        'success': True,
        'message': (
            f'Planul a fost aplicat: {changed_count} curse au primit alt șofer. '
            'Suprapunerile și limita de 8 ore au fost reverificate înainte de salvare.'
        ),
    })


original_admin_urls = admin.site.get_urls


def get_admin_urls():
    custom_urls = [
        path('agent-flota/', admin.site.admin_view(fleet_optimizer_admin), name='fleet-optimizer'),
        path('agent-flota/chat/', admin.site.admin_view(fleet_optimizer_admin_chat), name='fleet-optimizer-chat'),
        path('agent-flota/plan/', admin.site.admin_view(fleet_optimizer_generate_plan), name='fleet-optimizer-plan'),
        path('agent-flota/aplica/', admin.site.admin_view(fleet_optimizer_apply_plan), name='fleet-optimizer-apply'),
        path('agent-flota/plan-realocare/', admin.site.admin_view(fleet_optimizer_generate_reallocation_plan), name='fleet-optimizer-reallocation-plan'),
        path('agent-flota/aplica-realocare/', admin.site.admin_view(fleet_optimizer_apply_reallocation_plan), name='fleet-optimizer-reallocation-apply'),
        path('agent-flota/plan-soferi/', admin.site.admin_view(fleet_optimizer_generate_driver_plan), name='fleet-optimizer-driver-plan'),
        path('agent-flota/aplica-soferi/', admin.site.admin_view(fleet_optimizer_apply_driver_plan), name='fleet-optimizer-driver-apply'),
    ]
    return custom_urls + original_admin_urls()


admin.site.get_urls = get_admin_urls
