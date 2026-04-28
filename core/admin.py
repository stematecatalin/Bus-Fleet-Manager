from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.core.exceptions import ValidationError
from .models import User, Employee, Bus, Route, Ticket, Station, RouteStation, ContactMessage

@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'subject', 'created_at')
    search_fields = ('name', 'email', 'subject', 'message')
    readonly_fields = ('created_at',)
from django.utils.html import format_html
from django.db.models import Count
from django.db.models.functions import TruncDay
import json


admin.site.index_template = 'admin/index.html'


def get_ticket_stats():
    stats = (
        Ticket.objects.annotate(date=TruncDay('purchase_date'))
        .values('date')
        .annotate(y=Count('id'))
        .order_by('date')
    )
    labels = [s['date'].strftime("%d %b") for s in stats]
    values = [s['y'] for s in stats]
    return json.dumps(labels), json.dumps(values)



original_index = admin.site.index


def custom_index(request, extra_context=None):
    labels, values = get_ticket_stats()
    extra_context = extra_context or {}
    extra_context['chart_labels'] = labels
    extra_context['chart_values'] = values
    return original_index(request, extra_context)


admin.site.index = custom_index



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

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        if db_field.name == "position":
            if not request.user.is_superuser:
                kwargs['choices'] = [('driver', 'Șofer'), ('dispatcher', 'Dispecer')]
        return super().formfield_for_choice_field(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser and obj.position == "manager":
            raise ValidationError("Nu ai voie să creezi manageri.")
        super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            return qs.exclude(position="manager")
        return qs


@admin.register(Bus)
class BusAdmin(admin.ModelAdmin):
    list_display = ('license_plate', 'brand', 'model', 'capacity', 'status_colorat')
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

    def status_colorat(self, obj):
        culori = {'active': '#28a745', 'service': '#ffc107', 'defective': '#dc3545'}
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', culori.get(obj.status, 'gray'),
                           obj.status.upper())

    status_colorat.short_description = 'Stare Autobuz'


@admin.register(Station)
class StationAdmin(admin.ModelAdmin):
    list_display = ('name', 'latitude', 'longitude')
    search_fields = ('name',)


class RouteStationInline(admin.TabularInline):
    model = RouteStation
    extra = 1


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = ('id', 'bus', 'driver', 'departure_time', 'total_incasari_ruta')
    list_filter = ('departure_time',)
    search_fields = ('bus__license_plate', 'driver__user__last_name')
    inlines = [RouteStationInline]

    def total_incasari_ruta(self, obj):
        from .models import Ticket
        from django.db.models import Sum
        total = Ticket.objects.filter(route=obj).aggregate(Sum('price'))['price__sum'] or 0
        return format_html('<b style="color: #22427C;">{} RON</b>', total)

    total_incasari_ruta.short_description = 'Încasări Totale'


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_nume_client', 'route', 'price', 'purchase_date')
    list_filter = ('purchase_date', 'route')
    search_fields = ('client__email', 'client__first_name', 'client__last_name')

    def get_nume_client(self, obj):
        return f"{obj.client.first_name} {obj.client.last_name}"

    get_nume_client.short_description = 'Client'


@admin.register(RouteStation)
class RouteStationAdmin(admin.ModelAdmin):
    list_display = ('route', 'station', 'order', 'departure_time')