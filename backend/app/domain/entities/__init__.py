"""
Initialisation des entités du domaine
Résout les imports circulaires entre les modèles
"""

# Import des modèles dans l'ordre correct pour éviter les imports circulaires
from .user import User, UserCreate, UserRead, UserUpdate, StravaAuth, StravaAuthRead, GoogleAuth
from .activity import Activity, ActivityCreate, ActivityRead, ActivityWithStreams, ActivityStats
from .workout_plan import WorkoutPlan, WorkoutPlanCreate, WorkoutPlanRead, WorkoutPlanUpdate
from .enrichment_queue import EnrichmentQueue, EnrichmentStatus
from .segment import Segment, SegmentRead
from .segment_features import SegmentFeatures, SegmentFeaturesRead
from .activity_weather import ActivityWeather, ActivityWeatherRead

__all__ = [
    "User", "UserCreate", "UserRead", "UserUpdate", "StravaAuth", "StravaAuthRead", "GoogleAuth",
    "Activity", "ActivityCreate", "ActivityRead", "ActivityWithStreams", "ActivityStats",
    "WorkoutPlan", "WorkoutPlanCreate", "WorkoutPlanRead", "WorkoutPlanUpdate",
    "EnrichmentQueue", "EnrichmentStatus",
    "Segment", "SegmentRead",
    "SegmentFeatures", "SegmentFeaturesRead",
    "ActivityWeather", "ActivityWeatherRead",
] 