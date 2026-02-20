**🌍 Idioma / Language:** [🇪🇸 Español](README.es.md) · [🇬🇧 English](../README.md) · [🇩🇪 Deutsch](README.de.md) · [🇫🇷 Français](README.fr.md)

---

[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.9.0%2B-blue.svg)](https://www.home-assistant.io/)
[![HACS](https://img.shields.io/badge/HACS-Ready-41BDF5.svg)](https://hacs.xyz/)
[![Tests](https://github.com/BigDaddy1990/pawcontrol/actions/workflows/ci.yml/badge.svg)](https://github.com/BigDaddy1990/pawcontrol/actions/workflows/ci.yml)

# 🐕 PawControl – Compañero de Home Assistant para hogares con varios perros

**PawControl** es una integración completa de Home Assistant para la gestión inteligente de perros, con seguimiento GPS, recordatorios de alimentación automatizados, monitoreo de salud y flujos de automatización avanzados.

## ✨ Características principales

🔧 **Configuración sencilla** – Configuración completa basada en interfaz de usuario  
🍽️ **Alimentación inteligente** – Seguimiento de comidas con control de porciones y recordatorios adaptados a la salud  
🗺️ **Seguimiento GPS avanzado** – Monitoreo en tiempo real con geovallas y registro de rutas  
🏥 **Monitoreo de salud** – Seguimiento de peso, recordatorios de medicamentos, citas veterinarias  
📱 **Integración móvil** – Notificaciones con soporte iOS/Android  
🏠 **Integración domótica** – Sensores de puerta, automatizaciones meteorológicas  
📊 **Paneles generados automáticamente** – Interfaz adaptable con análisis detallados  
🔔 **Notificaciones inteligentes** – Alertas contextuales con protocolos de emergencia  

## 🚀 Instalación

### Mediante HACS (recomendado)
1. Abrir HACS en Home Assistant
2. **Integraciones** → menú superior derecho → **Repositorios personalizados**
3. Introducir `https://github.com/BigDaddy1990/pawcontrol`, categoría **Integración**
4. Buscar « PawControl » e instalar
5. Reiniciar Home Assistant

## ⚙️ Configuración

1. `Ajustes → Dispositivos y servicios → Añadir integración`
2. Buscar « PawControl »
3. Crear uno o varios perros (nombre, tamaño, peso)
4. Activar los módulos deseados (Alimentación, GPS, Salud, Meteorología…)
5. Asignar entidades externas (rastreador GPS, sensor de puerta, entidad meteorológica)

## 🤝 Contribuir

¡Las contribuciones son bienvenidas! La traducción al español es un stub —
abra `custom_components/pawcontrol/translations/es.json` y complete las
cadenas, luego envíe una Pull Request.

📖 [CONTRIBUTING.md](../CONTRIBUTING.md) · 🐛 [Issues](https://github.com/BigDaddy1990/pawcontrol/issues)

## 📄 Licencia

MIT – ver [LICENSE](../LICENSE)
