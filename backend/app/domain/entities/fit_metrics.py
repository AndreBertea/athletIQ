"""
Entité FitMetrics - Domain Layer
Données extraites des fichiers FIT Garmin.
Contient les métriques session (moyennes/totaux) et métadonnées.
Les streams par seconde sont stockés dans activity.streams_data.
Relation 1:1 avec Activity (même pattern que ActivityWeather).
"""
from sqlmodel import SQLModel, Field
from typing import Optional
from uuid import UUID, uuid4
from datetime import datetime


class FitMetrics(SQLModel, table=True):
    """Métriques FIT pour une activité, une entrée par activité."""
    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    activity_id: UUID = Field(foreign_key="activity.id", unique=True, index=True)

    # Running Dynamics (moyennes session)
    ground_contact_time_avg: Optional[float] = None  # ms
    vertical_oscillation_avg: Optional[float] = None  # mm
    stance_time_balance_avg: Optional[float] = None  # % (G/D)
    stance_time_percent_avg: Optional[float] = None  # %
    step_length_avg: Optional[float] = None  # mm
    vertical_ratio_avg: Optional[float] = None  # %

    # Puissance
    power_avg: Optional[float] = None  # W
    power_max: Optional[float] = None  # W
    normalized_power: Optional[float] = None  # W

    # Cadence
    cadence_avg: Optional[float] = None  # strides/min
    cadence_max: Optional[float] = None  # strides/min

    # Fréquence cardiaque (depuis session FIT)
    heart_rate_avg: Optional[int] = None  # bpm
    heart_rate_max: Optional[int] = None  # bpm

    # Vitesse (depuis session FIT)
    speed_avg: Optional[float] = None  # m/s
    speed_max: Optional[float] = None  # m/s

    # Température capteur
    temperature_avg: Optional[float] = None  # °C
    temperature_max: Optional[float] = None  # °C

    # Training Effect
    aerobic_training_effect: Optional[float] = None  # 0.0-5.0
    anaerobic_training_effect: Optional[float] = None  # 0.0-5.0

    # Totaux session
    total_calories: Optional[int] = None  # kcal
    total_strides: Optional[int] = None
    total_ascent: Optional[int] = None  # m
    total_descent: Optional[int] = None  # m
    total_distance: Optional[float] = None  # m
    total_timer_time: Optional[float] = None  # s
    total_elapsed_time: Optional[float] = None  # s

    # Metadata
    record_count: Optional[int] = None
    fit_downloaded_at: Optional[datetime] = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class FitMetricsRead(SQLModel):
    """Schéma pour lire les métriques FIT (réponse API)."""
    id: UUID
    activity_id: UUID

    # Running Dynamics
    ground_contact_time_avg: Optional[float]
    vertical_oscillation_avg: Optional[float]
    stance_time_balance_avg: Optional[float]
    stance_time_percent_avg: Optional[float]
    step_length_avg: Optional[float]
    vertical_ratio_avg: Optional[float]

    # Puissance
    power_avg: Optional[float]
    power_max: Optional[float]
    normalized_power: Optional[float]

    # Cadence
    cadence_avg: Optional[float]
    cadence_max: Optional[float]

    # FC
    heart_rate_avg: Optional[int]
    heart_rate_max: Optional[int]

    # Vitesse
    speed_avg: Optional[float]
    speed_max: Optional[float]

    # Température
    temperature_avg: Optional[float]
    temperature_max: Optional[float]

    # Training Effect
    aerobic_training_effect: Optional[float]
    anaerobic_training_effect: Optional[float]

    # Totaux
    total_calories: Optional[int]
    total_strides: Optional[int]
    total_ascent: Optional[int]
    total_descent: Optional[int]
    total_distance: Optional[float]
    total_timer_time: Optional[float]
    total_elapsed_time: Optional[float]

    # Metadata
    record_count: Optional[int]
    fit_downloaded_at: Optional[datetime]
