-- Week availability read
-- Parameters:
--   :instructor_id (uuid)
--   :week_start (date)
--   :week_end (date)
SELECT specific_date,
       start_time,
       end_time,
       updated_at,
       created_at
FROM availability_slots
WHERE instructor_id = :instructor_id
  AND specific_date BETWEEN :week_start AND :week_end
ORDER BY specific_date, start_time;

-- Week save delete phase
-- Parameters:
--   :instructor_id (uuid)
--   :dates (date[])
DELETE FROM availability_slots
WHERE instructor_id = :instructor_id
  AND specific_date = ANY(:dates);

-- Week save insert phase (representative bulk insert)
-- Parameters:
--   :instructor_id (uuid)
--   :specific_date (date)
--   :start_time (time)
--   :end_time (time)
INSERT INTO availability_slots (
    instructor_id,
    specific_date,
    start_time,
    end_time
) VALUES (
    :instructor_id,
    :specific_date,
    :start_time,
    :end_time
);
