#!/usr/bin/env python3
"""
Script pour tester la configuration Google Calendar de Stridelta
"""
import os
import sys
import requests
from urllib.parse import urlencode

def test_google_config():
    """Teste la configuration Google Calendar"""
    print("🔍 Test de la configuration Google Calendar pour Stridelta")
    print("=" * 60)
    
    # Vérifier les variables d'environnement
    required_vars = [
        'GOOGLE_CLIENT_ID',
        'GOOGLE_CLIENT_SECRET', 
        'GOOGLE_REDIRECT_URI',
        'ENCRYPTION_KEY'
    ]
    
    missing_vars = []
    for var in required_vars:
        value = os.getenv(var)
        if not value or value.startswith('your_'):
            missing_vars.append(var)
            print(f"❌ {var}: Non configuré")
        else:
            print(f"✅ {var}: Configuré")
    
    if missing_vars:
        print("\n❌ Variables manquantes :")
        for var in missing_vars:
            print(f"   - {var}")
        print("\n📝 Veuillez configurer ces variables dans votre fichier .env")
        return False
    
    # Tester la génération de l'URL d'autorisation
    try:
        client_id = os.getenv('GOOGLE_CLIENT_ID')
        redirect_uri = os.getenv('GOOGLE_REDIRECT_URI')
        
        auth_params = {
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': 'https://www.googleapis.com/auth/calendar https://www.googleapis.com/auth/calendar.events',
            'access_type': 'offline',
            'prompt': 'consent'
        }
        
        auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(auth_params)}"
        
        print("\n✅ URL d'autorisation générée avec succès")
        print(f"🔗 URL: {auth_url}")
        
        # Tester la connectivité
        print("\n🌐 Test de connectivité...")
        response = requests.get("https://accounts.google.com", timeout=5)
        if response.status_code == 200:
            print("✅ Connectivité Google OK")
        else:
            print(f"⚠️  Connectivité Google: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Erreur lors du test : {e}")
        return False
    
    # Tester le backend
    print("\n🔧 Test du backend Stridelta...")
    try:
        response = requests.get("http://localhost:8000/health", timeout=5)
        if response.status_code == 200:
            print("✅ Backend Stridelta accessible")
        else:
            print(f"⚠️  Backend Stridelta: {response.status_code}")
    except requests.exceptions.ConnectionError:
        print("❌ Backend Stridelta non accessible")
        print("   Assurez-vous que le backend est démarré avec :")
        print("   cd backend && ./start_backend_optimized.sh")
    except Exception as e:
        print(f"❌ Erreur lors du test du backend : {e}")
    
    print("\n" + "=" * 60)
    print("🎉 Test terminé !")
    print("\n📋 Prochaines étapes :")
    print("1. Démarrer le backend Stridelta")
    print("2. Ouvrir l'application dans le navigateur")
    print("3. Tester la connexion Google Calendar")
    
    return True

if __name__ == "__main__":
    # Charger les variables d'environnement depuis .env
    env_file = os.path.join(os.path.dirname(__file__), '..', 'backend', '.env')
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value
    
    test_google_config() 