-- ========================================
-- CRÉATION DE LA BASE activity_detail.db
-- ========================================

-- 1. Table maîtresse : activities
CREATE TABLE activities (
    activity_id           BIGINT          PRIMARY KEY,          -- 15136992633
    fetched_at            TIMESTAMP       NOT NULL,
    athlete_id            BIGINT          NOT NULL,
    name                  VARCHAR(255)    NOT NULL,
    distance_m            DOUBLE PRECISION,
    moving_time_s         INT,
    elapsed_time_s        INT,
    elev_gain_m           DOUBLE PRECISION,
    sport_type            VARCHAR(50),                         -- « TrailRun »
    workout_type          SMALLINT,
    start_date_utc        TIMESTAMP,
    start_date_local      TIMESTAMP,
    timezone_label        VARCHAR(100),
    utc_offset_s          INT,
    visibility            VARCHAR(20),                         -- everyone / followers / only_me
    trainer               BOOLEAN,
    commute               BOOLEAN,
    manual                BOOLEAN,
    private               BOOLEAN,
    gear_id               VARCHAR(30),
    avg_speed_m_s         DOUBLE PRECISION,
    max_speed_m_s         DOUBLE PRECISION,
    avg_cadence_rpm       DOUBLE PRECISION,
    avg_watts             DOUBLE PRECISION,
    max_watts             DOUBLE PRECISION,
    weighted_avg_watts    DOUBLE PRECISION,
    kilojoules            DOUBLE PRECISION,
    has_heartrate         BOOLEAN,
    avg_heartrate_bpm     DOUBLE PRECISION,
    max_heartrate_bpm     DOUBLE PRECISION,
    calories_kcal         DOUBLE PRECISION,
    description           TEXT,
    start_lat             DOUBLE PRECISION,
    start_lng             DOUBLE PRECISION,
    end_lat               DOUBLE PRECISION,
    end_lng               DOUBLE PRECISION,
    map_polyline          TEXT,
    summary_polyline      TEXT
);

-- 2. Réutilisable : athletes
CREATE TABLE athletes (
    athlete_id   BIGINT PRIMARY KEY,
    resource_state SMALLINT
);

-- 3. Segments et efforts
CREATE TABLE segments (
    segment_id        BIGINT      PRIMARY KEY,
    name              VARCHAR(255),
    activity_type     VARCHAR(20),
    distance_m        DOUBLE PRECISION,
    avg_grade_pct     DOUBLE PRECISION,
    max_grade_pct     DOUBLE PRECISION,
    elev_high_m       DOUBLE PRECISION,
    elev_low_m        DOUBLE PRECISION,
    climb_category    SMALLINT,
    city              VARCHAR(100),
    state             VARCHAR(100),
    country           VARCHAR(100)
);

CREATE TABLE segment_efforts (
    effort_id         BIGINT PRIMARY KEY,
    activity_id       BIGINT      NOT NULL REFERENCES activities,
    athlete_id        BIGINT      NOT NULL REFERENCES athletes,
    segment_id        BIGINT      NOT NULL REFERENCES segments,
    name              VARCHAR(255),
    elapsed_time_s    INT,
    moving_time_s     INT,
    start_date_utc    TIMESTAMP,
    start_date_local  TIMESTAMP,
    distance_m        DOUBLE PRECISION,
    average_cadence   DOUBLE PRECISION,
    average_watts     DOUBLE PRECISION,
    average_hr_bpm    DOUBLE PRECISION,
    max_hr_bpm        DOUBLE PRECISION,
    pr_rank           SMALLINT
);

-- 4. Splits et laps
CREATE TABLE splits_metric (
    activity_id          BIGINT   NOT NULL REFERENCES activities,
    split_id             BIGINT,                             -- Colonne manquante
    split_km             SMALLINT NOT NULL,          -- 1, 2, 3…
    distance_m           DOUBLE PRECISION,
    elapsed_time_s       INT,
    moving_time_s        INT,
    elevation_difference_m DOUBLE PRECISION,                 -- Renommé pour correspondre au script
    elev_diff_m          DOUBLE PRECISION,
    avg_speed_m_s        DOUBLE PRECISION,
    average_speed_m_s    DOUBLE PRECISION,                   -- Colonne manquante
    avg_gas_m_s          DOUBLE PRECISION,           -- grade-adjusted speed
    avg_hr_bpm           DOUBLE PRECISION,
    pace_zone            SMALLINT,
    PRIMARY KEY (activity_id, split_km)
);

CREATE TABLE splits_standard (
    activity_id          BIGINT   NOT NULL REFERENCES activities,
    split_id             BIGINT,                             -- Colonne manquante
    split_mile           SMALLINT NOT NULL,
    distance_m           DOUBLE PRECISION,
    elapsed_time_s       INT,
    moving_time_s        INT,
    elevation_difference_m DOUBLE PRECISION,                 -- Renommé pour correspondre au script
    elev_diff_m          DOUBLE PRECISION,
    avg_speed_m_s        DOUBLE PRECISION,
    average_speed_m_s    DOUBLE PRECISION,                   -- Colonne manquante  
    avg_gas_m_s          DOUBLE PRECISION,
    avg_hr_bpm           DOUBLE PRECISION,
    pace_zone            SMALLINT,
    PRIMARY KEY (activity_id, split_mile)
);

CREATE TABLE laps (
    lap_id            BIGINT PRIMARY KEY,
    activity_id       BIGINT  NOT NULL REFERENCES activities,
    name              VARCHAR(255),                           -- Colonne manquante
    lap_index         SMALLINT,
    elapsed_time_s    INT,
    moving_time_s     INT,
    start_date_utc    TIMESTAMP,
    distance_m        DOUBLE PRECISION,
    start_index       INT,                                   -- Colonne manquante  
    end_index         INT,                                   -- Colonne manquante
    avg_speed_m_s     DOUBLE PRECISION,
    max_speed_m_s     DOUBLE PRECISION,
    elev_gain_m       DOUBLE PRECISION,
    total_elevation_gain DOUBLE PRECISION,                  -- Colonne manquante
    average_speed     DOUBLE PRECISION,                     -- Colonne manquante
    max_speed         DOUBLE PRECISION,                     -- Colonne manquante
    average_cadence   DOUBLE PRECISION,                     -- Colonne manquante
    average_watts     DOUBLE PRECISION,                     -- Colonne manquante
    max_watts         DOUBLE PRECISION,                     -- Colonne manquante
    avg_cadence_rpm   DOUBLE PRECISION,
    avg_watts         DOUBLE PRECISION,
    avg_hr_bpm        DOUBLE PRECISION,
    max_hr_bpm        DOUBLE PRECISION,
    pace_zone         SMALLINT
);

-- 5. Best efforts (records personnels)
CREATE TABLE best_efforts (
    effort_id        BIGINT PRIMARY KEY,
    activity_id      BIGINT NOT NULL REFERENCES activities,
    athlete_id       BIGINT NOT NULL REFERENCES athletes,
    name             VARCHAR(255),                           -- Colonne manquante  
    metric_name      VARCHAR(50),           -- « 400m », « 1 mile »…
    elapsed_time_s   INT,
    moving_time_s    INT,                                    -- Colonne manquante
    start_date       TIMESTAMP,                              -- Colonne manquante
    start_date_local TIMESTAMP,                              -- Colonne manquante
    distance_m       DOUBLE PRECISION,
    start_index      INT,
    end_index        INT,
    pr_rank          SMALLINT,
    achievements     INT                                      -- Colonne manquante
);

-- 6. Streams (optionnel)
CREATE TABLE activity_streams (
    activity_id   BIGINT REFERENCES activities,
    stream_type   VARCHAR(20),  -- latlng, altitude, heartrate…
    data          TEXT          -- JSON: liste de valeurs ou d'objets
);

-- ========================================
-- INDEXES SUGGÉRÉS
-- ========================================

-- Index sur athlete_id pour filtrer par utilisateur
CREATE INDEX idx_activities_athlete_id ON activities(athlete_id);

-- Index sur start_date_utc pour trier chronologiquement
CREATE INDEX idx_activities_start_date ON activities(start_date_utc);

-- Index sur les coordonnées pour requêtes géographiques
CREATE INDEX idx_activities_start_coords ON activities(start_lat, start_lng);

-- Index sur segment_efforts pour jointures
CREATE INDEX idx_segment_efforts_activity ON segment_efforts(activity_id);
CREATE INDEX idx_segment_efforts_segment ON segment_efforts(segment_id);

-- Index sur activity_streams
CREATE INDEX idx_activity_streams_activity ON activity_streams(activity_id);
CREATE INDEX idx_activity_streams_type ON activity_streams(stream_type); 