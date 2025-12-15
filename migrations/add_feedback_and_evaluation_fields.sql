-- Migration: Add feedback_link and evaluation tracking fields
-- Date: 2025-12-15
-- Description: Adds feedback_link to events table and evaluation tracking to event_attendance table

-- Add feedback_link column to events table
ALTER TABLE events 
ADD COLUMN IF NOT EXISTS feedback_link VARCHAR(500);

-- Add evaluation tracking columns to event_attendance table
ALTER TABLE event_attendance 
ADD COLUMN IF NOT EXISTS evaluation_completed BOOLEAN DEFAULT FALSE;

ALTER TABLE event_attendance 
ADD COLUMN IF NOT EXISTS evaluation_completed_at TIMESTAMP WITH TIME ZONE;

-- Update existing records to have default values
UPDATE event_attendance 
SET evaluation_completed = FALSE 
WHERE evaluation_completed IS NULL;

-- Create index for faster queries on evaluation_completed
CREATE INDEX IF NOT EXISTS idx_event_attendance_evaluation 
ON event_attendance(event_id, evaluation_completed);
