from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("rute/", views.route_search, name="route_search"),
    path("rute/<int:route_id>/", views.route_detail, name="route_detail"),
    path("rute/<int:route_id>/cumpara/", views.buy_ticket, name="buy_ticket"),
    path("api/arrival-counts/", views.get_arrival_counts, name="get_arrival_counts"),
]