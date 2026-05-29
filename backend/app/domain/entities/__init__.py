"""
Initialisation des entités du domaine
Résout les imports circulaires entre les modèles
"""

# Import des modèles dans l'ordre correct pour éviter les imports circulaires
from .user import User, UserCreate, UserRead, UserUpdate, StravaAuth, StravaAuthRead, GoogleAuth, GarminAuth, GarminAuthRead
from .activity import Activity, ActivityCreate, ActivityRead, ActivityWithStreams, ActivityStats, ActivitySource
from .workout_plan import WorkoutPlan, WorkoutPlanCreate, WorkoutPlanRead, WorkoutPlanUpdate
from .enrichment_queue import EnrichmentQueue, EnrichmentStatus
from .segment import Segment, SegmentRead
from .segment_features import SegmentFeatures, SegmentFeaturesRead
from .activity_weather import ActivityWeather, ActivityWeatherRead
from .garmin_daily import GarminDaily, GarminDailyRead
from .training_load import TrainingLoad, TrainingLoadRead
from .fit_metrics import FitMetrics, FitMetricsRead
from .race_prediction import (
    RacePrediction,
    RacePredictionComparison,
    RacePredictionComparisonRead,
    RacePredictorV3ResidualModel,
    RacePredictionRead,
    RaceReferenceCandidate,
    RaceValidationReference,
)
from .athletic_profile import (
    ActivityLevel,
    AthleticProfile,
    AthleticProfileRead,
    AthleticProfileUpdate,
    AthleticSex,
    ExperienceLevel,
    PracticeDominant,
    WeeklyVolumeBand,
)
from .reference_test import (
    ReferenceTest,
    ReferenceTestCreate,
    ReferenceTestQuality,
    ReferenceTestRead,
    ReferenceTestSurface,
    ReferenceTestType,
    ReferenceTestUpdate,
)
from .live_session import (
    LiveSession,
    LiveSessionSource,
    LiveSessionStatus,
    LiveSessionCreate,
    LiveSessionRead,
    LiveSessionDetail,
    LiveTrackpoint,
    LiveTrackpointRead,
)
from .coach_athlete import (
    CoachAthleteRelation,
    RelationStatus,
    CoachAthleteRelationRead,
    InviteAthleteRequest,
    AthleteSummary,
    CoachSummary,
)
from .daily_checkin import (
    DailyCheckin,
    DailyCheckinRead,
    DailyCheckinCreate,
    ReadinessScore,
)
from .gpx_route import (
    GpxRoute,
    GpxAttachment,
    GpxRouteUserSettings,
    GpxRouteSummary,
    GpxRouteDetail,
    GpxAttachmentRead,
    GpxRouteUserSettingsRead,
    GpxRouteUserSettingsUpdate,
)

__all__ = [
    "User", "UserCreate", "UserRead", "UserUpdate", "StravaAuth", "StravaAuthRead", "GoogleAuth", "GarminAuth", "GarminAuthRead",
    "Activity", "ActivityCreate", "ActivityRead", "ActivityWithStreams", "ActivityStats", "ActivitySource",
    "WorkoutPlan", "WorkoutPlanCreate", "WorkoutPlanRead", "WorkoutPlanUpdate",
    "EnrichmentQueue", "EnrichmentStatus",
    "Segment", "SegmentRead",
    "SegmentFeatures", "SegmentFeaturesRead",
    "ActivityWeather", "ActivityWeatherRead",
    "GarminDaily", "GarminDailyRead",
    "TrainingLoad", "TrainingLoadRead",
    "FitMetrics", "FitMetricsRead",
    "RacePrediction", "RacePredictionRead", "RacePredictionComparison", "RacePredictionComparisonRead", "RaceValidationReference", "RaceReferenceCandidate", "RacePredictorV3ResidualModel",
    "AthleticProfile", "AthleticProfileRead", "AthleticProfileUpdate",
    "AthleticSex", "ActivityLevel", "ExperienceLevel", "PracticeDominant", "WeeklyVolumeBand",
    "ReferenceTest", "ReferenceTestCreate", "ReferenceTestRead", "ReferenceTestUpdate",
    "ReferenceTestType", "ReferenceTestSurface", "ReferenceTestQuality",
    "LiveSession", "LiveSessionSource", "LiveSessionStatus",
    "LiveSessionCreate", "LiveSessionRead", "LiveSessionDetail",
    "LiveTrackpoint", "LiveTrackpointRead",
    "CoachAthleteRelation", "RelationStatus",
    "CoachAthleteRelationRead", "InviteAthleteRequest",
    "AthleteSummary", "CoachSummary",
    "DailyCheckin", "DailyCheckinRead", "DailyCheckinCreate", "ReadinessScore",
    "GpxRoute", "GpxAttachment", "GpxRouteUserSettings", "GpxRouteSummary", "GpxRouteDetail", "GpxAttachmentRead", "GpxRouteUserSettingsRead", "GpxRouteUserSettingsUpdate",
]
