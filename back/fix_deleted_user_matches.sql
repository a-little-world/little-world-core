-- Fix ALL Deleted User Matches Migration Script
-- This script deactivates ALL matches for ALL users who are marked as inactive (is_active = false)
-- This should resolve chat API user confusion issues across the entire database

BEGIN TRANSACTION;

-- 1. First, let's see the current state of ALL deleted users and their matches
SELECT 'Current state of ALL deleted users and their matches:' as info;

SELECT 
    u.id as user_id,
    u.email,
    u.is_active,
    COUNT(m.id) as total_matches,
    COUNT(CASE WHEN m.active = 1 THEN 1 END) as active_matches,
    COUNT(CASE WHEN m.active = 0 THEN 1 END) as inactive_matches
FROM management_user u
LEFT JOIN management_match m ON (m.user1_id = u.id OR m.user2_id = u.id)
WHERE u.is_active = 0
GROUP BY u.id, u.email, u.is_active
ORDER BY u.id;

-- 2. Show summary of what needs to be fixed
SELECT 'Summary of matches that need to be deactivated:' as info;

SELECT 
    COUNT(*) as total_active_matches_for_deleted_users
FROM management_match m
WHERE m.active = 1 
  AND (m.user1_id IN (SELECT id FROM management_user WHERE is_active = 0)
       OR m.user2_id IN (SELECT id FROM management_user WHERE is_active = 0));

-- 3. Show specific examples of problematic matches (first 10)
SELECT 'Examples of problematic matches (first 10):' as info;

SELECT 
    m.id as match_id,
    m.user1_id,
    m.user2_id,
    m.active,
    m.created_at,
    u1.email as user1_email,
    u2.email as user2_email,
    CASE 
        WHEN u1.is_active = 0 THEN 'DELETED'
        WHEN u2.is_active = 0 THEN 'DELETED'
        ELSE 'BOTH_ACTIVE'
    END as status
FROM management_match m
JOIN management_user u1 ON m.user1_id = u1.id
JOIN management_user u2 ON m.user2_id = u2.id
WHERE m.active = 1 
  AND (u1.is_active = 0 OR u2.is_active = 0)
ORDER BY m.created_at DESC
LIMIT 10;

-- 4. Deactivate ALL matches for ALL deleted users
UPDATE management_match 
SET active = 0, updated_at = CURRENT_TIMESTAMP
WHERE active = 1 
  AND (user1_id IN (SELECT id FROM management_user WHERE is_active = 0)
       OR user2_id IN (SELECT id FROM management_user WHERE is_active = 0));

-- 5. Show the results after the update
SELECT 'After update - ALL deleted users and their matches:' as info;

SELECT 
    u.id as user_id,
    u.email,
    u.is_active,
    COUNT(m.id) as total_matches,
    COUNT(CASE WHEN m.active = 1 THEN 1 END) as active_matches,
    COUNT(CASE WHEN m.active = 0 THEN 1 END) as inactive_matches
FROM management_user u
LEFT JOIN management_match m ON (m.user1_id = u.id OR m.user2_id = u.id)
WHERE u.is_active = 0
GROUP BY u.id, u.email, u.is_active
ORDER BY u.id;

-- 6. Verify that no active matches remain for deleted users
SELECT 'Verification - No active matches should remain for deleted users:' as info;

SELECT 
    COUNT(*) as remaining_active_matches_for_deleted_users
FROM management_match m
WHERE m.active = 1 
  AND (m.user1_id IN (SELECT id FROM management_user WHERE is_active = 0)
       OR m.user2_id IN (SELECT id FROM management_user WHERE is_active = 0));

-- 7. Show summary of all changes made
SELECT 'Summary of all changes made:' as info;

SELECT 
    COUNT(*) as total_matches_deactivated
FROM management_match 
WHERE active = 0 
  AND (user1_id IN (SELECT id FROM management_user WHERE is_active = 0)
       OR user2_id IN (SELECT id FROM management_user WHERE is_active = 0));

-- 8. Show which users were affected
SELECT 'Users whose matches were affected:' as info;

SELECT DISTINCT
    u.id as user_id,
    u.email,
    u.is_active
FROM management_user u
JOIN management_match m ON (m.user1_id = u.id OR m.user2_id = u.id)
WHERE u.is_active = 0
  AND m.active = 0
ORDER BY u.id;

COMMIT;

-- Note: If you want to rollback instead, use ROLLBACK instead of COMMIT
-- ROLLBACK;
