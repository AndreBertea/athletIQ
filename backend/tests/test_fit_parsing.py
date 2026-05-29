"""
Tests pour le parsing de fichiers FIT — Tache 5.2.1
Teste parse_fit_file() et download_fit_file() dans garmin_sync_service.py
avec des mocks fitparse simulant des fichiers FIT de course.
"""
import sys
import pytest
from unittest.mock import MagicMock, patch

# Injecter un mock fitparse dans sys.modules AVANT l'import du service,
# car parse_fit_file fait `import fitparse` localement.
_mock_fitparse_module = MagicMock()
sys.modules.setdefault("fitparse", _mock_fitparse_module)

from app.domain.services.garmin_sync_service import parse_fit_file, download_fit_file


# ============================================================
# Helpers : mock fitparse messages
# ============================================================

def _make_record(stance_time=None, vertical_oscillation=None,
                 stance_time_balance=None, power=None):
    """Cree un mock fitparse record message."""
    values = {
        "stance_time": stance_time,
        "vertical_oscillation": vertical_oscillation,
        "stance_time_balance": stance_time_balance,
        "power": power,
    }
    record = MagicMock()
    record.get_value = lambda field: values.get(field)
    return record


def _make_session(aerobic=None, anaerobic=None):
    """Cree un mock fitparse session message."""
    values = {
        "total_training_effect": aerobic,
        "total_anaerobic_training_effect": anaerobic,
    }
    session = MagicMock()
    session.get_value = lambda field: values.get(field)
    return session


def _build_mock_fitfile(records=None, sessions=None):
    """Cree un mock FitFile instance avec les messages donnes."""
    records = records or []
    sessions = sessions or []

    def get_messages(msg_type):
        if msg_type == "record":
            return records
        elif msg_type == "session":
            return sessions
        return []

    fitfile = MagicMock()
    fitfile.get_messages = get_messages
    return fitfile


# ============================================================
# Tests : parse_fit_file — Running Dynamics complet
# ============================================================

class TestParseFitFileComplete:
    """Teste parse_fit_file avec un fichier FIT complet (Running Dynamics + power + TE)."""

    @patch("fitparse.FitFile")
    def test_full_running_dynamics(self, mock_fit_cls):
        """FIT file avec tous les champs Running Dynamics, power et Training Effect."""
        records = [
            _make_record(stance_time=245.0, vertical_oscillation=8.5,
                         stance_time_balance=50.2, power=230),
            _make_record(stance_time=250.0, vertical_oscillation=9.0,
                         stance_time_balance=49.8, power=235),
            _make_record(stance_time=248.0, vertical_oscillation=8.8,
                         stance_time_balance=50.0, power=228),
        ]
        sessions = [_make_session(aerobic=3.5, anaerobic=1.2)]

        mock_fit_cls.return_value = _build_mock_fitfile(records, sessions)

        result = parse_fit_file(b"fake_fit_data")

        assert result["ground_contact_time_avg"] == pytest.approx(247.7, abs=0.1)
        assert result["vertical_oscillation_avg"] == pytest.approx(8.77, abs=0.01)
        assert result["stance_time_balance_avg"] == pytest.approx(50.0, abs=0.01)
        assert result["power_avg"] == pytest.approx(231.0, abs=0.1)
        assert result["aerobic_training_effect"] == 3.5
        assert result["anaerobic_training_effect"] == 1.2
        assert result["record_count"] == 6  # 3 stance_times + 3 powers


# ============================================================
# Tests : parse_fit_file — Donnees partielles
# ============================================================

class TestParseFitFilePartial:
    """Teste parse_fit_file quand certains champs sont absents."""

    @patch("fitparse.FitFile")
    def test_only_power_no_running_dynamics(self, mock_fit_cls):
        """FIT d'un velo/treadmill : power present mais pas de Running Dynamics."""
        records = [
            _make_record(power=200),
            _make_record(power=210),
            _make_record(power=205),
        ]
        sessions = [_make_session(aerobic=2.8)]

        mock_fit_cls.return_value = _build_mock_fitfile(records, sessions)

        result = parse_fit_file(b"fake_fit_data")

        assert result["power_avg"] == pytest.approx(205.0, abs=0.1)
        assert result["aerobic_training_effect"] == 2.8
        assert "ground_contact_time_avg" not in result
        assert "vertical_oscillation_avg" not in result
        assert "stance_time_balance_avg" not in result
        assert "anaerobic_training_effect" not in result
        assert result["record_count"] == 3

    @patch("fitparse.FitFile")
    def test_only_running_dynamics_no_power(self, mock_fit_cls):
        """FIT sans capteur de puissance : Running Dynamics present, power absent."""
        records = [
            _make_record(stance_time=240.0, vertical_oscillation=9.2,
                         stance_time_balance=51.0),
            _make_record(stance_time=242.0, vertical_oscillation=9.0,
                         stance_time_balance=50.5),
        ]
        sessions = [_make_session(aerobic=4.0, anaerobic=2.5)]

        mock_fit_cls.return_value = _build_mock_fitfile(records, sessions)

        result = parse_fit_file(b"fake_fit_data")

        assert result["ground_contact_time_avg"] == pytest.approx(241.0, abs=0.1)
        assert result["vertical_oscillation_avg"] == pytest.approx(9.1, abs=0.01)
        assert result["stance_time_balance_avg"] == pytest.approx(50.75, abs=0.01)
        assert "power_avg" not in result
        assert result["aerobic_training_effect"] == 4.0
        assert result["anaerobic_training_effect"] == 2.5
        assert result["record_count"] == 2  # 2 stance_times + 0 powers

    @patch("fitparse.FitFile")
    def test_mixed_records_some_fields_missing(self, mock_fit_cls):
        """Certains records ont stance_time, d'autres non (donnees intermittentes)."""
        records = [
            _make_record(stance_time=245.0, power=220),
            _make_record(stance_time=None, power=225),   # pas de stance_time
            _make_record(stance_time=250.0, power=None),  # pas de power
        ]
        sessions = []

        mock_fit_cls.return_value = _build_mock_fitfile(records, sessions)

        result = parse_fit_file(b"fake_fit_data")

        # Moyennes sur les valeurs non-None seulement
        assert result["ground_contact_time_avg"] == pytest.approx(247.5, abs=0.1)
        assert result["power_avg"] == pytest.approx(222.5, abs=0.1)
        assert result["record_count"] == 4  # 2 stance + 2 powers


# ============================================================
# Tests : parse_fit_file — Fichier vide / minimal
# ============================================================

class TestParseFitFileEmpty:
    """Teste parse_fit_file avec un fichier FIT sans donnees utiles."""

    @patch("fitparse.FitFile")
    def test_no_records_no_session(self, mock_fit_cls):
        """FIT file vide : aucun record, aucune session."""
        mock_fit_cls.return_value = _build_mock_fitfile([], [])

        result = parse_fit_file(b"fake_fit_data")

        assert result["record_count"] == 0
        assert "ground_contact_time_avg" not in result
        assert "vertical_oscillation_avg" not in result
        assert "stance_time_balance_avg" not in result
        assert "power_avg" not in result
        assert "aerobic_training_effect" not in result
        assert "anaerobic_training_effect" not in result

    @patch("fitparse.FitFile")
    def test_records_all_none_values(self, mock_fit_cls):
        """Records existent mais tous les champs sont None."""
        records = [
            _make_record(),  # tout None
            _make_record(),
        ]
        mock_fit_cls.return_value = _build_mock_fitfile(records, [])

        result = parse_fit_file(b"fake_fit_data")

        assert result["record_count"] == 0
        assert "ground_contact_time_avg" not in result
        assert "power_avg" not in result


# ============================================================
# Tests : parse_fit_file — Session / Training Effect
# ============================================================

class TestParseFitFileSession:
    """Teste l'extraction des Training Effect depuis le message session."""

    @patch("fitparse.FitFile")
    def test_session_only_aerobic(self, mock_fit_cls):
        """Session avec seulement aerobic TE (ancien firmware)."""
        sessions = [_make_session(aerobic=3.0, anaerobic=None)]
        mock_fit_cls.return_value = _build_mock_fitfile([], sessions)

        result = parse_fit_file(b"fake_fit_data")

        assert result["aerobic_training_effect"] == 3.0
        assert "anaerobic_training_effect" not in result

    @patch("fitparse.FitFile")
    def test_session_no_training_effect(self, mock_fit_cls):
        """Session sans Training Effect (activite manuelle/importee)."""
        sessions = [_make_session()]
        mock_fit_cls.return_value = _build_mock_fitfile([], sessions)

        result = parse_fit_file(b"fake_fit_data")

        assert "aerobic_training_effect" not in result
        assert "anaerobic_training_effect" not in result

    @patch("fitparse.FitFile")
    def test_multiple_sessions_uses_first(self, mock_fit_cls):
        """Multisport : plusieurs sessions, on prend la premiere."""
        sessions = [
            _make_session(aerobic=4.0, anaerobic=2.0),
            _make_session(aerobic=2.5, anaerobic=0.5),
        ]
        mock_fit_cls.return_value = _build_mock_fitfile([], sessions)

        result = parse_fit_file(b"fake_fit_data")

        assert result["aerobic_training_effect"] == 4.0
        assert result["anaerobic_training_effect"] == 2.0


# ============================================================
# Tests : parse_fit_file — Precision arrondi
# ============================================================

class TestParseFitFileRounding:
    """Teste que les moyennes sont correctement arrondies."""

    @patch("fitparse.FitFile")
    def test_rounding_precision(self, mock_fit_cls):
        """Verifie les arrondis : GCT a 1 dec, VO a 2 dec, power a 1 dec."""
        records = [
            _make_record(stance_time=245.333, vertical_oscillation=8.777,
                         stance_time_balance=50.126, power=228.666),
        ]
        sessions = [_make_session(aerobic=3.14159)]

        mock_fit_cls.return_value = _build_mock_fitfile(records, sessions)

        result = parse_fit_file(b"fake_fit_data")

        assert result["ground_contact_time_avg"] == 245.3
        assert result["vertical_oscillation_avg"] == 8.78
        assert result["stance_time_balance_avg"] == 50.13
        assert result["power_avg"] == 228.7
        assert result["aerobic_training_effect"] == 3.1


# ============================================================
# Tests : parse_fit_file — Simulation run longue (20 records)
# ============================================================

class TestParseFitFileLongRun:
    """Simule un fichier FIT de course longue avec de nombreux records."""

    @patch("fitparse.FitFile")
    def test_20_records_averages(self, mock_fit_cls):
        """20 records avec valeurs progressives (fatigue → GCT augmente)."""
        records = []
        for i in range(20):
            records.append(_make_record(
                stance_time=240.0 + i * 1.0,     # 240 → 259
                vertical_oscillation=8.0 + i * 0.1,  # 8.0 → 9.9
                stance_time_balance=50.0 + (i % 3) * 0.1,  # oscille
                power=230 - i * 0.5,              # 230 → 220.5
            ))
        sessions = [_make_session(aerobic=4.5, anaerobic=3.2)]

        mock_fit_cls.return_value = _build_mock_fitfile(records, sessions)

        result = parse_fit_file(b"fake_fit_data")

        # GCT moyen : (240+241+...+259) / 20 = 249.5
        assert result["ground_contact_time_avg"] == 249.5
        # Power moyen : (230 + 229.5 + ... + 220.5) / 20 = 225.25
        assert result["power_avg"] == 225.2  # arrondi a 1 dec
        assert result["record_count"] == 40  # 20 stance + 20 power
        assert result["aerobic_training_effect"] == 4.5
        assert result["anaerobic_training_effect"] == 3.2


# ============================================================
# Tests : download_fit_file
# ============================================================

class TestDownloadFitFile:
    """Teste le telechargement de fichiers FIT via garth client."""

    def test_download_success(self):
        """Download reussi retourne les bytes."""
        client = MagicMock()
        client.download.return_value = b"\x0e\x20\x01\x00"  # fake FIT header

        result = download_fit_file(client, 12345678)

        client.download.assert_called_once_with(
            "/download-service/files/activity/12345678"
        )
        assert result == b"\x0e\x20\x01\x00"

    def test_download_empty_returns_none(self):
        """Download qui retourne des bytes vides → None."""
        client = MagicMock()
        client.download.return_value = b""

        result = download_fit_file(client, 12345678)

        assert result is None

    def test_download_none_returns_none(self):
        """Download qui retourne None → None."""
        client = MagicMock()
        client.download.return_value = None

        result = download_fit_file(client, 12345678)

        assert result is None

    def test_download_exception_returns_none(self):
        """Exception lors du download → None (pas de crash)."""
        client = MagicMock()
        client.download.side_effect = Exception("HTTP 404")

        result = download_fit_file(client, 99999)

        assert result is None
