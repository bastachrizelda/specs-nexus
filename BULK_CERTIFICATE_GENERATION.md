# Bulk Certificate Generation - Specs Nexus

## Overview

The Bulk Certificate Generation feature allows officers to automatically generate personalized certificates for all eligible event participants using a template-based system. Certificates include:

- Personalized recipient names
- Unique verification codes
- Optional QR codes for verification
- Auto-generated thumbnails
- Secure storage in Cloudflare R2

## Database Schema

The feature uses the existing Supabase database schema without modifications:

### `certificate_templates` table
- `id` - Primary key
- `event_id` - Foreign key to events (unique)
- `template_url` - URL to certificate template image
- `name_x` - X coordinate for name placement
- `name_y` - Y coordinate for name placement
- `font_size` - Font size for name (default: 48)
- `font_color` - Font color hex code (default: #000000)
- `font_family` - Font family name (default: Arial)
- `archived` - Soft delete flag

### `certificates` table (updated)
- `id` - Primary key
- `user_id` - Foreign key to users
- `event_id` - Foreign key to events
- `certificate_url` - URL to generated certificate PDF
- `thumbnail_url` - URL to certificate thumbnail
- `file_name` - Original filename
- `issued_date` - Timestamp of issuance
- `certificate_code` - Unique verification code (auto-generated)
- **Unique constraint**: (user_id, event_id)

## Eligibility Rules

A user is eligible for certificate generation if:

1. ✅ They exist in `event_participants` (registered for event)
2. ✅ The event is NOT archived
3. ✅ At least ONE of the following is true:
   - `event_attendance.checked_in_at` IS NOT NULL (attended)
   - `event_attendance.evaluation_completed` = TRUE (completed evaluation)
4. ❌ They do NOT already have a certificate for this event

## API Endpoints

### 1. Upload/Update Certificate Template

**POST** `/certificates/events/{event_id}/template`

**Auth**: Officer required

**Form Data**:
- `template_file` (file) - Certificate template image (PNG/JPG)
- `name_x` (int) - X coordinate for name placement
- `name_y` (int) - Y coordinate for name placement
- `font_size` (int, optional) - Font size (default: 48)
- `font_color` (string, optional) - Hex color (default: #000000)
- `font_family` (string, optional) - Font name (default: Arial)

**Response**: `CertificateTemplateSchema`

**Example**:
```bash
curl -X POST "http://localhost:8000/certificates/events/1/template" \
  -H "Authorization: Bearer {officer_token}" \
  -F "template_file=@certificate_template.png" \
  -F "name_x=500" \
  -F "name_y=300" \
  -F "font_size=48" \
  -F "font_color=#000000" \
  -F "font_family=Arial"
```

---

### 2. Get Certificate Template

**GET** `/certificates/events/{event_id}/template`

**Auth**: Officer required

**Response**: `CertificateTemplateSchema` or 404

---

### 3. Generate Bulk Certificates

**POST** `/certificates/events/{event_id}/generate-bulk`

**Auth**: Officer required

**Response**:
```json
{
  "message": "Bulk certificate generation completed",
  "generated_count": 45,
  "failed_count": 0,
  "failed_users": [],
  "eligible_user_ids": [1, 2, 3, ...]
}
```

**Features**:
- ✅ **Idempotent**: Safe to re-run, only generates for users without certificates
- ✅ **Partial failure handling**: Continues processing even if some certificates fail
- ✅ **Auto-scaling**: Handles long names by reducing font size
- ✅ **Unique codes**: Generates unique verification codes (format: `SPECS-XXXX-XXXX-XXXX`)
- ✅ **QR codes**: Embeds QR code with certificate code for easy verification
- ✅ **Deterministic naming**: `SpecsNexus_{EventTitle}_{UserName}.pdf`

**Example**:
```bash
curl -X POST "http://localhost:8000/certificates/events/1/generate-bulk" \
  -H "Authorization: Bearer {officer_token}"
```

---

### 4. Verify Certificate

**GET** `/certificates/verify/{certificate_code}`

**Auth**: Public (no authentication required)

**Response**:
```json
{
  "valid": true,
  "certificate_code": "SPECS-A1B2-C3D4-E5F6",
  "recipient_name": "Juan Dela Cruz",
  "event_title": "Python Workshop 2024",
  "issued_date": "2024-12-17T15:47:00Z",
  "certificate_url": "https://..."
}
```

**Example**:
```bash
curl "http://localhost:8000/certificates/verify/SPECS-A1B2-C3D4-E5F6"
```

---

### 5. Download Single Certificate

**GET** `/certificates/download/{certificate_id}`

**Auth**: User required (must own certificate)

**Response**:
```json
{
  "certificate_url": "https://...",
  "file_name": "SpecsNexus_PythonWorkshop_JuanDelaCruz.pdf"
}
```

---

### 6. Download All Certificates (ZIP)

**GET** `/certificates/events/{event_id}/download-all`

**Auth**: Officer required

**Response**: ZIP file containing all certificates for the event

**Example**:
```bash
curl -X GET "http://localhost:8000/certificates/events/1/download-all" \
  -H "Authorization: Bearer {officer_token}" \
  -o certificates.zip
```

---

### 7. Get Eligible Count

**GET** `/certificates/events/{event_id}/eligible-count`

**Auth**: Officer required

**Response**:
```json
{
  "event_id": 1,
  "eligible_count": 45,
  "eligible_user_ids": [1, 2, 3, ...]
}
```

---

## Workflow

### Step 1: Upload Certificate Template

1. Officer logs in
2. Navigate to event management
3. Upload certificate template image
4. Specify name placement coordinates (name_x, name_y)
5. Configure font settings (size, color, family)

**Tip**: Use an image editor to determine exact pixel coordinates for name placement.

### Step 2: Check Eligible Users

```bash
GET /certificates/events/{event_id}/eligible-count
```

This shows how many users will receive certificates.

### Step 3: Generate Certificates

```bash
POST /certificates/events/{event_id}/generate-bulk
```

The system will:
1. ✅ Fetch active certificate template
2. ✅ Query eligible users (attendance + no existing certificate)
3. ✅ Download template image
4. ✅ For each user:
   - Generate unique certificate code
   - Render name on template with auto-scaling
   - Add certificate code and QR code
   - Convert to PDF
   - Upload to Cloudflare R2
   - Insert record into database
5. ✅ Return summary with success/failure counts

### Step 4: Verify Certificates

Users can verify certificates using:
- Certificate code lookup: `/certificates/verify/{code}`
- QR code scan (contains certificate code)

---

## Edge Cases Handled

### Long Names
- Auto-scales font size down to minimum 24px
- Respects max width (60% of template width)

### Duplicate Names
- Unique filenames using UUID prefix
- No collision issues

### Missing Attendance
- Only generates for users with check-in OR evaluation completed
- Skips users without attendance records

### Archived Events/Templates
- Validates event is not archived
- Only uses active (non-archived) templates

### Partial Failures
- Continues processing remaining users if one fails
- Returns detailed failure report with user IDs and error messages
- Uses database rollback per-user to prevent partial records

### Duplicate Certificate Codes
- Checks for uniqueness before inserting
- Regenerates if collision detected (extremely rare)

### Re-running Generation
- Idempotent: Safe to run multiple times
- Only generates for users without existing certificates
- Uses unique constraint (user_id, event_id) to prevent duplicates

---

## File Naming Convention

**Format**: `SpecsNexus_{EventTitle}_{UserFullName}.pdf`

**Example**: `SpecsNexus_Python_Workshop_2024_Juan_Dela_Cruz.pdf`

**Sanitization**:
- Removes special characters
- Replaces spaces with underscores
- Truncates to 50 characters per segment

---

## Certificate Code Format

**Format**: `SPECS-XXXX-XXXX-XXXX`

**Example**: `SPECS-A1B2-C3D4-E5F6`

**Properties**:
- 12 random alphanumeric characters (uppercase)
- Hyphen-separated for readability
- Cryptographically secure (using `secrets` module)
- Unique across all certificates

---

## Storage

All certificates are stored in **Cloudflare R2** under:

```
certificates/{event_id}/{uuid}_{filename}.pdf
```

**Example**:
```
certificates/1/a1b2c3d4e5f6_SpecsNexus_Python_Workshop_Juan_Dela_Cruz.pdf
```

Accessible via Cloudflare Worker URL:
```
https://specsnexus-images.senya-videos.workers.dev/certificates/...
```

---

## Installation

### 1. Install Dependencies

```bash
cd back
pip install -r requirements.txt
```

New dependency added: `qrcode==7.4.2`

### 2. Environment Variables

Ensure these are set in `.env`:

```env
CF_ACCESS_KEY_ID=your_cloudflare_access_key
CF_SECRET_ACCESS_KEY=your_cloudflare_secret_key
CLOUDFLARE_R2_BUCKET=specs-nexus-files
CLOUDFLARE_R2_ENDPOINT=https://your-account-id.r2.cloudflarestorage.com
CLOUDFLARE_WORKER_URL=https://specsnexus-images.senya-videos.workers.dev
DATABASE_URL=postgresql://user:pass@host:5432/db
```

### 3. Run Migrations (if needed)

The models will auto-create tables on startup. If you need to manually migrate:

```bash
# The certificate_code column and certificate_templates table
# should already exist in your Supabase database
```

### 4. Start Server

```bash
uvicorn app.main:app --reload
```

---

## Testing

### Test Certificate Template Upload

```bash
curl -X POST "http://localhost:8000/certificates/events/1/template" \
  -H "Authorization: Bearer {officer_token}" \
  -F "template_file=@test_template.png" \
  -F "name_x=500" \
  -F "name_y=300"
```

### Test Bulk Generation

```bash
curl -X POST "http://localhost:8000/certificates/events/1/generate-bulk" \
  -H "Authorization: Bearer {officer_token}"
```

### Test Verification

```bash
curl "http://localhost:8000/certificates/verify/SPECS-A1B2-C3D4-E5F6"
```

---

## Production Checklist

- [x] Database schema matches Supabase
- [x] Unique constraint on (user_id, event_id)
- [x] Auto-generated certificate_code
- [x] Idempotent bulk generation
- [x] Partial failure handling
- [x] Long name auto-scaling
- [x] QR code embedding
- [x] Public verification endpoint
- [x] ZIP download for officers
- [x] Cloudflare R2 storage integration
- [x] Proper error logging
- [x] Officer authentication required
- [x] CORS headers configured

---

## Troubleshooting

### Issue: "No active certificate template found"
**Solution**: Upload a template first using POST `/certificates/events/{event_id}/template`

### Issue: "No eligible users found"
**Solution**: Ensure users have checked in OR completed evaluation in `event_attendance` table

### Issue: "Failed to download template"
**Solution**: Verify template_url is accessible and returns a valid image

### Issue: Font not found
**Solution**: The system falls back to default font. Ensure font files are available on the server or use standard fonts (Arial, Times New Roman)

### Issue: Certificate code collision
**Solution**: System automatically regenerates. If persistent, check database for corruption.

---

## Future Enhancements

- [ ] Batch processing with progress tracking
- [ ] Email delivery of certificates
- [ ] Custom template variables (date, event location, etc.)
- [ ] Multiple template support per event
- [ ] Certificate revocation
- [ ] Blockchain verification
- [ ] Multi-language support

---

## Support

For issues or questions:
1. Check logs: `tail -f logs/app.log`
2. Verify database connectivity
3. Test Cloudflare R2 credentials
4. Review API response error messages

---

## License

Part of Specs Nexus - Student Organization Management System
