"""Constantes pour Météo Sentinelle."""

DOMAIN = "meteo_sentinelle"

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

# --- Arbres / cultures surveillés (sous-entrées) ---
SUBENTRY_TYPE_TREE = "tree"

CONF_CROP = "crop"
CONF_STAGE = "stage"
CONF_TREE_NAME = "tree_name"
CONF_AUTO_ADVANCE = "auto_advance"
CONF_GDD_OFFSET = "gdd_offset"

DEFAULT_AUTO_ADVANCE = True
DEFAULT_GDD_OFFSET = 0.0

# --- Alerting ---
CONF_NOTIFICATIONS = "notifications"
DEFAULT_NOTIFICATIONS = True

EVENT_RISK_CHANGED = f"{DOMAIN}_risk_changed"
EVENT_STAGE_ADVANCED = f"{DOMAIN}_stage_advanced"

#: Niveaux à partir desquels une notification persistante est créée.
NOTIFY_FROM_LEVEL = "warning"

# --- Oïdium : extension pluie hors Gubler-Thomas d'origine ---
CONF_RAIN_PENALTY = "powdery_mildew_rain_penalty"

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

#: Modèles maladie pertinents pour chaque espèce. Le gel s'applique à
#: toutes. Appliquer le mildiou de la pomme de terre à un pommier n'aurait
#: aucun sens agronomique : chaque arbre ne reçoit que ce qui le concerne.
CROP_DISEASE_MODELS: dict[str, list[str]] = {
    "apple": [MODEL_POWDERY_MILDEW],
    "pear": [MODEL_POWDERY_MILDEW],
    "apricot": [MODEL_POWDERY_MILDEW],
    "plum": [MODEL_POWDERY_MILDEW],
    "peach": [MODEL_POWDERY_MILDEW],
    "sweet_cherry": [MODEL_POWDERY_MILDEW],
    "vine": [MODEL_POWDERY_MILDEW, MODEL_LATE_BLIGHT],
    "potato": [MODEL_LATE_BLIGHT],
    "tender_annual": [MODEL_LATE_BLIGHT, MODEL_POWDERY_MILDEW],
    "hardy_vegetable": [MODEL_POWDERY_MILDEW],
    "generic": [MODEL_LATE_BLIGHT, MODEL_POWDERY_MILDEW],
}

#: Modèles pouvant faire l'objet d'un traitement phytosanitaire.
TREATABLE_MODELS = [MODEL_LATE_BLIGHT, MODEL_POWDERY_MILDEW]

DEFAULT_NAME = "Sentinelle"
DEFAULT_UPDATE_INTERVAL_MINUTES = 15
#: Profondeur d'historique interrogée pour les modèles maladie.
HISTORY_HOURS = 96

# Niveaux de risque partagés par tous les modèles.
RISK_NONE = "none"
RISK_WATCH = "watch"
RISK_WARNING = "warning"
RISK_SEVERE = "severe"
RISK_LEVELS = [RISK_NONE, RISK_WATCH, RISK_WARNING, RISK_SEVERE]

# --- Services ---
SERVICE_LOG_TREATMENT = "log_treatment"
SERVICE_CLEAR_TREATMENT = "clear_treatment"
SERVICE_RESET_MILDEW_INDEX = "reset_powdery_mildew_index"
SERVICE_SET_STAGE = "set_stage"

ATTR_TARGET = "target"
ATTR_PRODUCT = "product"
ATTR_RESIDUAL_DAYS = "residual_days"
ATTR_RAINFAST_MM = "rainfast_mm"
ATTR_TREE = "tree"
ATTR_STAGE = "stage"

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.state"
