from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.core.exceptions import ValidationError
from .models import User, Employee, Bus, Route, Ticket, Station, RouteStation


@admin.register(User)
class CustomUserAdmin(UserAdmin):

    list_display = ('email', 'first_name', 'last_name', 'phone_number', 'is_staff')
    search_fields = ('email', 'first_name', 'last_name', 'phone_number')
    ordering = ('email',)

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Date personale', {
            'fields': ('first_name', 'last_name', 'phone_number')
        }),
        ('Permisiuni', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')
        }),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'first_name', 'last_name', 'phone_number', 'is_staff', 'groups'),
        }),
    )

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('user', 'position', 'status', 'salary')
    list_filter = ('position', 'status')
    search_fields = ('user__email', 'cnp')

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        if db_field.name == "position":
            if not request.user.is_superuser:
                kwargs['choices'] = [
                    ('driver', 'Șofer'),
                    ('dispatcher', 'Dispecer'),
                ]
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
    list_display = ('brand', 'model', 'license_plate', 'status')
    search_fields = ('brand', 'model', 'license_plate')
    list_filter = ('status',)


@admin.register(Station)
class StationAdmin(admin.ModelAdmin):
    list_display = ('name', 'latitude', 'longitude')
    search_fields = ('name',)


class RouteStationInline(admin.TabularInline):
    model = RouteStation
    extra = 1


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = ('id', 'departure_time', 'arrival_time', 'bus', 'driver')
    list_filter = ('departure_time',)
    search_fields = ('bus__license_plate', 'driver__user__email')
    inlines = [RouteStationInline]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "driver":
            kwargs["queryset"] = Employee.objects.filter(
                position="driver",
                status="active"
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('id', 'client', 'route', 'price', 'purchase_date')
    list_filter = ('purchase_date',)
    search_fields = ('client__email',)