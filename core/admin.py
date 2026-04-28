from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Employee, Bus, Route, Ticket, Station, RouteStation, RouteSchedule, Trip
from django.utils.html import format_html
from django.urls import path, reverse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from datetime import datetime


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('email', 'first_name', 'last_name', 'phone_number', 'is_staff')
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
    list_display = ('get_nume_complet', 'position', 'status', 'salary')
    list_filter = ('position', 'status')
    search_fields = ('user__email', 'cnp', 'user__first_name', 'user__last_name', 'license_number')
    list_editable = ('status',)

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
    list_display = ('license_plate', 'brand', 'model', 'capacity', 'status')
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


@admin.register(Station)
class StationAdmin(admin.ModelAdmin):
    list_display = ('name', 'latitude', 'longitude')
    search_fields = ('name',)
    
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


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = ('name', 'total_distance', 'manage_schedule_link')
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
    list_display = ('route', 'day_of_week', 'get_full_info_display')
    list_filter = ('day_of_week', 'route')

    def get_full_info_display(self, obj):
        return obj.get_full_info()
    get_full_info_display.short_description = 'Orar (Plecare - Sosire)'


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = ('get_route_name', 'date', 'departure_time', 'driver', 'bus', 'status', 'total_incasari')
    list_filter = ('date', 'status', 'schedule__route')
    search_fields = ('schedule__route__name', 'driver__user__last_name', 'bus__license_plate')

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


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_nume_client', 'trip', 'price', 'purchase_date', 'is_boarded')
    list_filter = ('purchase_date', 'trip__schedule__route', 'is_boarded')
    search_fields = ('client__email', 'client__first_name', 'client__last_name', 'passenger_name')

    def get_nume_client(self, obj):
        return f"{obj.client.first_name} {obj.client.last_name}"

    get_nume_client.short_description = 'Client'


@admin.register(RouteStation)
class RouteStationAdmin(admin.ModelAdmin):
    list_display = ('route', 'station', 'order', 'time_from_start', 'distance_from_start')
