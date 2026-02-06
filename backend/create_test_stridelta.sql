-- ========================================
-- CRÉATION DE LA BASE stridelta.db (TEST)
-- ========================================

-- Table activity simplifiée pour test
CREATE TABLE activity (
    activity_id BIGINT PRIMARY KEY,
    strava_id BIGINT,
    name VARCHAR(255),
    distance DOUBLE PRECISION,
    start_date TIMESTAMP,
    sport_type VARCHAR(50)
);

-- Insertion de quelques activités de test (tirées du CSV)
INSERT INTO activity (activity_id, strava_id, name, distance, start_date, sport_type) VALUES
(1, 15158283669, 'Night Run', 6303.2, '2025-07-18T19:00:03Z', 'Run'),
(2, 15136992633, 'Petit échauffement d''avant Padel', 20316.1, '2025-07-16T16:21:16Z', 'TrailRun'),
(3, 15082787911, 'Evening Run', 10245.2, '2025-07-11T18:51:06Z', 'Run'),
(4, 15018565019, 'Trail mini Tordus', 12612.8, '2025-07-05T16:00:51Z', 'TrailRun'); 