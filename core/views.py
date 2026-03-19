from django.shortcuts import render
import json

def index(request):
    # 1. Statiile noastre (bulinele)
    statii = [
        {"id": 1, "nume": "Gara de Nord", "lat": 44.4455, "lng": 26.0751},
        {"id": 2, "nume": "Piața Victoriei", "lat": 44.4518, "lng": 26.0858},
        {"id": 3, "nume": "Piața Romană", "lat": 44.4468, "lng": 26.0975},
    ]
    
    # 2. Ruta (punctele prin care trece linia)
    # Acestea sunt practic latitudinile si longitudinile in ordine
    ruta_puncte = [
        [44.4455, 26.0751], # Plecare Gara de Nord
        [44.4500, 26.0800], # Un punct intermediar pe strada
        [44.4518, 26.0858], # Statie Victoriei
        [44.4490, 26.0920], # Alta curba
        [44.4468, 26.0975],
        # Sosire Romana
    ]
    
    context = {
        'statii_json': json.dumps(statii),
        'ruta_json': json.dumps(ruta_puncte)
    }
    return render(request, "core/index.html", context)
