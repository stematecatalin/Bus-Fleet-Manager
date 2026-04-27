from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("rute/", views.route_search, name="route_search"),
    path("api/arrival-counts/", views.get_arrival_counts, name="get_arrival_counts"),
]