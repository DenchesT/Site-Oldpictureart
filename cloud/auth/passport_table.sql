-- In the SAME YDB database as the existing 'likes' table.
-- Run exactly once in YDB Query Editor before deploying the updated function.
-- Does not change or delete existing data.
CREATE TABLE passport (
    user_id Utf8,
    entry_key Utf8,
    payload Utf8,
    updated_at Timestamp,
    PRIMARY KEY (user_id, entry_key)
);
