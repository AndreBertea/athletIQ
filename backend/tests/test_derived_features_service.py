"""
Tests pour derived_features_service — Tache 4.2.1 / 4.5
Valide Minetti, grade_variability, cardiac_drift, cadence_decay, efficiency_factor,
TRIMP, CTL/ATL/TSB convergence.
"""
import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch, PropertyMock
from uuid import uuid4

from app.domain.services.derived_features_service import (
    minetti_cost,
    compute_trimp,
    compute_segment_features,
    compute_training_load,
    _compute_grade_variability,
    _compute_cardiac_drift,
    _compute_cadence_decay,
    _compute_efficiency_factor,
    _get_rhr_delta_7d,
    _get_daily_trimp,
)


# --- Helpers ---

def _make_segment(
    segment_index=0,
    avg_grade_percent=None,
    avg_hr=None,
    avg_cadence=None,
    pace_min_per_km=None,
    distance_m=100.0,
    elapsed_time_s=30.0,
):
    seg = MagicMock()
    seg.id = uuid4()
    seg.activity_id = uuid4()
    seg.segment_index = segment_index
    seg.avg_grade_percent = avg_grade_percent
    seg.avg_hr = avg_hr
    seg.avg_cadence = avg_cadence
    seg.pace_min_per_km = pace_min_per_km
    seg.distance_m = distance_m
    seg.elapsed_time_s = elapsed_time_s
    return seg


# ===================================================================
# Tests Minetti (4.5.1)
# ===================================================================

class TestMinettiCost:
    def test_grade_zero(self):
        """Grade 0 -> ~3.6 J/(kg*m)."""
        assert abs(minetti_cost(0.0) - 3.6) < 0.01

    def test_grade_negative_01(self):
        """Grade -0.1 -> valeur proche du minimum."""
        val = minetti_cost(-0.1)
        assert val < minetti_cost(0.0)
        assert val > 0  # Cout toujours positif pour -10%

    def test_minimum_around_negative_018(self):
        """Le minimum se trouve autour de grade -0.15 a -0.20."""
        vals = [(g / 100.0, minetti_cost(g / 100.0)) for g in range(-25, 0)]
        min_grade, min_val = min(vals, key=lambda x: x[1])
        assert -0.25 < min_grade < -0.10

    def test_positive_grade_higher_cost(self):
        """Grade positif -> cout plus eleve que plat."""
        assert minetti_cost(0.1) > minetti_cost(0.0)
        assert minetti_cost(0.2) > minetti_cost(0.1)

    def test_steep_downhill_still_positive(self):
        """Meme une forte descente a un cout positif (freinage)."""
        assert minetti_cost(-0.25) > 0

    def test_known_values(self):
        """Grade 0 -> exactement 3.6 (terme constant du polynome)."""
        assert minetti_cost(0.0) == pytest.approx(3.6, abs=0.001)

    # --- Tests 4.5.1 : Validation Minetti contre valeurs connues ---

    def test_grade_zero_exact(self):
        """Grade 0 -> 3.6 J/(kg*m) exactement (terme constant du polynome Minetti)."""
        assert minetti_cost(0.0) == pytest.approx(3.6, abs=1e-6)

    def test_grade_neg_010_known_value(self):
        """Grade -0.10 -> ~2.15 J/(kg*m) (valeur tabulee du polynome)."""
        assert minetti_cost(-0.10) == pytest.approx(2.1517, abs=0.01)

    def test_grade_neg_020_known_value(self):
        """Grade -0.20 -> ~1.80 J/(kg*m) (proche du minimum)."""
        assert minetti_cost(-0.20) == pytest.approx(1.80, abs=0.01)

    def test_grade_pos_010_known_value(self):
        """Grade +0.10 -> ~5.97 J/(kg*m) (valeur tabulee)."""
        assert minetti_cost(0.10) == pytest.approx(5.9682, abs=0.01)

    def test_grade_pos_020_known_value(self):
        """Grade +0.20 -> ~9.01 J/(kg*m) (valeur tabulee)."""
        assert minetti_cost(0.20) == pytest.approx(9.0067, abs=0.01)

    def test_minimum_value_approx_178(self):
        """Le minimum du polynome est ~1.78 J/(kg*m) a grade ~-0.18."""
        # Balayage fin pour trouver le minimum
        best_cost = float("inf")
        best_grade = 0.0
        for g_int in range(-250, 0):
            g = g_int / 1000.0
            c = minetti_cost(g)
            if c < best_cost:
                best_cost = c
                best_grade = g
        assert best_cost == pytest.approx(1.78, abs=0.02)
        assert best_grade == pytest.approx(-0.181, abs=0.005)

    def test_minimum_is_at_negative_grade(self):
        """Le cout minimum n'est PAS a grade 0 mais a une pente negative (descente optimale)."""
        assert minetti_cost(-0.18) < minetti_cost(0.0)
        assert minetti_cost(-0.18) < minetti_cost(-0.10)
        assert minetti_cost(-0.18) < minetti_cost(-0.25)

    def test_symmetry_uphill_costlier_than_downhill(self):
        """A meme pente absolue, monter coute plus cher que descendre."""
        for g in [0.05, 0.10, 0.15, 0.20, 0.25]:
            assert minetti_cost(g) > minetti_cost(-g)

    def test_cost_always_positive_in_running_range(self):
        """Le cout est toujours positif dans la plage de pente courante [-0.45, +0.45]."""
        for g_int in range(-45, 46):
            g = g_int / 100.0
            assert minetti_cost(g) > 0, f"Cout negatif a grade {g}"


# ===================================================================
# Tests Grade Variability
# ===================================================================

class TestGradeVariability:
    def test_flat_course(self):
        """Parcours plat -> variabilite ~0."""
        segments = [_make_segment(i, avg_grade_percent=0.0) for i in range(10)]
        result = _compute_grade_variability(segments)
        for v in result.values():
            assert v == pytest.approx(0.0, abs=0.01)

    def test_variable_course(self):
        """Parcours avec grades varies -> variabilite > 0."""
        grades = [0.0, 5.0, -3.0, 8.0, -5.0, 2.0, 10.0, -2.0]
        segments = [_make_segment(i, avg_grade_percent=g) for i, g in enumerate(grades)]
        result = _compute_grade_variability(segments)
        for v in result.values():
            assert v > 0

    def test_none_grade(self):
        """Segments sans grade -> None."""
        segments = [_make_segment(0, avg_grade_percent=None)]
        result = _compute_grade_variability(segments)
        assert list(result.values())[0] is None

    def test_single_segment(self):
        """Un seul segment avec grade -> variabilite 0."""
        segments = [_make_segment(0, avg_grade_percent=5.0)]
        result = _compute_grade_variability(segments)
        assert list(result.values())[0] == pytest.approx(0.0, abs=0.01)


# ===================================================================
# Tests Cardiac Drift (4.5.4)
# ===================================================================

class TestCardiacDrift:
    def test_no_drift(self):
        """HR et pace constants -> drift ~0."""
        segments = [
            _make_segment(i, avg_hr=150.0, pace_min_per_km=5.0)
            for i in range(10)
        ]
        result = _compute_cardiac_drift(segments)
        for v in result.values():
            assert v == pytest.approx(0.0, abs=0.01)

    def test_positive_drift(self):
        """HR qui augmente a pace constante -> drift positif."""
        segments = []
        for i in range(10):
            hr = 140 + i * 2  # 140 -> 158
            segments.append(_make_segment(i, avg_hr=hr, pace_min_per_km=5.0))
        result = _compute_cardiac_drift(segments)
        drift_val = list(result.values())[0]
        assert drift_val is not None
        assert drift_val > 0

    def test_insufficient_segments(self):
        """Moins de 4 segments -> None."""
        segments = [
            _make_segment(0, avg_hr=150.0, pace_min_per_km=5.0),
            _make_segment(1, avg_hr=152.0, pace_min_per_km=5.0),
        ]
        result = _compute_cardiac_drift(segments)
        for v in result.values():
            assert v is None

    def test_no_hr(self):
        """Pas de HR -> None."""
        segments = [_make_segment(i, avg_hr=None, pace_min_per_km=5.0) for i in range(10)]
        result = _compute_cardiac_drift(segments)
        for v in result.values():
            assert v is None

    def test_same_value_all_segments(self):
        """Drift est une metrique globale : meme valeur pour tous les segments."""
        segments = [
            _make_segment(i, avg_hr=140 + i, pace_min_per_km=5.0)
            for i in range(8)
        ]
        result = _compute_cardiac_drift(segments)
        values = list(result.values())
        assert all(v == values[0] for v in values)


# ===================================================================
# Tests Cardiac Drift avec mock HR croissant (4.5.4)
# ===================================================================

class TestCardiacDriftMockHR:
    """Tests approfondis du cardiac drift avec profils HR realistes."""

    def test_linear_hr_rise_constant_pace(self):
        """HR lineairement croissant (140->170) a pace constant -> drift positif calculable.

        1ere moitie (5 segs) : HR moyen = (140+142+144+146+148)/5 = 144, pace = 5.0
        2eme moitie (5 segs) : HR moyen = (150+152+154+156+158)/5 = 154, pace = 5.0
        ratio_1 = 144/5 = 28.8, ratio_2 = 154/5 = 30.8
        drift = 30.8/28.8 - 1 = 0.0694...
        """
        segments = [
            _make_segment(i, avg_hr=140 + i * 2, pace_min_per_km=5.0)
            for i in range(10)
        ]
        result = _compute_cardiac_drift(segments)
        drift = list(result.values())[0]
        assert drift is not None
        # Valeur exacte : (154/5) / (144/5) - 1 = 154/144 - 1
        expected = (154.0 / 144.0) - 1.0
        assert drift == pytest.approx(expected, abs=0.001)

    def test_steep_hr_rise_large_drift(self):
        """HR qui monte fortement (130->190) -> drift eleve (>10%).

        Simule un effort en seuil ou la derive cardiaque est importante.
        """
        segments = [
            _make_segment(i, avg_hr=130 + i * 6.67, pace_min_per_km=4.5)
            for i in range(10)
        ]
        result = _compute_cardiac_drift(segments)
        drift = list(result.values())[0]
        assert drift is not None
        assert drift > 0.10  # >10% de derive

    def test_hr_rise_with_pace_slowdown(self):
        """HR augmente ET pace ralentit -> le ratio HR/pace peut diminuer.

        Cardiac drift = (HR/pace)_2nd / (HR/pace)_1st - 1.
        Si pace augmente proportionnellement plus que HR, le ratio HR/pace
        diminue et le drift est negatif. C'est correct : le ratio mesure
        l'efficacite cardiaque par unite de vitesse.
        """
        segments = []
        for i in range(10):
            hr = 145 + i * 2      # 145 -> 163 (+12.4%)
            pace = 5.0 + i * 0.1  # 5.0 -> 5.9 (+18%)
            segments.append(_make_segment(i, avg_hr=hr, pace_min_per_km=pace))
        result = _compute_cardiac_drift(segments)
        drift = list(result.values())[0]
        assert drift is not None
        # pace augmente plus vite que HR -> ratio HR/pace diminue -> drift < 0
        assert drift < 0

    def test_hr_rise_with_pace_speedup_reduces_drift(self):
        """HR augmente mais pace accelere -> drift reduit ou negatif.

        Ex: un runner en negative split (accelere en 2eme moitie).
        """
        segments = []
        for i in range(10):
            hr = 145 + i * 1     # 145 -> 154 (legere hausse)
            pace = 5.5 - i * 0.1 # 5.5 -> 4.6 (acceleration)
            segments.append(_make_segment(i, avg_hr=hr, pace_min_per_km=pace))
        result = _compute_cardiac_drift(segments)
        drift = list(result.values())[0]
        assert drift is not None
        # Le ratio HR/pace en 2eme moitie augmente moins car pace baisse
        # Compare au cas constant-pace, le drift est plus faible

    def test_exactly_4_segments_minimum(self):
        """Exactement 4 segments valides -> drift calcule (seuil minimum)."""
        segments = [
            _make_segment(0, avg_hr=140.0, pace_min_per_km=5.0),
            _make_segment(1, avg_hr=145.0, pace_min_per_km=5.0),
            _make_segment(2, avg_hr=155.0, pace_min_per_km=5.0),
            _make_segment(3, avg_hr=160.0, pace_min_per_km=5.0),
        ]
        result = _compute_cardiac_drift(segments)
        drift = list(result.values())[0]
        assert drift is not None
        # 1ere moitie (2 segs) : HR moyen = (140+145)/2 = 142.5
        # 2eme moitie (2 segs) : HR moyen = (155+160)/2 = 157.5
        expected = (157.5 / 142.5) - 1.0
        assert drift == pytest.approx(expected, abs=0.001)

    def test_3_valid_among_mixed_returns_none(self):
        """4 segments dont 1 sans HR -> seulement 3 valides -> None."""
        segments = [
            _make_segment(0, avg_hr=140.0, pace_min_per_km=5.0),
            _make_segment(1, avg_hr=None, pace_min_per_km=5.0),
            _make_segment(2, avg_hr=155.0, pace_min_per_km=5.0),
            _make_segment(3, avg_hr=160.0, pace_min_per_km=5.0),
        ]
        result = _compute_cardiac_drift(segments)
        for v in result.values():
            assert v is None

    def test_drift_magnitude_proportional_to_hr_rise(self):
        """Plus la hausse HR est forte, plus le drift est eleve (a pace constante)."""
        pace = 5.0
        drifts = []
        for hr_delta in [5, 10, 20]:
            segments = [
                _make_segment(i, avg_hr=150 + (i * hr_delta / 9), pace_min_per_km=pace)
                for i in range(10)
            ]
            result = _compute_cardiac_drift(segments)
            d = list(result.values())[0]
            drifts.append(d)

        assert drifts[0] < drifts[1] < drifts[2]

    def test_20_segments_realistic_marathon(self):
        """Simulation marathon (20 segs de ~2km) : HR monte de 145 a 175, pace constant.

        A pace constant, seule la hausse HR determine le drift.
        """
        segments = [
            _make_segment(i, avg_hr=145 + i * 1.5, pace_min_per_km=5.0)
            for i in range(20)
        ]
        result = _compute_cardiac_drift(segments)
        drift = list(result.values())[0]
        assert drift is not None
        assert drift > 0
        # 1ere moitie (10 segs) : HR moyen = 145 + avg(0..9)*1.5 = 145+6.75 = 151.75
        # 2eme moitie (10 segs) : HR moyen = 145 + avg(10..19)*1.5 = 145+21.75 = 166.75
        # drift = 166.75/151.75 - 1 ≈ 0.099 (~10%)
        assert drift > 0.05


# ===================================================================
# Tests Cadence Decay
# ===================================================================

class TestCadenceDecay:
    def test_no_decay(self):
        """Cadence constante -> decay ~0."""
        segments = [_make_segment(i, avg_cadence=85.0) for i in range(10)]
        result = _compute_cadence_decay(segments)
        for v in result.values():
            assert v == pytest.approx(0.0, abs=0.01)

    def test_negative_decay(self):
        """Cadence qui diminue -> decay negatif."""
        segments = []
        for i in range(10):
            cad = 90 - i * 2  # 90 -> 72
            segments.append(_make_segment(i, avg_cadence=cad))
        result = _compute_cadence_decay(segments)
        decay_val = list(result.values())[0]
        assert decay_val is not None
        assert decay_val < 0

    def test_insufficient_segments(self):
        """Moins de 4 segments avec cadence -> None."""
        segments = [_make_segment(0, avg_cadence=85.0)]
        result = _compute_cadence_decay(segments)
        for v in result.values():
            assert v is None


# ===================================================================
# Tests Efficiency Factor
# ===================================================================

class TestEfficiencyFactor:
    def test_basic(self):
        """pace 5 min/km, HR 150 -> EF = 5/150."""
        segments = [_make_segment(0, avg_hr=150.0, pace_min_per_km=5.0)]
        result = _compute_efficiency_factor(segments)
        assert list(result.values())[0] == pytest.approx(5.0 / 150.0, abs=0.001)

    def test_no_hr(self):
        """Pas de HR -> None."""
        segments = [_make_segment(0, avg_hr=None, pace_min_per_km=5.0)]
        result = _compute_efficiency_factor(segments)
        assert list(result.values())[0] is None

    def test_no_pace(self):
        """Pas de pace -> None."""
        segments = [_make_segment(0, avg_hr=150.0, pace_min_per_km=None)]
        result = _compute_efficiency_factor(segments)
        assert list(result.values())[0] is None

    def test_lower_ef_means_better(self):
        """EF plus bas = meilleure efficacite."""
        seg_fast = _make_segment(0, avg_hr=150.0, pace_min_per_km=4.0)
        seg_slow = _make_segment(1, avg_hr=150.0, pace_min_per_km=6.0)
        res_fast = _compute_efficiency_factor([seg_fast])
        res_slow = _compute_efficiency_factor([seg_slow])
        assert list(res_fast.values())[0] < list(res_slow.values())[0]


# ===================================================================
# Tests TRIMP (4.5.2)
# ===================================================================

class TestTrimp:
    def test_basic_trimp(self):
        """TRIMP simplifie = duration * avg_hr."""
        trimp = compute_trimp(avg_hr=150.0, duration_min=60.0)
        assert trimp == 150.0 * 60.0

    def test_trimp_with_max_hr(self):
        """TRIMP normalise = duration * (avg_hr / max_hr) * 100."""
        trimp = compute_trimp(avg_hr=150.0, duration_min=60.0, max_hr=200.0)
        assert trimp == pytest.approx(60.0 * (150.0 / 200.0) * 100.0)

    def test_trimp_no_hr(self):
        """Pas de HR -> None."""
        assert compute_trimp(avg_hr=None, duration_min=60.0) is None

    def test_trimp_zero_hr(self):
        """HR = 0 -> None."""
        assert compute_trimp(avg_hr=0.0, duration_min=60.0) is None

    def test_trimp_known_activity(self):
        """1h a HR moyen 160, max HR 190 -> TRIMP ~5052.6."""
        trimp = compute_trimp(avg_hr=160.0, duration_min=60.0, max_hr=190.0)
        expected = 60.0 * (160.0 / 190.0) * 100.0
        assert trimp == pytest.approx(expected, rel=0.01)

    # --- Tests 4.5.2 : TRIMP avec activites connues ---

    def test_trimp_easy_run_45min(self):
        """Easy run : 45min, avg HR 135, max HR 190 -> TRIMP normalise ~3197."""
        trimp = compute_trimp(avg_hr=135.0, duration_min=45.0, max_hr=190.0)
        expected = 45.0 * (135.0 / 190.0) * 100.0  # 3197.37
        assert trimp == pytest.approx(expected, abs=0.1)

    def test_trimp_tempo_run_30min(self):
        """Tempo run : 30min, avg HR 170, max HR 195 -> TRIMP normalise ~2615."""
        trimp = compute_trimp(avg_hr=170.0, duration_min=30.0, max_hr=195.0)
        expected = 30.0 * (170.0 / 195.0) * 100.0  # 2615.38
        assert trimp == pytest.approx(expected, abs=0.1)

    def test_trimp_long_run_90min(self):
        """Long run : 90min, avg HR 145, max HR 185 -> TRIMP normalise ~7054."""
        trimp = compute_trimp(avg_hr=145.0, duration_min=90.0, max_hr=185.0)
        expected = 90.0 * (145.0 / 185.0) * 100.0  # 7054.05
        assert trimp == pytest.approx(expected, abs=0.1)

    def test_trimp_interval_session_40min(self):
        """Interval : 40min, avg HR 175, max HR 200 -> TRIMP normalise ~3500."""
        trimp = compute_trimp(avg_hr=175.0, duration_min=40.0, max_hr=200.0)
        expected = 40.0 * (175.0 / 200.0) * 100.0  # 3500.0
        assert trimp == pytest.approx(expected, abs=0.1)

    def test_trimp_ordering_by_intensity(self):
        """TRIMP normalise reflete l'intensite : interval > tempo > easy (a duree egale)."""
        duration = 60.0
        max_hr = 195.0
        easy = compute_trimp(avg_hr=130.0, duration_min=duration, max_hr=max_hr)
        tempo = compute_trimp(avg_hr=165.0, duration_min=duration, max_hr=max_hr)
        interval = compute_trimp(avg_hr=180.0, duration_min=duration, max_hr=max_hr)
        assert easy < tempo < interval

    def test_trimp_simple_proportional_to_duration(self):
        """TRIMP simplifie (sans max_hr) est proportionnel a la duree."""
        trimp_30 = compute_trimp(avg_hr=150.0, duration_min=30.0)
        trimp_60 = compute_trimp(avg_hr=150.0, duration_min=60.0)
        assert trimp_60 == pytest.approx(trimp_30 * 2.0, rel=1e-9)

    def test_trimp_simple_proportional_to_hr(self):
        """TRIMP simplifie est proportionnel a avg_hr."""
        trimp_low = compute_trimp(avg_hr=120.0, duration_min=60.0)
        trimp_high = compute_trimp(avg_hr=180.0, duration_min=60.0)
        assert trimp_high / trimp_low == pytest.approx(180.0 / 120.0, rel=1e-9)

    def test_trimp_negative_hr_returns_none(self):
        """HR negatif -> None."""
        assert compute_trimp(avg_hr=-10.0, duration_min=60.0) is None

    def test_trimp_zero_duration(self):
        """Duree 0 -> TRIMP = 0 (pas d'effort)."""
        trimp = compute_trimp(avg_hr=150.0, duration_min=0.0)
        assert trimp == pytest.approx(0.0, abs=1e-9)

    def test_trimp_max_hr_zero_returns_none_or_simple(self):
        """max_hr = 0 -> fallback sur TRIMP simplifie (car max_hr <= 0)."""
        trimp = compute_trimp(avg_hr=150.0, duration_min=60.0, max_hr=0.0)
        # max_hr=0 fait que la condition max_hr and max_hr > 0 est False
        # -> fallback sur duration * avg_hr
        assert trimp == pytest.approx(60.0 * 150.0, abs=0.1)


class TestGetDailyTrimp:
    """Tests pour _get_daily_trimp avec mock activites (4.5.2)."""

    def _make_activity(self, moving_time: int, average_heartrate, max_heartrate=None):
        """Helper : cree un mock Activity."""
        act = MagicMock()
        act.moving_time = moving_time
        act.average_heartrate = average_heartrate
        act.max_heartrate = max_heartrate
        return act

    def test_single_activity(self):
        """Une seule activite dans la journee."""
        session = MagicMock()
        act = self._make_activity(3600, 150.0, 185.0)  # 60min, HR 150, max 185
        session.exec.return_value.all.return_value = [act]

        trimp = _get_daily_trimp(session, uuid4(), date(2026, 2, 7))
        expected = 60.0 * (150.0 / 185.0) * 100.0
        assert trimp == pytest.approx(expected, abs=0.1)

    def test_two_activities_same_day(self):
        """Deux activites dans la meme journee -> somme des TRIMPs."""
        session = MagicMock()
        act1 = self._make_activity(2700, 140.0, 180.0)  # 45min easy
        act2 = self._make_activity(1800, 170.0, 195.0)  # 30min tempo
        session.exec.return_value.all.return_value = [act1, act2]

        trimp = _get_daily_trimp(session, uuid4(), date(2026, 2, 7))
        expected1 = 45.0 * (140.0 / 180.0) * 100.0
        expected2 = 30.0 * (170.0 / 195.0) * 100.0
        assert trimp == pytest.approx(expected1 + expected2, abs=0.1)

    def test_no_activities(self):
        """Pas d'activite -> TRIMP = 0."""
        session = MagicMock()
        session.exec.return_value.all.return_value = []

        trimp = _get_daily_trimp(session, uuid4(), date(2026, 2, 7))
        assert trimp == 0.0

    def test_activity_without_hr(self):
        """Activite sans HR -> TRIMP None, donc non comptee (total reste 0)."""
        session = MagicMock()
        act = self._make_activity(3600, None, None)
        session.exec.return_value.all.return_value = [act]

        trimp = _get_daily_trimp(session, uuid4(), date(2026, 2, 7))
        assert trimp == 0.0

    def test_mixed_activities_hr_and_no_hr(self):
        """Une activite avec HR + une sans -> seule celle avec HR est comptee."""
        session = MagicMock()
        act_with_hr = self._make_activity(3600, 155.0, 190.0)  # 60min
        act_no_hr = self._make_activity(1800, None, None)  # 30min sans HR
        session.exec.return_value.all.return_value = [act_with_hr, act_no_hr]

        trimp = _get_daily_trimp(session, uuid4(), date(2026, 2, 7))
        expected = 60.0 * (155.0 / 190.0) * 100.0
        assert trimp == pytest.approx(expected, abs=0.1)

    def test_activity_without_max_hr_uses_simple_trimp(self):
        """Activite avec avg_hr mais sans max_hr -> TRIMP simplifie."""
        session = MagicMock()
        act = self._make_activity(3600, 150.0, None)  # 60min, no max HR
        session.exec.return_value.all.return_value = [act]

        trimp = _get_daily_trimp(session, uuid4(), date(2026, 2, 7))
        expected = 60.0 * 150.0  # TRIMP simplifie
        assert trimp == pytest.approx(expected, abs=0.1)


# ===================================================================
# Tests CTL/ATL/TSB convergence (4.5.3)
# ===================================================================

class TestCtlAtlConvergence:
    def test_ctl_convergence_60_days(self):
        """CTL converge vers TRIMP quotidien constant apres ~60 jours."""
        # Simuler EWMA manuellement
        daily_trimp = 100.0
        ctl = 0.0
        for _ in range(60):
            ctl = ctl * (1 - 1 / 42) + daily_trimp * (1 / 42)
        # Apres 60 jours, CTL devrait etre proche de daily_trimp (>75%)
        assert ctl > daily_trimp * 0.75
        assert ctl < daily_trimp  # Pas encore 100%

    def test_atl_converges_faster(self):
        """ATL (7j) converge plus vite que CTL (42j)."""
        daily_trimp = 100.0
        ctl = 0.0
        atl = 0.0
        for _ in range(14):
            ctl = ctl * (1 - 1 / 42) + daily_trimp * (1 / 42)
            atl = atl * (1 - 1 / 7) + daily_trimp * (1 / 7)
        assert atl > ctl  # ATL converge plus vite

    def test_tsb_positive_after_rest(self):
        """Apres une periode d'entrainement puis repos, TSB devient positif."""
        daily_trimp = 200.0
        ctl = 0.0
        atl = 0.0
        # 30 jours d'entrainement
        for _ in range(30):
            ctl = ctl * (1 - 1 / 42) + daily_trimp * (1 / 42)
            atl = atl * (1 - 1 / 7) + daily_trimp * (1 / 7)
        # 14 jours de repos
        for _ in range(14):
            ctl = ctl * (1 - 1 / 42)
            atl = atl * (1 - 1 / 7)
        tsb = ctl - atl
        assert tsb > 0  # Frais apres repos

    def test_tsb_negative_during_heavy_training(self):
        """Pendant un entrainement intense, TSB est negatif (fatigue)."""
        ctl = 50.0  # Fitness de base
        atl = 50.0
        heavy_trimp = 300.0
        # 5 jours intensifs
        for _ in range(5):
            ctl = ctl * (1 - 1 / 42) + heavy_trimp * (1 / 42)
            atl = atl * (1 - 1 / 7) + heavy_trimp * (1 / 7)
        tsb = ctl - atl
        assert tsb < 0  # Fatigue

    def test_ewma_zero_trimp_decays(self):
        """Sans entrainement, CTL et ATL decroissent vers 0."""
        ctl = 100.0
        atl = 100.0
        for _ in range(100):
            ctl = ctl * (1 - 1 / 42)
            atl = atl * (1 - 1 / 7)
        assert ctl < 10  # Decroit fortement
        assert atl < 0.01  # ATL decroit plus vite


# ===================================================================
# Tests compute_training_load sur 60 jours (4.5.3)
# ===================================================================

class TestComputeTrainingLoad60Days:
    """Teste compute_training_load de bout en bout sur 60 jours de donnees mockees."""

    def _run_compute(self, daily_trimps: dict, date_from: date, date_to: date):
        """Helper : execute compute_training_load avec des TRIMPs mockes par jour.

        daily_trimps : {date: trimp_value} pour chaque jour avec activite.
        Retourne (days_computed, stored_records) ou stored_records est une liste
        des TrainingLoad ajoutes a la session.
        """
        user_id = uuid4()
        stored = []

        def fake_get_daily_trimp(session, uid, target_date):
            return daily_trimps.get(target_date, 0.0)

        def fake_get_rhr_delta(session, uid, target_date):
            return None

        # Mock session : pas de TrainingLoad precedent, pas d'existant, capture les add()
        session = MagicMock()
        session.exec.return_value.first.return_value = None  # pas de prev_load ni existing
        session.add.side_effect = lambda obj: stored.append(obj)

        with patch(
            "app.domain.services.derived_features_service._get_daily_trimp",
            side_effect=fake_get_daily_trimp,
        ), patch(
            "app.domain.services.derived_features_service._get_rhr_delta_7d",
            side_effect=fake_get_rhr_delta,
        ):
            days = compute_training_load(session, user_id, date_from, date_to)

        return days, stored

    def test_constant_trimp_60_days_ctl_convergence(self):
        """TRIMP constant 100/jour pendant 60 jours : CTL converge vers ~76."""
        date_from = date(2026, 1, 1)
        date_to = date(2026, 3, 1)  # 60 jours
        daily_trimps = {
            date_from + timedelta(days=i): 100.0 for i in range(60)
        }

        days, stored = self._run_compute(daily_trimps, date_from, date_to)
        assert days == 60

        last = stored[-1]
        # CTL apres 60j de TRIMP=100 : EWMA 42j partant de 0
        ctl_expected = 0.0
        for _ in range(60):
            ctl_expected = ctl_expected * (1 - 1 / 42) + 100.0 * (1 / 42)
        assert last.ctl_42d == pytest.approx(ctl_expected, abs=0.01)
        assert last.ctl_42d > 75.0  # >75% de convergence

    def test_constant_trimp_60_days_atl_near_target(self):
        """TRIMP constant 100/jour pendant 60 jours : ATL quasi-converge (~100)."""
        date_from = date(2026, 1, 1)
        date_to = date(2026, 3, 1)
        daily_trimps = {
            date_from + timedelta(days=i): 100.0 for i in range(60)
        }

        _, stored = self._run_compute(daily_trimps, date_from, date_to)
        last = stored[-1]
        # ATL 7j converge tres vite vers 100
        assert last.atl_7d > 98.0
        assert last.atl_7d < 101.0

    def test_atl_converges_faster_than_ctl(self):
        """Apres 14 jours de TRIMP constant, ATL est plus proche de la cible que CTL."""
        date_from = date(2026, 1, 1)
        date_to = date(2026, 1, 14)  # 14 jours
        daily_trimps = {
            date_from + timedelta(days=i): 100.0 for i in range(14)
        }

        _, stored = self._run_compute(daily_trimps, date_from, date_to)
        last = stored[-1]
        assert last.atl_7d > last.ctl_42d

    def test_training_then_rest_tsb_positive(self):
        """30 jours d'entrainement + 30 jours repos : TSB finit positif."""
        date_from = date(2026, 1, 1)
        date_to = date(2026, 3, 1)  # 60 jours
        daily_trimps = {}
        for i in range(30):
            daily_trimps[date_from + timedelta(days=i)] = 200.0
        # Jours 30-59 : pas de TRIMP (repos) -> default 0.0

        _, stored = self._run_compute(daily_trimps, date_from, date_to)
        last = stored[-1]
        assert last.tsb > 0  # Frais apres 30j repos

    def test_heavy_block_tsb_negative(self):
        """Bloc intensif sur 7 jours partant d'un etat equilibre : TSB negatif."""
        date_from = date(2026, 1, 1)
        date_to = date(2026, 1, 7)  # 7 jours
        daily_trimps = {
            date_from + timedelta(days=i): 300.0 for i in range(7)
        }

        _, stored = self._run_compute(daily_trimps, date_from, date_to)
        last = stored[-1]
        # Partant de CTL=0, ATL=0, un gros bloc fait monter ATL >> CTL -> TSB < 0
        assert last.tsb < 0

    def test_60_days_values_stored_correctly(self):
        """Verifie que 60 TrainingLoad sont crees avec TSB = CTL - ATL."""
        date_from = date(2026, 1, 1)
        date_to = date(2026, 3, 1)
        daily_trimps = {
            date_from + timedelta(days=i): 80.0 for i in range(60)
        }

        days, stored = self._run_compute(daily_trimps, date_from, date_to)
        assert days == 60
        assert len(stored) == 60

        for tl in stored:
            # Tolerance 0.02 car CTL, ATL et TSB sont arrondis individuellement a 2 decimales
            assert tl.tsb == pytest.approx(tl.ctl_42d - tl.atl_7d, abs=0.02)

    def test_variable_trimp_monotonic_ctl(self):
        """TRIMP croissant sur 60 jours : CTL augmente de facon monotone."""
        date_from = date(2026, 1, 1)
        date_to = date(2026, 3, 1)
        daily_trimps = {
            date_from + timedelta(days=i): 50.0 + i * 2.0 for i in range(60)
        }

        _, stored = self._run_compute(daily_trimps, date_from, date_to)
        ctl_values = [tl.ctl_42d for tl in stored]
        # CTL doit etre strictement croissant (TRIMP toujours > CTL courant)
        for i in range(1, len(ctl_values)):
            assert ctl_values[i] > ctl_values[i - 1]

    def test_zero_trimp_all_60_days(self):
        """60 jours sans activite : CTL, ATL, TSB restent a 0."""
        date_from = date(2026, 1, 1)
        date_to = date(2026, 3, 1)

        _, stored = self._run_compute({}, date_from, date_to)
        for tl in stored:
            assert tl.ctl_42d == 0.0
            assert tl.atl_7d == 0.0
            assert tl.tsb == 0.0


# ===================================================================
# Tests RHR Delta
# ===================================================================

class TestRhrDelta:
    def test_rhr_delta_with_data(self):
        """RHR delta = today.rhr - past.rhr."""
        session = MagicMock()
        today_data = MagicMock()
        today_data.resting_hr = 55
        past_data = MagicMock()
        past_data.resting_hr = 50

        session.exec.return_value.first.side_effect = [today_data, past_data]

        delta = _get_rhr_delta_7d(session, uuid4(), date(2026, 2, 7))
        assert delta == 5.0

    def test_rhr_delta_no_garmin(self):
        """Pas de donnees Garmin -> None."""
        session = MagicMock()
        session.exec.return_value.first.return_value = None

        delta = _get_rhr_delta_7d(session, uuid4(), date(2026, 2, 7))
        assert delta is None

    def test_rhr_delta_partial_data(self):
        """Donnee today mais pas past -> None."""
        session = MagicMock()
        today_data = MagicMock()
        today_data.resting_hr = 55

        session.exec.return_value.first.side_effect = [today_data, None]

        delta = _get_rhr_delta_7d(session, uuid4(), date(2026, 2, 7))
        assert delta is None


# ===================================================================
# Tests compute_segment_features (integration)
# ===================================================================

class TestComputeSegmentFeatures:
    def test_updates_minetti_for_segments(self):
        """compute_segment_features met a jour minetti_cost sur SegmentFeatures."""
        activity_id = uuid4()
        seg = _make_segment(0, avg_grade_percent=0.0, avg_hr=150.0, pace_min_per_km=5.0, avg_cadence=85.0)
        seg.activity_id = activity_id

        features = MagicMock()
        features.minetti_cost = None

        session = MagicMock()
        # exec pour select segments
        # exec pour select features
        call_count = [0]

        def mock_exec(query):
            result = MagicMock()
            if call_count[0] == 0:
                result.all.return_value = [seg]
                call_count[0] += 1
            else:
                result.first.return_value = features
            return result

        session.exec = mock_exec

        count = compute_segment_features(session, activity_id)
        assert count == 1
        assert features.minetti_cost == pytest.approx(3.6, abs=0.01)

    def test_no_segments_returns_zero(self):
        """Pas de segments -> retourne 0."""
        session = MagicMock()
        session.exec.return_value.all.return_value = []
        assert compute_segment_features(session, uuid4()) == 0
