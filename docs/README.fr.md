**🌍 Langue / Language:** [🇫🇷 Français](README.fr.md) · [🇬🇧 English](../README.md) · [🇩🇪 Deutsch](README.de.md) · [🇪🇸 Español](README.es.md)

---

[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.9.0%2B-blue.svg)](https://www.home-assistant.io/)
[![HACS](https://img.shields.io/badge/HACS-Ready-41BDF5.svg)](https://hacs.xyz/)
[![Tests](https://github.com/BigDaddy1990/pawcontrol/actions/workflows/ci.yml/badge.svg)](https://github.com/BigDaddy1990/pawcontrol/actions/workflows/ci.yml)

# 🐕 PawControl – Compagnon Home Assistant pour les foyers multi-chiens

**PawControl** est une intégration Home Assistant complète pour la gestion intelligente des chiens, avec suivi GPS, rappels d'alimentation automatisés, surveillance de la santé et workflows d'automatisation avancés.

## ✨ Fonctionnalités principales

🔧 **Configuration facile** – Configuration complète via l'interface utilisateur  
🍽️ **Alimentation intelligente** – Suivi des repas avec contrôle des portions et rappels adaptés à la santé  
🗺️ **Suivi GPS avancé** – Surveillance en temps réel avec géofencing et enregistrement de parcours  
🏥 **Surveillance de la santé** – Suivi du poids, rappels de médicaments, rendez-vous vétérinaires  
📱 **Intégration mobile** – Notifications avec support iOS/Android  
🏠 **Intégration domotique** – Capteurs de porte, automations météo  
📊 **Tableaux de bord générés automatiquement** – Interface responsive avec analyses détaillées  
🔔 **Notifications intelligentes** – Alertes contextuelles avec protocoles d'urgence  

## 🚀 Installation

### Via HACS (recommandé)
1. Ouvrir HACS dans Home Assistant
2. **Intégrations** → menu en haut à droite → **Dépôts personnalisés**
3. Saisir `https://github.com/BigDaddy1990/pawcontrol`, catégorie **Intégration**
4. Rechercher « PawControl » et installer
5. Redémarrer Home Assistant

## ⚙️ Configuration

1. `Paramètres → Appareils et services → Ajouter une intégration`
2. Rechercher « PawControl »
3. Créer un ou plusieurs chiens (nom, taille, poids)
4. Activer les modules souhaités (Alimentation, GPS, Santé, Météo…)
5. Attribuer les entités externes (tracker GPS, capteur de porte, météo)

## 🤝 Contribuer

Les contributions sont les bienvenues ! La traduction française est un stub –
ouvrez `custom_components/pawcontrol/translations/fr.json` et complétez les
chaînes, puis soumettez une Pull Request.

📖 [CONTRIBUTING.md](../CONTRIBUTING.md) · 🐛 [Issues](https://github.com/BigDaddy1990/pawcontrol/issues)

## 📄 Licence

MIT – voir [LICENSE](../LICENSE)
