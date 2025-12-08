-- SQL Script to Add approval_status and decline_reason Columns to Events Table
-- Run this in your PostgreSQL database (Supabase SQL Editor)

-- Step 1: Create the enum type for approval status
DO $$ BEGIN
    CREATE TYPE event_approval_status AS ENUM ('pending', 'approved', 'declined');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Step 2: Add approval_status column with default value 'pending'
ALTER TABLE events 
ADD COLUMN IF NOT EXISTS approval_status event_approval_status DEFAULT 'pending';

-- Step 3: Add decline_reason column (nullable)
ALTER TABLE events 
ADD COLUMN IF NOT EXISTS decline_reason VARCHAR(500);

-- Step 4: Update existing events to 'approved' status (so they remain visible to students)
-- This assumes all existing events were already approved
UPDATE events 
SET approval_status = 'approved' 
WHERE approval_status IS NULL;

-- Verification: Check the columns were added
-- SELECT column_name, data_type, column_default 
-- FROM information_schema.columns 
-- WHERE table_name = 'events' 
-- AND column_name IN ('approval_status', 'decline_reason');

