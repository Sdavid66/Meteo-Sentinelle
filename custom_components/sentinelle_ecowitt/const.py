"""Constantes pour Sentinelle Ecowitt."""

DOMAIN = "sentinelle_ecowitt"

# Entités source configurées par l'utilisateur (issues de l'intégration
# Ecowitt native ou de toute autre source compatible).
CONF_TEMP_ENTITY = "temperature_entity"
CONF_HUMIDITY_ENTITY = "humidity_entity"
CONF_RAIN_ENTITY = "rain_rate_entity"
CONF_WIND_ENTITY = "wind_speed_entity"
CONF_LEAF_WETNESS_ENTITY = "leaf_wetness_entity"
CONF_WEATHER_ENTITY = "weather_entity"
CONF_ENABLED_MODELS = "enabled_models"

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
