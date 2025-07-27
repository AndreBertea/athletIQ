#!/usr/bin/env python3
"""
Script de test pour l'import CSV des plans d'entraînement
"""
import requests
import json
from pathlib import Path

# Configuration
API_BASE_URL = "http://localhost:8000/api/v1"
CSV_FILE_PATH = Path("../plan_entrainement.csv")

def test_csv_import():
    """Teste l'import CSV des plans d'entraînement"""
    
    print("🧪 Test d'import CSV des plans d'entraînement")
    print("=" * 50)
    
    # 1. Vérifier que le fichier CSV existe
    if not CSV_FILE_PATH.exists():
        print(f"❌ Fichier CSV non trouvé : {CSV_FILE_PATH}")
        return
    
    print(f"✅ Fichier CSV trouvé : {CSV_FILE_PATH}")
    
    # 2. Lire le contenu du fichier CSV
    try:
        with open(CSV_FILE_PATH, 'r', encoding='utf-8') as f:
            csv_content = f.read()
        print(f"✅ Contenu CSV lu ({len(csv_content)} caractères)")
    except Exception as e:
        print(f"❌ Erreur lors de la lecture du fichier CSV : {e}")
        return
    
    # 3. Analyser le contenu CSV
    lines = csv_content.strip().split('\n')
    if len(lines) < 2:
        print("❌ Fichier CSV invalide (moins de 2 lignes)")
        return
    
    header = lines[0].split('\t')
    data_lines = lines[1:]
    
    print(f"✅ En-têtes détectés : {header}")
    print(f"✅ {len(data_lines)} lignes de données")
    
    # 4. Afficher un aperçu des données
    print("\n📊 Aperçu des données :")
    for i, line in enumerate(data_lines[:5]):  # Premières 5 lignes
        fields = line.split('\t')
        if len(fields) >= 6:
            phase = fields[0] if len(fields) > 0 else "N/A"
            semaine = fields[1] if len(fields) > 1 else "N/A"
            date = fields[2] if len(fields) > 2 else "N/A"
            type_entrainement = fields[3] if len(fields) > 3 else "N/A"
            km = fields[4] if len(fields) > 4 else "N/A"
            dplus = fields[5] if len(fields) > 5 else "N/A"
            
            print(f"  {i+1}. {date} - {type_entrainement} - {km}km ({dplus}m D+) - Phase: {phase}")
    
    if len(data_lines) > 5:
        print(f"  ... et {len(data_lines) - 5} autres lignes")
    
    # 5. Test de l'API (si disponible)
    print("\n🌐 Test de l'API d'import CSV")
    print("Note : Ce test nécessite que le backend soit démarré et accessible")
    
    try:
        # Préparer le fichier pour l'upload
        files = {
            'file': ('plan_entrainement.csv', csv_content, 'text/csv')
        }
        
        # Headers (sans authentification pour ce test)
        headers = {
            'Content-Type': 'multipart/form-data'
        }
        
        # Appel API
        response = requests.post(
            f"{API_BASE_URL}/workout-plans/import-csv",
            files=files,
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Import CSV réussi !")
            print(f"   Plans importés : {result.get('imported_count', 0)}")
            print(f"   Total traité : {result.get('total_count', 0)}")
            if result.get('errors'):
                print(f"   Erreurs : {len(result['errors'])}")
                for error in result['errors'][:3]:  # Afficher les 3 premières erreurs
                    print(f"     - {error}")
        else:
            print(f"❌ Erreur API : {response.status_code}")
            print(f"   Réponse : {response.text}")
            
    except requests.exceptions.ConnectionError:
        print("⚠️  Backend non accessible (démarrez-le avec 'python -m uvicorn app.main:app --reload')")
    except Exception as e:
        print(f"❌ Erreur lors du test API : {e}")
    
    print("\n" + "=" * 50)
    print("✅ Test terminé")

if __name__ == "__main__":
    test_csv_import() 