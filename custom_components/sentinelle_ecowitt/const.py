"""Constantes pour Sentinelle Ecowitt."""

DOMAIN = "sentinelle_ecowitt"

# --- Sources primaires : capteurs de la station Ecowitt de l'utilisateur ---
CONF_TEMP_ENTITY = "temperature_entity"
CONF_HUMIDITY_ENTITY = "humidity_entity"
CONF_RAIN_ENTITY = "rain_rate_entity"
CONF_WIND_ENTITY = "wind_speed_entity"
CONF_LEAF_WETNESS_ENTITY = "leaf_wetness_entity"

# --- Sources de secours : capteurs temps réel d'une station officielle
# (typiquement l'intégration MeteoSwiss). Utilisées lorsque le capteur
# Ecowitt correspondant est absent, indisponible ou en panne. ---
CONF_FALLBACK_TEMP_ENTITY = "fallback_temperature_entity"
CONF_FALLBACK_HUMIDITY_ENTITY = "fallback_humidity_entity"
CONF_FALLBACK_WIND_ENTITY = "fallback_wind_speed_entity"
CONF_FALLBACK_RAIN_ENTITY = "fallback_rain_rate_entity"

# --- Prévisions ---
CONF_WEATHER_ENTITY = "weather_entity"

CONF_ENABLED_MODELS = "enabled_models"

# Correspondance mesure -> (entité primaire, entité de secours).
MEASUREMENT_SOURCES = {
    "temperature": (CONF_TEMP_ENTITY, CONF_FALLBACK_TEMP_ENTITY),
    "humidity": (CONF_HUMIDITY_ENTITY, CONF_FALLBACK_HUMIDITY_ENTITY),
    "wind_speed": (CONF_WIND_ENTITY, CONF_FALLBACK_WIND_ENTITY),
    "rain_rate": (CONF_RAIN_ENTITY, CONF_FALLBACK_RAIN_ENTITY),
}

# Origine effective d'une mesure, exposée en attribut d'entité.
SOURCE_PRIMARY = "ecowitt"
SOURCE_FALLBACK = "meteoswiss"
SOURCE_NONE = "unavailable"

# Modèles de risque disponibles.
MODEL_FROST = "frost"
MODEL_LATE_BLIGHT = "late_blight"
MODEL_POWDERY_MILDEW = "powdery_mildew"

AVAILABLE_MODELS = [MODEL_FROST, MODEL_LATE_BLIGHT, MODEL_POWDERY_MILDEW]
DEFAULT_ENABLED_MODELS = [MODEL_FROST]

DEFAULT_NAME = "Sentinelle"
DEFAULT_UPDATE_INTERVAL_MINUTES = 15

# Niveaux de risque partagés par tous les modèles.
RISK_NONE = "none"
RISK_WATCH = "watch"
RISK_WARNING = "warning"
RISK_SEVERE = "severe"
RISK_LEVELS = [RISK_NONE, RISK_WATCH, RISK_WARNING, RISK_SEVERE]
