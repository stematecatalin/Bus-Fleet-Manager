from datetime import date, time, timedelta
from unittest.mock import Mock, patch

import requests
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .fleet_optimizer import analyze_fleet, ask_fleet_agent
from .models import Bus, Employee, Route, RouteSchedule, Station, Ticket, Trip, User


class FleetOptimizerTests(TestCase):
    def setUp(self):
        self.route = Route.objects.create(
            name="Alexandria - București",
            total_distance=90,
            duration=timedelta(hours=2),
        )
        self.schedule_one = RouteSchedule.objects.create(
            route=self.route, day_of_week=0, departure_time=time(9, 0)
        )
        self.schedule_two = RouteSchedule.objects.create(
            route=self.route, day_of_week=0, departure_time=time(10, 0)
        )
        self.bus = Bus.objects.create(
            vin="12345678901234567", brand="Mercedes", model="Tourismo",
            license_plate="B-10-AUT", capacity=50, status="active",
        )
        driver_user = User.objects.create_user(
            email="driver@autotrans.ro", password="test12345",
            first_name="Ion", last_name="Popescu", phone_number="0700000000",
        )
        self.driver = Employee.objects.create(
            user=driver_user, cnp="1234567890123", position="driver",
            hire_date=date(2020, 1, 1), salary=5000,
            license_number="TR123", status="active",
        )

    def test_analysis_detects_overlapping_bus_and_driver(self):
        monday = date(2026, 6, 15)
        Trip.objects.create(
            schedule=self.schedule_one, date=monday, bus=self.bus, driver=self.driver
        )
        Trip.objects.create(
            schedule=self.schedule_two, date=monday, bus=self.bus, driver=self.driver
        )

        issue_types = {issue["type"] for issue in analyze_fleet(monday, days=1)["issues"]}

        self.assertIn("bus_conflict", issue_types)
        self.assertIn("driver_conflict", issue_types)

    def test_analysis_recommends_smallest_suitable_active_bus(self):
        smaller_bus = Bus.objects.create(
            vin="76543210987654321", brand="Iveco", model="Daily",
            license_plate="B-20-AUT", capacity=20, status="active",
        )
        trip = Trip.objects.create(schedule=self.schedule_one, date=date(2026, 6, 15))

        analysis = analyze_fleet(date(2026, 6, 15), days=1)
        trip_data = next(item for item in analysis["trips"] if item["id"] == trip.id)

        self.assertEqual(trip_data["recommended_bus"]["id"], smaller_bus.id)

    def test_analysis_warns_when_driver_exceeds_eight_hours_without_overlap(self):
        long_route = Route.objects.create(
            name="Rută lungă", total_distance=300, duration=timedelta(hours=5)
        )
        early = RouteSchedule.objects.create(
            route=long_route, day_of_week=0, departure_time=time(6, 0)
        )
        late = RouteSchedule.objects.create(
            route=long_route, day_of_week=0, departure_time=time(12, 0)
        )
        monday = date(2026, 6, 15)
        Trip.objects.create(schedule=early, date=monday, driver=self.driver)
        Trip.objects.create(schedule=late, date=monday, driver=self.driver)

        issues = analyze_fleet(monday, days=1)["issues"]
        hours_issue = next(issue for issue in issues if issue["type"] == "driver_daily_hours")

        self.assertIn("10 ore", hours_issue["message"])
        self.assertNotIn("driver_conflict", {issue["type"] for issue in issues})

    def test_analysis_suggests_merging_nearby_low_occupancy_trips(self):
        monday = timezone.localdate() + timedelta(days=1)
        first = Trip.objects.create(schedule=self.schedule_one, date=monday, bus=self.bus)
        second = Trip.objects.create(schedule=self.schedule_two, date=monday, bus=self.bus)

        opportunities = analyze_fleet(monday, days=1)["opportunities"]

        self.assertEqual(len(opportunities), 1)
        self.assertEqual(opportunities[0]["trip_ids"], [first.id, second.id])
        self.assertEqual(opportunities[0]["recommended_bus"]["id"], self.bus.id)

    @patch("core.fleet_optimizer.requests.post", side_effect=requests.ConnectionError("offline"))
    def test_admin_can_generate_and_apply_bus_reallocation(self, post):
        manager = User.objects.create_user(
            email="fleet@autotrans.ro", password="test12345",
            first_name="Manager", last_name="Flotă", phone_number="0744444444",
            is_staff=True,
        )
        unavailable_bus = Bus.objects.create(
            vin="11111111111111111", brand="MAN", model="Lion's Coach",
            license_plate="B-30-AUT", capacity=45, status="service",
        )
        replacement_bus = Bus.objects.create(
            vin="22222222222222222", brand="Iveco", model="Crossway",
            license_plate="B-31-AUT", capacity=30, status="active",
        )
        travel_date = timezone.localdate() + timedelta(days=1)
        trip = Trip.objects.create(
            schedule=self.schedule_one, date=travel_date, bus=unavailable_bus
        )
        self.client.force_login(manager)

        plan_response = self.client.post(
            reverse("admin:fleet-optimizer-reallocation-plan"),
            data={"trip_ids": [trip.id]},
            content_type="application/json",
        )

        self.assertEqual(plan_response.status_code, 200)
        plan = plan_response.json()["plan"]
        self.assertEqual(plan["recommended_bus"]["id"], replacement_bus.id)

        apply_response = self.client.post(
            reverse("admin:fleet-optimizer-reallocation-apply"),
            data={"token": plan["token"]},
            content_type="application/json",
        )

        self.assertEqual(apply_response.status_code, 200)
        trip.refresh_from_db()
        self.assertEqual(trip.bus, replacement_bus)

    @patch("core.fleet_optimizer.requests.post", side_effect=requests.ConnectionError("offline"))
    def test_bus_reallocation_is_revalidated_before_apply(self, post):
        manager = User.objects.create_user(
            email="safety@autotrans.ro", password="test12345",
            first_name="Manager", last_name="Siguranță", phone_number="0755555555",
            is_staff=True,
        )
        unavailable_bus = Bus.objects.create(
            vin="33333333333333333", brand="MAN", model="Lion's Coach",
            license_plate="B-40-AUT", capacity=45, status="defective",
        )
        replacement_bus = Bus.objects.create(
            vin="44444444444444444", brand="Setra", model="S 415",
            license_plate="B-41-AUT", capacity=25, status="active",
        )
        trip = Trip.objects.create(
            schedule=self.schedule_one,
            date=timezone.localdate() + timedelta(days=1),
            bus=unavailable_bus,
        )
        self.client.force_login(manager)
        plan_response = self.client.post(
            reverse("admin:fleet-optimizer-reallocation-plan"),
            data={"trip_ids": [trip.id]},
            content_type="application/json",
        )
        plan = plan_response.json()["plan"]

        replacement_bus.status = "service"
        replacement_bus.save(update_fields=["status"])
        apply_response = self.client.post(
            reverse("admin:fleet-optimizer-reallocation-apply"),
            data={"token": plan["token"]},
            content_type="application/json",
        )

        self.assertEqual(apply_response.status_code, 400)
        trip.refresh_from_db()
        self.assertEqual(trip.bus, unavailable_bus)

    @patch("core.fleet_optimizer.requests.post", side_effect=requests.ConnectionError("offline"))
    def test_bus_plan_does_not_affect_an_existing_assignment(self, post):
        manager = User.objects.create_user(
            email="bus-flow@autotrans.ro", password="test12345",
            first_name="Manager", last_name="Flux", phone_number="0750000001",
            is_staff=True,
        )
        unavailable_bus = Bus.objects.create(
            vin="55555555555555555", brand="MAN", model="Coach",
            license_plate="B-50-AUT", capacity=40, status="service",
        )
        replacement_bus = Bus.objects.create(
            vin="66666666666666666", brand="Setra", model="S 515",
            license_plate="B-51-AUT", capacity=45, status="active",
        )
        travel_date = timezone.localdate() + timedelta(days=1)
        target = Trip.objects.create(
            schedule=self.schedule_one, date=travel_date,
            bus=unavailable_bus, driver=self.driver,
        )
        self.client.force_login(manager)
        plan_response = self.client.post(
            reverse("admin:fleet-optimizer-reallocation-plan"),
            data={"trip_ids": [target.id]},
            content_type="application/json",
        )
        plan = plan_response.json()["plan"]
        self.assertEqual(plan["recommended_bus"]["id"], replacement_bus.id)

        overlapping_schedule = RouteSchedule.objects.create(
            route=self.route, day_of_week=travel_date.weekday(), departure_time=time(9, 30)
        )
        existing = Trip.objects.create(
            schedule=overlapping_schedule, date=travel_date,
            bus=replacement_bus, driver=None,
        )
        apply_response = self.client.post(
            reverse("admin:fleet-optimizer-reallocation-apply"),
            data={"token": plan["token"]},
            content_type="application/json",
        )

        self.assertEqual(apply_response.status_code, 400)
        target.refresh_from_db()
        existing.refresh_from_db()
        self.assertEqual(target.bus, unavailable_bus)
        self.assertEqual(existing.bus, replacement_bus)

    @patch("core.fleet_optimizer.requests.post", side_effect=requests.ConnectionError("offline"))
    def test_admin_distributes_overlapping_trips_between_drivers(self, post):
        manager = User.objects.create_user(
            email="dispatch@autotrans.ro", password="test12345",
            first_name="Dispecer", last_name="AutoTrans", phone_number="0766666666",
            is_staff=True,
        )
        drivers = [self.driver]
        for index in range(2):
            user = User.objects.create_user(
                email=f"driver{index + 2}@autotrans.ro", password="test12345",
                first_name=f"Șofer{index + 2}", last_name="Test",
                phone_number=f"077777777{index}",
            )
            drivers.append(Employee.objects.create(
                user=user, cnp=f"223456789012{index}", position="driver",
                hire_date=date(2021, 1, 1), salary=5000,
                license_number=f"TR20{index}", status="active",
            ))
        schedules = [
            self.schedule_one,
            RouteSchedule.objects.create(
                route=self.route, day_of_week=0, departure_time=time(9, 30)
            ),
            self.schedule_two,
        ]
        travel_date = timezone.localdate() + timedelta(days=1)
        trips = [
            Trip.objects.create(
                schedule=schedule, date=travel_date, bus=self.bus, driver=self.driver
            )
            for schedule in schedules
        ]
        self.client.force_login(manager)

        plan_response = self.client.post(
            reverse("admin:fleet-optimizer-driver-plan"),
            data={"trip_ids": [trip.id for trip in trips]},
            content_type="application/json",
        )

        self.assertEqual(plan_response.status_code, 200)
        plan = plan_response.json()["plan"]
        recommended_ids = {
            assignment["recommended_driver"]["id"] for assignment in plan["assignments"]
        }
        self.assertEqual(recommended_ids, {driver.id for driver in drivers})
        self.assertEqual(plan["changed_count"], 2)

        apply_response = self.client.post(
            reverse("admin:fleet-optimizer-driver-apply"),
            data={"token": plan["token"]},
            content_type="application/json",
        )

        self.assertEqual(apply_response.status_code, 200)
        self.assertEqual(
            len({trip.driver_id for trip in Trip.objects.filter(id__in=[item.id for item in trips])}),
            3,
        )

    @patch("core.fleet_optimizer.requests.post", side_effect=requests.ConnectionError("offline"))
    def test_driver_plan_is_revalidated_before_apply(self, post):
        manager = User.objects.create_user(
            email="driver-safety@autotrans.ro", password="test12345",
            first_name="Manager", last_name="Șoferi", phone_number="0788888888",
            is_staff=True,
        )
        replacement_user = User.objects.create_user(
            email="replacement@autotrans.ro", password="test12345",
            first_name="Mihai", last_name="Ionescu", phone_number="0799999999",
        )
        replacement = Employee.objects.create(
            user=replacement_user, cnp="3234567890123", position="driver",
            hire_date=date(2022, 1, 1), salary=5000,
            license_number="TR300", status="active",
        )
        travel_date = timezone.localdate() + timedelta(days=1)
        first = Trip.objects.create(
            schedule=self.schedule_one, date=travel_date, bus=self.bus, driver=self.driver
        )
        second = Trip.objects.create(
            schedule=self.schedule_two, date=travel_date, bus=self.bus, driver=self.driver
        )
        self.client.force_login(manager)
        plan_response = self.client.post(
            reverse("admin:fleet-optimizer-driver-plan"),
            data={"trip_ids": [first.id, second.id]},
            content_type="application/json",
        )
        plan = plan_response.json()["plan"]
        moved = next(item for item in plan["assignments"] if item["changed"])
        self.assertEqual(moved["recommended_driver"]["id"], replacement.id)

        replacement.status = "vacation"
        replacement.save(update_fields=["status"])
        apply_response = self.client.post(
            reverse("admin:fleet-optimizer-driver-apply"),
            data={"token": plan["token"]},
            content_type="application/json",
        )

        self.assertEqual(apply_response.status_code, 400)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.driver, self.driver)
        self.assertEqual(second.driver, self.driver)

    @patch("core.fleet_optimizer.requests.post")
    def test_driver_agent_corrects_an_invalid_plan_after_validator_feedback(self, post):
        manager = User.objects.create_user(
            email="ai-dispatch@autotrans.ro", password="test12345",
            first_name="Agent", last_name="Tester", phone_number="0701010101",
            is_staff=True,
        )
        replacement_user = User.objects.create_user(
            email="ai-driver@autotrans.ro", password="test12345",
            first_name="Radu", last_name="Agent", phone_number="0702020202",
        )
        replacement = Employee.objects.create(
            user=replacement_user, cnp="4234567890123", position="driver",
            hire_date=date(2023, 1, 1), salary=5000,
            license_number="TR400", status="active",
        )
        travel_date = timezone.localdate() + timedelta(days=1)
        first = Trip.objects.create(
            schedule=self.schedule_one, date=travel_date, bus=self.bus, driver=self.driver
        )
        second = Trip.objects.create(
            schedule=self.schedule_two, date=travel_date, bus=self.bus, driver=self.driver
        )

        invalid_response = Mock()
        invalid_response.raise_for_status.return_value = None
        invalid_response.json.return_value = {"message": {"content": (
            '{"assignments": ['
            f'{{"trip_id": {first.id}, "driver_id": {self.driver.id}}},'
            f'{{"trip_id": {second.id}, "driver_id": {self.driver.id}}}'
            '], "rationale": "Păstrez alocările."}'
        )}}
        valid_response = Mock()
        valid_response.raise_for_status.return_value = None
        valid_response.json.return_value = {"message": {"content": (
            '{"assignments": ['
            f'{{"trip_id": {first.id}, "driver_id": {self.driver.id}}},'
            f'{{"trip_id": {second.id}, "driver_id": {replacement.id}}}'
            '], "rationale": "Mut a doua cursă pentru a elimina suprapunerea."}'
        )}}
        explanation_response = Mock()
        explanation_response.raise_for_status.return_value = None
        explanation_response.json.return_value = {
            "message": {"content": '{"rationale": "Explicație suplimentară."}'}
        }
        post.side_effect = [invalid_response, valid_response, explanation_response]
        self.client.force_login(manager)

        response = self.client.post(
            reverse("admin:fleet-optimizer-driver-plan"),
            data={"trip_ids": [first.id, second.id]},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        plan = response.json()["plan"]
        self.assertEqual(plan["source"], "ai")
        self.assertEqual(plan["model"], "mistral-nemo")
        self.assertEqual(plan["attempts"], 2)
        self.assertIn("elimina suprapunerea", plan["rationale"])
        second_assignment = next(
            item for item in plan["assignments"] if item["trip_id"] == second.id
        )
        self.assertEqual(second_assignment["recommended_driver"]["id"], replacement.id)
        validator_feedback = post.call_args_list[1].kwargs["json"]["messages"][-1]["content"]
        self.assertIn("respins de validator", validator_feedback)

    @patch("core.fleet_optimizer.requests.post", side_effect=requests.ConnectionError("offline"))
    def test_admin_can_generate_and_apply_merge_plan(self, post):
        manager = User.objects.create_user(
            email="admin@autotrans.ro", password="test12345",
            first_name="Admin", last_name="AutoTrans", phone_number="0733333333",
            is_staff=True,
        )
        departure = Station.objects.create(name="Alexandria", latitude=43.97, longitude=25.33)
        arrival = Station.objects.create(name="București", latitude=44.43, longitude=26.10)
        travel_date = timezone.localdate() + timedelta(days=1)
        first = Trip.objects.create(schedule=self.schedule_one, date=travel_date, bus=self.bus)
        second = Trip.objects.create(schedule=self.schedule_two, date=travel_date, bus=self.bus)
        Ticket.objects.create(
            client=manager, trip=second, start_station=departure, end_station=arrival,
            passenger_name="Admin AutoTrans", price=45,
        )
        self.client.force_login(manager)

        plan_response = self.client.post(
            reverse("admin:fleet-optimizer-plan"),
            data={"first_trip_id": first.id, "second_trip_id": second.id},
            content_type="application/json",
        )
        self.assertEqual(plan_response.status_code, 200)
        plan = plan_response.json()["plan"]

        apply_response = self.client.post(
            reverse("admin:fleet-optimizer-apply"),
            data={"token": plan["token"]},
            content_type="application/json",
        )

        self.assertEqual(apply_response.status_code, 200)
        keep_trip = Trip.objects.get(id=plan["keep_trip"]["id"])
        cancelled_trip = Trip.objects.get(id=plan["cancel_trip"]["id"])
        self.assertEqual(cancelled_trip.status, "cancelled")
        self.assertFalse(Ticket.objects.filter(trip=cancelled_trip).exists())
        self.assertEqual(Ticket.objects.filter(trip=keep_trip).count(), 1)
        self.assertEqual(keep_trip.bus, self.bus)
        self.assertEqual(
            keep_trip.schedule.departure_time.strftime("%H:%M"),
            plan["proposed_departure_time"],
        )

    @patch("core.fleet_optimizer.requests.post", side_effect=requests.ConnectionError("offline"))
    def test_agent_uses_deterministic_fallback(self, post):
        analysis = analyze_fleet(date(2026, 6, 15), days=1)

        result = ask_fleet_agent("Ce prioritizez?", analysis)

        self.assertTrue(result["fallback"])
        self.assertIn("confirmată manual", result["answer"])

    def test_regular_user_cannot_access_management_agent(self):
        user = User.objects.create_user(
            email="client@example.com", password="test12345",
            first_name="Ana", last_name="Ionescu", phone_number="0711111111",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("admin:fleet-optimizer"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("admin:login"), response.url)

    def test_staff_user_can_access_management_agent(self):
        user = User.objects.create_user(
            email="manager@example.com", password="test12345",
            first_name="Mara", last_name="Ionescu", phone_number="0722222222",
            is_staff=True,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("admin:fleet-optimizer"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Agent pentru optimizarea flotei")
