from django.test import TestCase
from django.urls import reverse
from django.core.exceptions import ValidationError
import json
from unittest.mock import patch
from datetime import date, time, timedelta

from django.utils import timezone

from .chatbot import fallback_intent
from .models import User, Bus, Station, Route, Employee, RouteSchedule, RouteStation, Ticket, Trip

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

class RouteSearchTests(TestCase):
    def setUp(self):
        self.dep = Station.objects.create(name="Departure", latitude=44.0, longitude=26.0)
        self.mid = Station.objects.create(name="Middle", latitude=44.1, longitude=26.1)
        self.arr = Station.objects.create(name="Arrival", latitude=44.2, longitude=26.2)
        
        self.route = Route.objects.create(name="Test Route", total_distance=100.0, duration=timedelta(hours=2))
        RouteStation.objects.create(route=self.route, station=self.dep, order=1, time_from_start=timedelta(0))
        RouteStation.objects.create(route=self.route, station=self.mid, order=2, time_from_start=timedelta(hours=1))
        RouteStation.objects.create(route=self.route, station=self.arr, order=3, time_from_start=timedelta(hours=2))
        
        self.date = date.today() + timedelta(days=1)
        self.sched = RouteSchedule.objects.create(
            route=self.route, 
            day_of_week=self.date.weekday(), 
            departure_time=time(10, 0)
        )

    def test_search_with_departure_only(self):
        """Test searching with only departure station returns results."""
        url = reverse('route_search')
        response = self.client.get(url, {
            'departure': self.dep.id,
            'date': self.date.isoformat()
        })
        self.assertEqual(response.status_code, 200)
        results = response.context['results']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['dep_name'], "Departure")
        self.assertEqual(results[0]['arr_name'], "Arrival") # Should default to last station

    def test_search_with_departure_and_arrival(self):
        """Test searching with both stations still works."""
        url = reverse('route_search')
        response = self.client.get(url, {
            'departure': self.dep.id,
            'arrival': self.mid.id,
            'date': self.date.isoformat()
        })
        self.assertEqual(response.status_code, 200)
        results = response.context['results']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['dep_name'], "Departure")
        self.assertEqual(results[0]['arr_name'], "Middle")

    def test_search_with_no_departure_returns_no_results(self):
        """Test searching without departure station returns no results."""
        url = reverse('route_search')
        response = self.client.get(url, {
            'date': self.date.isoformat()
        })
        self.assertEqual(response.status_code, 200)
        results = response.context['results']
        self.assertEqual(len(results), 0)



class ChatbotTests(TestCase):
    @patch("core.chatbot.call_intent_agent")
    def test_chatbot_answers_greeting(self, intent_agent):
        intent_agent.return_value = {
            "intent": "greeting", "departure": None, "arrival": None, "date": None
        }
        response = self.client.post(
            reverse("send_chat_message"),
            data=json.dumps({"message": "Salut"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("asistentul AutoTrans", response.json()["support_message"]["text"])

    @patch("core.chatbot.call_intent_agent")
    def test_chatbot_finds_route_from_database(self, intent_agent):
        departure = Station.objects.create(name="Alexandria", latitude=43.97, longitude=25.33)
        arrival = Station.objects.create(name="București", latitude=44.43, longitude=26.10)
        route = Route.objects.create(
            name="Alexandria - București", total_distance=88, duration=timedelta(hours=2)
        )
        RouteStation.objects.create(
            route=route, station=departure, order=1,
            time_from_start=timedelta(), distance_from_start=0,
        )
        RouteStation.objects.create(
            route=route, station=arrival, order=2,
            time_from_start=timedelta(hours=2), distance_from_start=88,
        )
        travel_date = timezone.localdate() + timedelta(days=1)
        RouteSchedule.objects.create(
            route=route, day_of_week=travel_date.weekday(), departure_time=time(12, 0)
        )
        intent_agent.return_value = {
            "intent": "search_route",
            "departure": "Alexandria",
            "arrival": "București",
            "date": travel_date.isoformat(),
        }

        response = self.client.post(
            reverse("send_chat_message"),
            data=json.dumps({"message": "Vreau mâine din Alexandria în București"}),
            content_type="application/json",
        )

        reply = response.json()["support_message"]["text"]
        journey = response.json()["support_message"]["journeys"][0]
        self.assertIn("12:00", reply)
        self.assertIn("14:00", reply)
        self.assertIn("Vezi și rezervă", reply)
        self.assertIn(travel_date.strftime("%d.%m.%Y"), reply)
        self.assertEqual(journey["total_price"], "44.00")
        self.assertEqual(journey["date"], travel_date.strftime("%d.%m.%Y"))
        self.assertEqual(
            journey["legs"][0]["departure_date"], travel_date.strftime("%d.%m.%Y")
        )
        self.assertEqual(
            journey["legs"][0]["arrival_date"], travel_date.strftime("%d.%m.%Y")
        )

    @patch("core.chatbot.call_intent_agent")
    def test_chatbot_finds_route_with_transfer_and_requested_time(self, intent_agent):
        alexandria = Station.objects.create(
            name="Alexandria (Centru)", latitude=43.97, longitude=25.33
        )
        bucharest = Station.objects.create(
            name="București (Autogara Rahova)", latitude=44.43, longitude=26.10
        )
        craiova = Station.objects.create(
            name="Craiova (Autogara Nord)", latitude=44.32, longitude=23.80
        )
        first_route = Route.objects.create(
            name="Alexandria - București", total_distance=88, duration=timedelta(hours=1)
        )
        second_route = Route.objects.create(
            name="București - Craiova", total_distance=230, duration=timedelta(hours=2)
        )
        RouteStation.objects.create(
            route=first_route, station=alexandria, order=1,
            time_from_start=timedelta(), distance_from_start=0,
        )
        RouteStation.objects.create(
            route=first_route, station=bucharest, order=2,
            time_from_start=timedelta(hours=1), distance_from_start=88,
        )
        RouteStation.objects.create(
            route=second_route, station=bucharest, order=1,
            time_from_start=timedelta(), distance_from_start=0,
        )
        RouteStation.objects.create(
            route=second_route, station=craiova, order=2,
            time_from_start=timedelta(hours=2), distance_from_start=230,
        )
        travel_date = timezone.localdate() + timedelta(days=1)
        RouteSchedule.objects.create(
            route=first_route, day_of_week=travel_date.weekday(), departure_time=time(8, 0)
        )
        RouteSchedule.objects.create(
            route=first_route, day_of_week=travel_date.weekday(), departure_time=time(12, 0)
        )
        RouteSchedule.objects.create(
            route=second_route, day_of_week=travel_date.weekday(), departure_time=time(13, 30)
        )
        intent_agent.return_value = {
            "intent": "search_route",
            "departure": "Alexandria (Centru)",
            "arrival": "Craiova (Autogara Nord)",
            "date": travel_date.isoformat(),
            "time": "10:00",
        }

        response = self.client.post(
            reverse("send_chat_message"),
            data=json.dumps({
                "message": "Cum ajung mâine din Alexandria în Craiova după ora 10:00?"
            }),
            content_type="application/json",
        )

        reply = response.json()["support_message"]["text"]
        journeys = response.json()["support_message"]["journeys"]
        self.assertIn("Transfer în București", reply)
        self.assertIn("12:00", reply)
        self.assertIn("13:30", reply)
        self.assertNotIn("08:00", reply)
        self.assertEqual(journeys[0]["transfer_count"], 1)
        self.assertEqual(len(journeys[0]["legs"]), 2)
        self.assertEqual(journeys[0]["total_price"], "159.00")

    @patch("core.chatbot.call_intent_agent", return_value=None)
    def test_chatbot_fallback_understands_hour_without_minutes(self, intent_agent):
        departure = Station.objects.create(
            name="București (Autogara Rahova)", latitude=44.43, longitude=26.10
        )
        arrival = Station.objects.create(
            name="Alexandria (Centru)", latitude=43.97, longitude=25.33
        )
        route = Route.objects.create(
            name="București - Alexandria", total_distance=92, duration=timedelta(hours=2)
        )
        RouteStation.objects.create(
            route=route, station=departure, order=1,
            time_from_start=timedelta(), distance_from_start=0,
        )
        RouteStation.objects.create(
            route=route, station=arrival, order=2,
            time_from_start=timedelta(hours=2), distance_from_start=92,
        )
        travel_date = timezone.localdate() + timedelta(days=1)
        for departure_time in (time(7, 0), time(13, 30), time(18, 30)):
            RouteSchedule.objects.create(
                route=route,
                day_of_week=travel_date.weekday(),
                departure_time=departure_time,
            )

        response = self.client.post(
            reverse("send_chat_message"),
            data=json.dumps({
                "message": "mâine la ora 15 am autobuz bucuresti-alexandria?"
            }),
            content_type="application/json",
        )

        fallback = fallback_intent("mâine la ora 15 am autobuz bucuresti-alexandria?")
        reply = response.json()["support_message"]["text"]
        journeys = response.json()["support_message"]["journeys"]
        self.assertEqual(fallback["time"], "15:00")
        self.assertIn("18:30", reply)
        self.assertNotIn("07:00", reply)
        self.assertNotIn("13:30", reply)
        self.assertEqual(len(journeys), 1)

    @patch("core.chatbot.call_intent_agent", return_value=None)
    def test_chatbot_answers_traveller_faq_without_ai(self, intent_agent):
        response = self.client.post(
            reverse("send_chat_message"),
            data=json.dumps({"message": "Pot lua un bagaj mare cu mine?"}),
            content_type="application/json",
        )
        reply = response.json()["support_message"]["text"]
        self.assertIn("politică oficială pentru bagaje", reply)
        self.assertIn("Contact", reply)

    @patch("core.chatbot.call_intent_agent")
    def test_chatbot_shows_authenticated_users_next_trip(self, intent_agent):
        user = User.objects.create_user(
            email="traveller@example.com", password="password123",
            first_name="Ana", last_name="Ionescu", phone_number="0700000001",
        )
        departure = Station.objects.create(name="Pitești", latitude=44.85, longitude=24.87)
        arrival = Station.objects.create(name="București", latitude=44.43, longitude=26.10)
        route = Route.objects.create(
            name="Pitești - București", total_distance=110, duration=timedelta(hours=2)
        )
        RouteStation.objects.create(
            route=route, station=departure, order=1,
            time_from_start=timedelta(), distance_from_start=0,
        )
        RouteStation.objects.create(
            route=route, station=arrival, order=2,
            time_from_start=timedelta(hours=2), distance_from_start=110,
        )
        travel_date = timezone.localdate() + timedelta(days=2)
        schedule = RouteSchedule.objects.create(
            route=route, day_of_week=travel_date.weekday(), departure_time=time(9, 0)
        )
        trip = Trip.objects.create(schedule=schedule, date=travel_date)
        Ticket.objects.create(
            client=user, trip=trip, start_station=departure, end_station=arrival,
            passenger_name="Ana Ionescu", price=55,
        )
        intent_agent.return_value = {
            "intent": "personal_trips", "departure": None, "arrival": None,
            "date": None, "time": None,
        }
        self.client.force_login(user)

        response = self.client.post(
            reverse("send_chat_message"),
            data=json.dumps({"message": "Care este următoarea mea cursă?"}),
            content_type="application/json",
        )
        reply = response.json()["support_message"]["text"]
        self.assertIn("09:00", reply)
        self.assertIn("Pitești", reply)
        self.assertIn("București", reply)

    @patch("core.chatbot.call_intent_agent")
    def test_route_price_question_overrides_wrong_ticket_intent(self, intent_agent):
        departure = Station.objects.create(
            name="Alexandria (Centru)", latitude=43.97, longitude=25.33
        )
        arrival = Station.objects.create(
            name="Turnu Măgurele (Port)", latitude=43.75, longitude=24.87
        )
        route = Route.objects.create(
            name="Alexandria - Turnu Măgurele",
            total_distance=65,
            duration=timedelta(hours=1, minutes=30),
        )
        RouteStation.objects.create(
            route=route, station=departure, order=1,
            time_from_start=timedelta(), distance_from_start=0,
        )
        RouteStation.objects.create(
            route=route, station=arrival, order=2,
            time_from_start=timedelta(hours=1, minutes=30), distance_from_start=65,
        )
        travel_date = timezone.localdate() + timedelta(days=1)
        RouteSchedule.objects.create(
            route=route, day_of_week=travel_date.weekday(), departure_time=time(9, 0)
        )
        intent_agent.return_value = {
            "intent": "ticket_help", "departure": None, "arrival": None,
            "date": None, "time": None,
        }

        response = self.client.post(
            reverse("send_chat_message"),
            data=json.dumps({
                "message": "Ce preț are cursa de la Alexandria la Turnu Măgurele mâine?"
            }),
            content_type="application/json",
        )

        support = response.json()["support_message"]
        self.assertEqual(support["journeys"], [])
        self.assertIn("32.50 RON", support["text"])
        self.assertIn("cursa directă", support["text"])
