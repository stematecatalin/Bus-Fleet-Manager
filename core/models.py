from django.db import models


class Autobuz(models.Model):
    vin = models.CharField(max_length=17)
    marca = models.CharField(max_length=50)
    model = models.CharField(max_length=50)
    nr_inmatriculare = models.CharField(max_length=50)
    capacitate = models.IntegerField()
    status = models.CharField(max_length=50)


class Utilizator(models.Model):
    nume = models.CharField(max_length=50)
    prenume = models.CharField(max_length=50)
    cnp = models.CharField(max_length=13)
    rol = models.CharField(max_length=50, null=True)
    nr_telefon = models.CharField(max_length=15)
    email = models.EmailField()
    data_angajarii = models.DateTimeField(null=True)
    username = models.CharField(max_length=50, unique=True)
    parola = models.CharField(max_length=50)


class Ruta(models.Model):
    distanta_totala = models.IntegerField()
    durata = models.IntegerField()
    ora_plecare = models.DateTimeField()
    ora_sosire = models.DateTimeField()

    utilizator = models.ForeignKey(Utilizator, on_delete=models.CASCADE,null=True)
    autobuz = models.ForeignKey(Autobuz, on_delete=models.CASCADE, null=True)


class Bilet(models.Model):
    client = models.ForeignKey(Utilizator, on_delete=models.CASCADE)
    ruta = models.ForeignKey(Ruta, on_delete=models.CASCADE)

    pret = models.DecimalField(max_digits=6, decimal_places=2)
    data_cumparare = models.DateTimeField(auto_now_add=True)


class Statie(models.Model):
    denumire = models.CharField(max_length=50)
    latitudine = models.CharField(max_length=50)
    longitudine = models.CharField(max_length=50)


class Statie_Ruta(models.Model):
    ruta = models.ForeignKey(Ruta, on_delete=models.CASCADE)
    statie = models.ForeignKey(Statie, on_delete=models.CASCADE)
    ora_plecare = models.DateTimeField()