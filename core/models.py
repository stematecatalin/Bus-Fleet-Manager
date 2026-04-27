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


class Route(models.Model):
    total_distance = models.FloatField("Distanță totală")
    duration = models.DurationField("Durată")
    departure_time = models.DateTimeField("Ora plecare")
    arrival_time = models.DateTimeField("Ora sosire")

    driver = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="routes",
        null=True,
        verbose_name="Șofer"
    )

    bus = models.ForeignKey(
        Bus,
        on_delete=models.CASCADE,
        related_name="routes",
        null=True,
        verbose_name="Autobuz"
    )

    def clean(self):
        if self.driver and self.driver.position != "driver":
            raise ValidationError("Angajatul nu este șofer.")
        if self.driver and self.driver.status != "active":
            raise ValidationError("Șoferul nu este activ.")

    class Meta:
        verbose_name = "Rută"
        verbose_name_plural = "Rute"

    def __str__(self):
        return f"Ruta {self.id}"


class RouteStation(models.Model):
    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name="stations")
    station = models.ForeignKey(Station, on_delete=models.CASCADE)

    order = models.IntegerField("Ordine")
    departure_time = models.DateTimeField("Ora plecare")

    class Meta:
        unique_together = ('route', 'order')
        ordering = ['order']
        verbose_name = "Stație pe rută"
        verbose_name_plural = "Stații pe rută"

    def __str__(self):
        return f"{self.route} - {self.station} ({self.order})"


class Ticket(models.Model):
    client = models.ForeignKey(User, on_delete=models.CASCADE, related_name="tickets")
    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name="tickets")

    price = models.DecimalField("Preț", max_digits=6, decimal_places=2)
    purchase_date = models.DateTimeField("Data cumpărării", auto_now_add=True)

    class Meta:
        verbose_name = "Bilet"
        verbose_name_plural = "Bilete"

    def __str__(self):
        return f"Bilet {self.id}"