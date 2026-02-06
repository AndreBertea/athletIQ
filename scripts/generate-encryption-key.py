#!/usr/bin/env python3
"""
Script pour générer une clé de chiffrement sécurisée pour Stridelta
"""
from cryptography.fernet import Fernet
import sys

def generate_encryption_key():
    """Génère une clé de chiffrement sécurisée"""
    try:
        key = Fernet.generate_key()
        print("🔐 Clé de chiffrement générée avec succès !")
        print("=" * 50)
        print(f"ENCRYPTION_KEY={key.decode()}")
        print("=" * 50)
        print("\n📝 Instructions :")
        print("1. Copiez cette clé dans votre fichier .env")
        print("2. Remplacez 'your_secure_encryption_key_here' par cette clé")
        print("3. Gardez cette clé secrète et ne la partagez jamais")
        print("4. Utilisez une clé différente pour la production")
        return key.decode()
    except Exception as e:
        print(f"❌ Erreur lors de la génération de la clé : {e}")
        sys.exit(1)

if __name__ == "__main__":
    generate_encryption_key() 