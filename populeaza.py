import os
import django
from datetime import date, timedelta
from django.utils import timezone


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Bus_Fleet_Manager.settings')
django.setup()

from core.models import User, Employee, Bus, Station, Route, RouteStation, Ticket

def populate():
    Ticket.objects.all().delete()
    RouteStation.objects.all().delete()
    Route.objects.all().delete()
    Employee.objects.all().delete()
    User.objects.all().delete()
    Bus.objects.all().delete()
    Station.objects.all().delete()


    print("--- Pasul 2: Creăm date noi ---")

    #Angajati
    u1 = User.objects.create_user(
        email="rmihalache@autotrans.ro",
        password="parola1",
        first_name="Radu",
        last_name="Mihalache",
        phone_number="0741724491"
    )

    u2 = User.objects.create_user(
        email="mirceadumitrache@autotrans.ro",
        password="parola2",
        first_name="Mircea",
        last_name="Dumitrache",
        phone_number="0762784699"
    )

    u3 = User.objects.create_user(
        email="vasilerece@autotrans.ro",
        password="parola3",
        first_name="Vasile",
        last_name="Rece",
        phone_number="0788716637"
    )

    u4 = User.objects.create_user(
        email="tomoescumarius@autotrans.ro",
        password="parola4",
        first_name="Marius",
        last_name="Tomoescu",
        phone_number="0725811364"
    )

    u5 = User.objects.create_user(
        email="petrepetcu@autotrans.ro",
        password="parola5",
        first_name="Petre",
        last_name="Petcu",
        phone_number="0782967428"
    )

    u6 = User.objects.create_user(
        email="sarbumihai@autotrans.ro",
        password="parola6",
        first_name="Mihai",
        last_name="Sarbu",
        phone_number="0748554876"
    )

    u7 = User.objects.create_user(
        email="tudorgheorghe@autotrans.ro",
        password="parola7",
        first_name="Gheorghe",
        last_name="Tudor",
        phone_number="0743371827"
    )

    u8 = User.objects.create_user(
        email="simionadrian@autotrans.ro",
        password="parola8",
        first_name="Adrian",
        last_name="Simion",
        phone_number="0798273912"
    )

    u9 = User.objects.create_user(
        email="ubaniculae@autotrans.ro",
        password="parola9",
        first_name="Niculae",
        last_name="Uba",
        phone_number="0733816891"
    )

    #Pasageri
    pasager1 = User.objects.create_user(
        email="amanmonica23@gmail.com",
        password="parola15",
        first_name="Monica",
        last_name="Aman",
        phone_number="0734871864"
    )

    pasager2 = User.objects.create_user(
        email="barleasimona15@gmail.com",
        password="parola16",
        first_name="Simona",
        last_name="Barlea",
        phone_number="0784183968"
    )

    pasager3 = User.objects.create_user(
        email="bratugabriel@gmail.com",
        password="parola17",
        first_name="Gabriel",
        last_name="Bratu",
        phone_number="0787196438"
    )

    pasager4 = User.objects.create_user(
        email="becheanuraul4@gmail.com",
        password="parola18",
        first_name="Raul",
        last_name="Becheanu",
        phone_number="0782496228"
    )

    pasager5 = User.objects.create_user(
        email="belgealaurentiu1@gmail.com",
        password="parola19",
        first_name="Laurentiu",
        last_name="Belgea",
        phone_number="0778874659"
    )

    pasager6 = User.objects.create_user(
        email="soareilinca42@gmail.com",
        password="parola20",
        first_name="Ilinca",
        last_name="Soare",
        phone_number="0773728461"
    )

    pasager7 = User.objects.create_user(
        email="stannsoare@gmail.com",
        password="parola21",
        first_name="Leo",
        last_name="Stan",
        phone_number="0719867366"
    )

    pasager8 = User.objects.create_user(
        email="ionstoicaa2@gmail.com",
        password="parola22",
        first_name="Ion",
        last_name="Stoica",
        phone_number="0771222468"
    )

    pasager9 = User.objects.create_user(
        email="adelinamunteanu@gmail.com",
        password="parola23",
        first_name="Adelina",
        last_name="Munteanu",
        phone_number="0746228744"
    )

    pasager10 = User.objects.create_user(
        email="andreeaedanila15@gmail.com",
        password="parola24",
        first_name="Andreea",
        last_name="Danila",
        phone_number="0736345871"
    )

    pasager11 = User.objects.create_user(
        email="rusmariuss2@gmail.com",
        password="parola25",
        first_name="Marius",
        last_name="Rus",
        phone_number="0714759559"
    )

    pasager12 = User.objects.create_user(
        email="mihaelarotaru2@gmail.com",
        password="parola26",
        first_name="Mihaela",
        last_name="Rotaru",
        phone_number="0736845779"
    )

    pasager13 = User.objects.create_user(
        email="sebimocanu13@gmail.com",
        password="parola27",
        first_name="Sebastian",
        last_name="Mocanu",
        phone_number="0761857899"
    )

    pasager14 = User.objects.create_user(
        email="andraataranuu@gmail.com",
        password="parola28",
        first_name="Andra",
        last_name="Taranu",
        phone_number="0738457489"
    )

    pasager15 = User.objects.create_user(
        email="alexecosmin48@gmail.com",
        password="parola29",
        first_name="Cosmin",
        last_name="Alexe",
        phone_number="0742663871"
    )


    #Angajati
    sofer_angajat1 = Employee.objects.create(
        user=u1,
        cnp="1800507411235",
        position="driver",
        hire_date=date(2020, 5, 7),
        salary=4500.00,
        status="active",
        rating=4,
        license_number="B0099221"
    )

    sofer_angajat2 = Employee.objects.create(
        user=u2,
        cnp="1850202424568",
        position="driver",
        hire_date=date(2019, 6, 10),
        salary=5000.00,
        status="active",
        rating=5,
        license_number="B1122334"
    )

    sofer_angajat3 = Employee.objects.create(
        user=u3,
        cnp="1921215127891",
        position="driver",
        hire_date=date(2022, 10, 20),
        salary=3000.00,
        status="vacation",
        rating=4,
        license_number="B5566778"
    )

    sofer_angajat4 = Employee.objects.create(
        user=u4,
        cnp="1980430351112",
        position="driver",
        hire_date=date(2023, 10, 1),
        salary=3500.00,
        status="medical_leave",
        rating=4,
        license_number="CJ4581375"
    )

    sofer_angajat5 = Employee.objects.create(
        user=u5,
        cnp="5000101409991",
        position="driver",
        hire_date=date(2024, 2, 2),
        salary=3500.00,
        status="active",
        rating=5,
        license_number="TR1782974"
    )

    sofer_angajat6 = Employee.objects.create(
        user=u6,
        cnp="1980284781992",
        position="driver",
        hire_date=date(2018, 7, 25),
        salary=4500.00,
        status="active",
        rating=5,
        license_number="VS1489256"
    )

    manager_angajat = Employee.objects.create(
        user=u7,
        cnp="1911574827941",
        position="manager",
        hire_date=date(2019, 3, 10),
        salary=8000.00,
        status="active",
        license_number=None
    )

    dispatcher_angajat1=Employee.objects.create(
        user=u8,
        cnp="5020315409876",
        position="dispatcher",
        hire_date=date(2021, 1, 20),
        salary=5000.00,
        status="active",
        license_number=None
    )

    dispatcher_angajat2 = Employee.objects.create(
        user=u9,
        cnp="1951130402468",
        position="dispatcher",
        hire_date=date(2023, 10, 21),
        salary=5500.00,
        status="vacation",
        license_number=None
    )


    # AUTOBUZE
    b1 = Bus.objects.create(
        vin="WDB4102141D778844",
        brand="Mercedes-Benz",
        model="Citaro",
        license_plate="B-01-ATT",
        capacity=70,
        status="active"
    )

    b2 = Bus.objects.create(
        vin="YV3R422C1FA000123",
        brand="Volvo",
        model="9700",
        license_plate="B-02-ATT",
        capacity=50,
        status="service"
    )

    b3 = Bus.objects.create(
        vin="WDB4102141D777888",
        brand="Mercedes-Benz",
        model="Tourismo",
        license_plate="B-03-ATT",
        capacity=51,
        status="defective"
    )

    b4 = Bus.objects.create(
        vin="WDB9066331E999000",
        brand="Mercedes-Benz",
        model="Sprinter",
        license_plate="B-04-ATT",
        capacity=19,
        status="active"
    )

    b5 = Bus.objects.create(
        vin="WDB6334511C555666",
        brand="Mercedes-Benz",
        model="Intouro",
        license_plate="B-05-ATT",
        capacity=55,
        status="active"
    )

    b6 = Bus.objects.create(
        vin="WDB6280311B333444",
        brand="Mercedes-Benz",
        model="Conecto",
        license_plate="B-06-ATT",
        capacity=95,
        status="active"
    )



    #STAȚII
    st_buc = Station.objects.create(name="București (Autogara Rahova)", latitude=44.3951, longitude=26.0428)
    st_alex = Station.objects.create(name="Alexandria (Centru)", latitude=43.9686, longitude=25.3333)
    st_turnu = Station.objects.create(name="Turnu Măgurele (Port)", latitude=43.7486, longitude=24.8703)
    st_rosiori = Station.objects.create(name="Roșiorii de Vede", latitude=44.1122, longitude=24.9922)
    st_pitesti = Station.objects.create(name="Pitești (Autogara Sud)", latitude=44.8565, longitude=24.8697)
    st_slatina = Station.objects.create(name="Slatina (Centru)", latitude=44.4297, longitude=24.3642)
    st_craiova = Station.objects.create(name="Craiova (Autogara Nord)", latitude=44.3184, longitude=23.8033)




    # Autobuz Bucuresti-Turnu Magurele, oprire Alexandria

    ruta_sud = Route.objects.create(
        total_distance=150.5,
        duration=timedelta(hours=3),  #
        departure_time=timezone.now(),
        arrival_time=timezone.now() + timedelta(hours=3),
        driver=sofer_angajat1,
        bus=b1
    )

    ora_sosire_turnu = ruta_sud.arrival_time
    ora_plecare_retur_sud = ora_sosire_turnu + timedelta(hours=1)

    ruta_retur_sud = Route.objects.create(
        total_distance=150.5,
        duration=timedelta(hours=3),
        departure_time=ora_plecare_retur_sud,
        arrival_time=ora_plecare_retur_sud + timedelta(hours=3),
        driver=sofer_angajat1,
        bus=b1
    )

    ruta_arges = Route.objects.create(
        total_distance=98.0,  # Distanța în km
        duration=timedelta(hours=1, minutes=45),
        departure_time=timezone.now() + timedelta(hours=5),
        arrival_time=timezone.now() + timedelta(hours=6, minutes=45),
        driver=sofer_angajat2,
        bus=b2
    )

    ora_sosire_pitesti = ruta_arges.arrival_time
    ora_plecare_retur_arges = ora_sosire_pitesti + timedelta(minutes=45)

    ruta_retur_arges = Route.objects.create(
        total_distance=98.0,
        duration=timedelta(hours=1, minutes=45),
        departure_time=ora_plecare_retur_arges,
        arrival_time=ora_plecare_retur_arges + timedelta(hours=1, minutes=45),
        driver=sofer_angajat2,
        bus=b2
    )

    ruta_oltenia = Route.objects.create(
        total_distance=230.0,
        duration=timedelta(hours=4),  #
        departure_time=timezone.now() + timedelta(hours=2),
        arrival_time=timezone.now() + timedelta(hours=6),
        driver=sofer_angajat3,
        bus=b3
    )

    ora_sosire_dus_oltenia = ruta_oltenia.arrival_time
    ora_plecare_retur_oltenia = ora_sosire_dus_oltenia + timedelta(hours=2)
    ruta_retur_oltenia = Route.objects.create(
        total_distance=230.0,
        duration=timedelta(hours=4),
        departure_time=ora_plecare_retur_oltenia,
        arrival_time=ora_plecare_retur_oltenia + timedelta(hours=4),
        driver=sofer_angajat3,
        bus=b3
    )

    #Ruta Bucuresti-Alexandria-Turnu Magurele
    #1. Statia 1: Plecare din Bucuresti
    RouteStation.objects.create(
        route=ruta_sud,
        station=st_buc,
        order=1,
        departure_time=timezone.now()
    )

    #2. Stația 2: Oprire la Alexandria
    RouteStation.objects.create(
        route=ruta_sud,
        station=st_alex,
        order=2,
        departure_time=timezone.now() + timedelta(hours=1, minutes=30)
    )

    #3. Statia 3: Turnu Magurele
    RouteStation.objects.create(
        route=ruta_sud,
        station=st_turnu,
        order=3,
        departure_time=timezone.now() + timedelta(hours=3)
    )

    #Ruta Turnu-Magurele-Alexandria-Bucuresti
    #1. Statia 1: Turnu Magurele
    RouteStation.objects.create(
        route=ruta_retur_sud,
        station=st_turnu,
        order=1,
        departure_time=ora_plecare_retur_sud
    )

    #2. Statia 2: Alexandria
    RouteStation.objects.create(
        route=ruta_retur_sud,
        station=st_alex,
        order=2,
        departure_time=ora_plecare_retur_sud + timedelta(hours=1, minutes=30)
    )

    #3. Statia 3: București
    RouteStation.objects.create(
        route=ruta_retur_sud,
        station=st_buc,
        order=3,
        departure_time=ora_plecare_retur_sud + timedelta(hours=3)
    )


    #Ruta Alexandria-Rosiorii de Vede-Pitesti
    # Statia 1: Alexandria
    RouteStation.objects.create(
        route=ruta_arges,
        station=st_alex,
        order=1,
        departure_time=ruta_arges.departure_time
    )

    # 2. Statia 2: Roșiorii de Vede
    RouteStation.objects.create(
        route=ruta_arges,
        station=st_rosiori,
        order=2,
        departure_time=ruta_arges.departure_time + timedelta(minutes=45)
    )

    # 3. Statia 3: Pitești
    RouteStation.objects.create(
        route=ruta_arges,
        station=st_pitesti,
        order=3,
        departure_time=ruta_arges.departure_time + timedelta(hours=1, minutes=45)
    )

    # Ruta Pitesti-Rosiorii de Vede-Alexandria
    #1. Statia 1: Pitesti
    RouteStation.objects.create(
        route=ruta_retur_arges,
        station=st_pitesti,
        order=1,
        departure_time=ora_plecare_retur_arges
    )

    #2. Statia 2:Rosiorii de Vede
    RouteStation.objects.create(
        route=ruta_retur_arges,
        station=st_rosiori,
        order=2,
        departure_time=ora_plecare_retur_arges + timedelta(hours=1)
    )

    #3. Statia 3:Alexandria
    RouteStation.objects.create(
        route=ruta_retur_arges,
        station=st_alex,
        order=3,
        departure_time=ora_plecare_retur_arges + timedelta(hours=1, minutes=45)
    )

#Ruta Bucuresti-Slatina-Craiova
    # 1. Statia 1: București
    RouteStation.objects.create(
        route=ruta_oltenia,
        station=st_buc,
        order=1,
        departure_time=ruta_oltenia.departure_time
    )

    # 2. Statia 2: Slatina
    RouteStation.objects.create(
        route=ruta_oltenia,
        station=st_slatina,
        order=2,
        departure_time=ruta_oltenia.departure_time + timedelta(hours=2, minutes=30)
    )

    # 3. Statia 3: Craiova
    RouteStation.objects.create(
        route=ruta_oltenia,
        station=st_craiova,
        order=3,
        departure_time=ruta_oltenia.departure_time + timedelta(hours=4)
    )

#Ruta Craiova-Slatina-Bucuresti
# 1. Statia 1: Craiova
    RouteStation.objects.create(
        route=ruta_retur_oltenia,
        station=st_craiova,
        order=1,
        departure_time=ora_plecare_retur_oltenia
    )

    # Statia 2: Slatina
    RouteStation.objects.create(
        route=ruta_retur_oltenia,
        station=st_slatina,
        order=2,
        departure_time=ora_plecare_retur_oltenia + timedelta(hours=1, minutes=30)
    )

    # Statia 3 :Bucuresti
    RouteStation.objects.create(
        route=ruta_retur_oltenia,
        station=st_buc,
        order=3,
        departure_time=ora_plecare_retur_oltenia + timedelta(hours=4)
    )

    Ticket.objects.create(
        client=pasager1,
        route=ruta_oltenia,
        price=60.00,
        purchase_date=timezone.now()
    )

    Ticket.objects.create(
        client=pasager2,
        route=ruta_retur_oltenia,
        price=60.00,
        purchase_date=timezone.now() - timedelta(hours=2, minutes=20)
    )

    Ticket.objects.create(
        client=pasager3,
        route=ruta_sud,
        price=50.00,
        purchase_date=timezone.now() - timedelta(hours=2, minutes=10)
    )

    Ticket.objects.create(
        client=pasager4,
        route=ruta_retur_sud,
        price=50.00,
        purchase_date=timezone.now() - timedelta(hours=1, minutes=33)
    )

    Ticket.objects.create(
        client=pasager5,
        route=ruta_arges,
        price=70.00,
        purchase_date=timezone.now() - timedelta(hours=5, minutes=23)
    )

    Ticket.objects.create(
        client=pasager6,
        route=ruta_retur_oltenia,
        price=60.00,
        purchase_date=timezone.now() - timedelta(hours=4, minutes=18)
    )

    Ticket.objects.create(
        client=pasager7,
        route=ruta_arges,
        price=70.00,
        purchase_date=timezone.now() - timedelta(hours=7, minutes=8)
    )

    Ticket.objects.create(
        client=pasager8,
        route=ruta_arges,
        price=70.00,
        purchase_date=timezone.now() - timedelta(hours=2, minutes=14)
    )

    Ticket.objects.create(
        client=pasager9,
        route=ruta_retur_oltenia,
        price=60.00,
        purchase_date=timezone.now() - timedelta(hours=2, minutes=48)
    )

    Ticket.objects.create(
        client=pasager10,
        route=ruta_retur_arges,
        price=70.00,
        purchase_date=timezone.now() - timedelta(hours=3, minutes=27)
    )

    Ticket.objects.create(
        client=pasager11,
        route=ruta_sud,
        price=50.00,
        purchase_date=timezone.now() - timedelta(hours=1, minutes=38)
    )

    Ticket.objects.create(
        client=pasager12,
        route=ruta_retur_sud,
        price=50.00,
        purchase_date=timezone.now() - timedelta(hours=1, minutes=9)
    )

    Ticket.objects.create(
        client=pasager13,
        route=ruta_oltenia,
        price=60.00,
        purchase_date=timezone.now() - timedelta(hours=1, minutes=27)
    )

    print("--- POPULARE REUȘITĂ! Toate datele au fost create. ---")

if __name__ == '__main__':
    populate()