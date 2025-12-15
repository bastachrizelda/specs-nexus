-- Add evaluation_open field to events table
ALTER TABLE events 
ADD COLUMN IF NOT EXISTS evaluation_open BOOLEAN DEFAULT FALSE;

-- Update existing events to have default value
UPDATE events 
SET evaluation_open = FALSE 
WHERE evaluation_open IS NULL;
