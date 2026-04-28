from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.core.exceptions import ValidationError


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email-ul este obligatoriu")

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    username = None

    email = models.EmailField("Email", unique=True)

    first_name = models.CharField("Prenume", max_length=150)
    last_name = models.CharField("Nume", max_length=150)
    phone_number = models.CharField("Telefon", max_length=15)
    address = models.CharField("Adresă", max_length=255, blank=True, null=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        verbose_name = "Utilizator"
        verbose_name_plural = "Utilizatori"

    def __str__(self):
        return self.email


class Employee(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, verbose_name="Utilizator")

    cnp = models.CharField("CNP", max_length=13, unique=True)

    POSITION_CHOICES = [
        ('driver', 'Șofer'),
        ('manager', 'Manager'),
        ('dispatcher', 'Dispecer'),
    ]
    position = models.CharField("Funcție", max_length=20, choices=POSITION_CHOICES)

    hire_date = models.DateField("Data angajării")

    salary = models.DecimalField("Salariu", max_digits=10, decimal_places=2)

    rating = models.FloatField("Rating", default=5.0)

    license_number = models.CharField("Număr permis", max_length=50, null=True, blank=True)

    STATUS_CHOICES = [
        ('active', 'Activ'),
        ('medical_leave', 'Concediu medical'),
        ('vacation', 'Concediu de odihnă'),
    ]
    status = models.CharField("Status", max_length=20, choices=STATUS_CHOICES, default='active')

    def clean(self):
        if self.position != "driver" and self.license_number:
            raise ValidationError("Doar șoferii pot avea permis.")

    class Meta:
        verbose_name = "Angajat"
        verbose_name_plural = "Angajați"

    def __str__(self):
        return f"{self.user} - {self.position}"


class Bus(models.Model):
    vin = models.CharField("VIN", max_length=17, unique=True)
    brand = models.CharField("Marcă", max_length=50)
    model = models.CharField("Model", max_length=50)
    license_plate = models.CharField("Număr înmatriculare", max_length=20, unique=True)
    capacity = models.IntegerField("Capacitate")

    STATUS_CHOICES = [
        ('active', 'Activ'),
        ('service', 'În service'),
        ('defective', 'Defect'),
    ]
    status = models.CharField("Status", max_length=20, choices=STATUS_CHOICES)

    class Meta:
        verbose_name = "Autobuz"
        verbose_name_plural = "Autobuze"

    def __str__(self):
        return f"{self.brand} {self.model} ({self.license_plate})"


class Station(models.Model):
    name = models.CharField("Denumire", max_length=100)
    latitude = models.FloatField("Latitudine")
    longitude = models.FloatField("Longitudine")

    class Meta:
        verbose_name = "Stație"
        verbose_name_plural = "Stații"

    def __str__(self):
        return self.name

    def name_formatted(self):
        """Returnează numele cu <br> înainte de paranteză pentru layout."""
        if ' (' in self.name:
            return self.name.replace(' (', '<br>(')
        return self.name


class Route(models.Model):
    name = models.CharField("Nume Rută", max_length=255, default="Rută nespecificată")
    total_distance = models.FloatField("Distanță totală")
    duration = models.DurationField("Durată estimată")

    class Meta:
        verbose_name = "Rută"
        verbose_name_plural = "Rute"

    def __str__(self):
        return self.name


class RouteStation(models.Model):
    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name="stations")
    station = models.ForeignKey(Station, on_delete=models.CASCADE)

    order = models.IntegerField("Ordine")
    time_from_start = models.DurationField("Timp de la plecare", help_text="Durata de la începutul rutei până la această stație")
    distance_from_start = models.FloatField("Distanță de la plecare", default=0.0, help_text="Distanța în km de la începutul rutei până la această stație")

    class Meta:
        unique_together = ('route', 'order')
        ordering = ['order']
        verbose_name = "Stație pe rută"
        verbose_name_plural = "Stații pe rută"

    def __str__(self):
        return f"{self.route} - {self.station} ({self.order})"


class RouteSchedule(models.Model):
    DAY_CHOICES = [
        (0, 'Luni'),
        (1, 'Marți'),
        (2, 'Miercuri'),
        (3, 'Joi'),
        (4, 'Vineri'),
        (5, 'Sâmbătă'),
        (6, 'Duminică'),
    ]
    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name="schedules")
    day_of_week = models.IntegerField("Ziua săptămânii", choices=DAY_CHOICES)
    departure_time = models.TimeField("Ora plecare din prima stație")

    class Meta:
        verbose_name = "Orar Rută"
        verbose_name_plural = "Orare Rute"
        unique_together = ('route', 'day_of_week', 'departure_time')

    def __str__(self):
        return f"{self.route.name} - {self.get_day_of_week_display()} la {self.departure_time}"

    def get_full_info(self):
        stations = self.route.stations.order_by('order')
        first_rs = stations.first()
        last_rs = stations.last()

        if not first_rs or not last_rs:
            return f"{self.departure_time.strftime('%H:%M')}"

        from datetime import datetime, date
        dummy_date = date(2000, 1, 1)
        departure_dt = datetime.combine(dummy_date, self.departure_time)
        arrival_dt = departure_dt + last_rs.time_from_start
        arrival_time = arrival_dt.time()

        from django.utils.html import format_html
        return format_html(
            '<div class="sched-card">'
            '  <div class="sched-row start">'
            '    <span class="s-time">{}</span>'
            '    <span class="s-station">{}</span>'
            '  </div>'
            '  <div class="sched-separator">↓</div>'
            '  <div class="sched-row end">'
            '    <span class="s-time">{}</span>'
            '    <span class="s-station">{}</span>'
            '  </div>'
            '</div>',
            self.departure_time.strftime('%H:%M'),
            format_html(first_rs.station.name_formatted()),
            arrival_time.strftime('%H:%M'),
            format_html(last_rs.station.name_formatted())
        )


class Trip(models.Model):
    schedule = models.ForeignKey(RouteSchedule, on_delete=models.CASCADE, related_name="trips")
    date = models.DateField("Data cursei")
    
    driver = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        related_name="trips",
        null=True,
        blank=True,
        verbose_name="Șofer"
    )

    bus = models.ForeignKey(
        Bus,
        on_delete=models.SET_NULL,
        related_name="trips",
        null=True,
        blank=True,
        verbose_name="Autobuz"
    )

    STATUS_CHOICES = [
        ('scheduled', 'Programată'),
        ('active', 'În curs'),
        ('completed', 'Finalizată'),
        ('cancelled', 'Anulată'),
    ]
    status = models.CharField("Status", max_length=20, choices=STATUS_CHOICES, default='scheduled')

    class Meta:
        verbose_name = "Cursă"
        verbose_name_plural = "Curse"
        unique_together = ('schedule', 'date')

    def clean(self):
        if self.driver and self.driver.position != "driver":
            raise ValidationError("Angajatul nu este șofer.")
        if self.driver and self.driver.status != "active":
            raise ValidationError("Șoferul nu este activ.")

    def __str__(self):
        return f"{self.schedule.route.name} - {self.date} {self.schedule.departure_time}"


class Ticket(models.Model):
    client = models.ForeignKey(User, on_delete=models.CASCADE, related_name="tickets")
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="tickets")
    
    start_station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name="starting_tickets", null=True)
    end_station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name="ending_tickets", null=True)

    passenger_name = models.CharField("Nume Pasager", max_length=255, default="Nespecificat")
    price = models.DecimalField("Preț", max_digits=6, decimal_places=2)
    purchase_date = models.DateTimeField("Data cumpărării", auto_now_add=True)
    is_boarded = models.BooleanField("Îmbarcat", default=False)

    class Meta:
        verbose_name = "Bilet"
        verbose_name_plural = "Bilete"

    def __str__(self):
        return f"Bilet {self.id} - {self.passenger_name} ({'Îmbarcat' if self.is_boarded else 'Așteptare'})"
