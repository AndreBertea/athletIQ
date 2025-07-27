#!/usr/bin/env python3
"""
Script de test pour l'intégration Google Calendar
"""
import requests
import json
import sys
from datetime import datetime, timedelta

# Configuration
API_BASE_URL = "http://localhost:8000/api/v1"
TEST_EMAIL = "test@example.com"
TEST_PASSWORD = "testpassword123"

def get_auth_token():
    """Récupère un token d'authentification"""
    print("🔐 Authentification...")
    
    login_data = {
        "username": TEST_EMAIL,
        "password": TEST_PASSWORD
    }
    
    response = requests.post(f"{API_BASE_URL}/auth/login", data=login_data)
    
    if response.status_code == 200:
        token_data = response.json()
        return token_data["access_token"]
    else:
        print(f"❌ Erreur d'authentification: {response.status_code}")
        print(response.text)
        return None

def test_google_status(token):
    """Teste le statut de la connexion Google"""
    print("\n📊 Test du statut Google Calendar...")
    
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{API_BASE_URL}/auth/google/status", headers=headers)
    
    if response.status_code == 200:
        status = response.json()
        print(f"✅ Statut Google Calendar: {status}")
        return status["connected"]
    else:
        print(f"❌ Erreur lors de la récupération du statut: {response.status_code}")
        print(response.text)
        return False

def test_google_login_url(token):
    """Teste la génération de l'URL de connexion Google"""
    print("\n🔗 Test de l'URL de connexion Google...")
    
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{API_BASE_URL}/auth/google/login", headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ URL de connexion générée: {data['authorization_url']}")
        return True
    else:
        print(f"❌ Erreur lors de la génération de l'URL: {response.status_code}")
        print(response.text)
        return False

def test_google_calendars(token):
    """Teste la récupération des calendriers Google"""
    print("\n📅 Test de la récupération des calendriers...")
    
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{API_BASE_URL}/google-calendar/calendars", headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        calendars = data.get("calendars", [])
        print(f"✅ {len(calendars)} calendriers trouvés:")
        for cal in calendars:
            print(f"  - {cal['summary']} (ID: {cal['id']})")
        return True
    else:
        print(f"❌ Erreur lors de la récupération des calendriers: {response.status_code}")
        print(response.text)
        return False

def test_export_workout_plans(token):
    """Teste l'export des plans d'entraînement"""
    print("\n📤 Test de l'export des plans d'entraînement...")
    
    headers = {"Authorization": f"Bearer {token}"}
    data = {"calendar_id": "primary"}
    
    response = requests.post(f"{API_BASE_URL}/google-calendar/export", json=data, headers=headers)
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Export réussi: {result}")
        return True
    else:
        print(f"❌ Erreur lors de l'export: {response.status_code}")
        print(response.text)
        return False

def test_import_calendar(token):
    """Teste l'import depuis Google Calendar"""
    print("\n📥 Test de l'import depuis Google Calendar...")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Période de test (7 jours)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)
    
    data = {
        "calendar_id": "primary",
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d")
    }
    
    response = requests.post(f"{API_BASE_URL}/google-calendar/import", data=data, headers=headers)
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Import réussi: {result}")
        return True
    else:
        print(f"❌ Erreur lors de l'import: {response.status_code}")
        print(response.text)
        return False

def main():
    """Fonction principale de test"""
    print("🧪 Test de l'intégration Google Calendar")
    print("=" * 50)
    
    # Récupérer le token d'authentification
    token = get_auth_token()
    if not token:
        print("❌ Impossible de récupérer le token d'authentification")
        sys.exit(1)
    
    print(f"✅ Token récupéré: {token[:20]}...")
    
    # Tests
    tests = [
        ("Statut Google", lambda: test_google_status(token)),
        ("URL de connexion", lambda: test_google_login_url(token)),
        ("Calendriers", lambda: test_google_calendars(token)),
        ("Export", lambda: test_export_workout_plans(token)),
        ("Import", lambda: test_import_calendar(token))
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ Erreur lors du test {test_name}: {e}")
            results.append((test_name, False))
    
    # Résumé
    print("\n" + "=" * 50)
    print("📋 Résumé des tests:")
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\n🎯 Résultat: {passed}/{total} tests réussis")
    
    if passed == total:
        print("🎉 Tous les tests sont passés !")
        sys.exit(0)
    else:
        print("⚠️  Certains tests ont échoué")
        sys.exit(1)

if __name__ == "__main__":
    main() 