from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("rute/", views.route_search, name="route_search"),
    path("rute/<int:route_id>/", views.route_detail, name="route_detail"),
    path("rute/<int:route_id>/checkout/", views.checkout, name="checkout"),
    path("rute/<int:route_id>/procesare-plata/", views.process_payment, name="process_payment"),
    path("rezervarile-mele/", views.my_reservations, name="my_reservations"),
    path("bilet/<int:ticket_id>/download/", views.generate_ticket_pdf, name="download_ticket"),
    path("sofer/", views.driver_dashboard, name="driver_dashboard"),
    path("scanner/", views.ticket_scanner, name="ticket_scanner"),
    path("api/validate-ticket/", views.validate_ticket_api, name="validate_ticket_api"),
    path("api/arrival-counts/", views.get_arrival_counts, name="get_arrival_counts"),
]