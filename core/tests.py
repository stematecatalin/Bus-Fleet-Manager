from django.test import TestCase
from django.urls import reverse
from django.core.exceptions import ValidationError
from .models import User, Bus, Station, Route, Employee
from datetime import date, timedelta

class ModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpassword",
            first_name="Test",
            last_name="User",
            phone_number="0700000000"
        )
        self.bus = Bus.objects.create(
            vin="TESTVIN123",
            brand="TestBrand",
            model="TestModel",
            license_plate="B-99-TST",
            capacity=50,
            status="active"
        )
        self.station = Station.objects.create(
            name="Test Station",
            latitude=44.0,
            longitude=26.0
        )
        self.route = Route.objects.create(
            name="Test Route",
            total_distance=100.0,
            duration=timedelta(hours=2)
        )

    def test_user_creation(self):
        self.assertEqual(self.user.email, "test@example.com")
        self.assertEqual(str(self.user), "test@example.com")

    def test_bus_creation(self):
        self.assertEqual(self.bus.license_plate, "B-99-TST")
        self.assertIn("TestBrand", str(self.bus))

    def test_station_creation(self):
        self.assertEqual(self.station.name, "Test Station")
        self.assertEqual(str(self.station), "Test Station")

    def test_route_creation(self):
        self.assertEqual(self.route.name, "Test Route")
        self.assertEqual(str(self.route), "Test Route")

class EmployeeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="driver@example.com",
            password="password",
            first_name="John",
            last_name="Doe"
        )

    def test_driver_creation(self):
        employee = Employee.objects.create(
            user=self.user,
            cnp="1234567890123",
            position="driver",
            hire_date=date.today(),
            salary=3000,
            license_number="LICENSE123"
        )
        self.assertEqual(employee.position, "driver")
        self.assertEqual(employee.license_number, "LICENSE123")

    def test_invalid_license_for_non_driver(self):
        """Manageri nu ar trebui să aibă număr de permis (conform validării din model)"""
        employee = Employee(
            user=self.user,
            cnp="1234567890123",
            position="manager",
            hire_date=date.today(),
            salary=5000,
            license_number="SHOULD_NOT_BE_HERE"
        )
        with self.assertRaises(ValidationError):
            employee.full_clean()

class ViewTests(TestCase):
    def test_index_view(self):
        response = self.client.get(reverse('index'))
        self.assertEqual(response.status_code, 200)

    def test_rute_view(self):
        response = self.client.get(reverse('route_search'))
        self.assertEqual(response.status_code, 200)
