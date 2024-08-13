#!/bin/bash

EMAILS_JSON='back/emails/emails.json'
RENDERED_DIR='rendered_test_emails'
ZIP_FILE='test_emails.zip'

# Create a directory to store the rendered test emails
mkdir -p "$RENDERED_DIR"

# Extract email IDs and templates from the emails.json file
EMAIL_IDS=$(jq -r '.emails | to_entries[] | .key' "$EMAILS_JSON")
EMAIL_TEMPLATES=$(jq -r '.emails | to_entries[] | .value.template' "$EMAILS_JSON")

# Convert email templates to an array
readarray -t TEMPLATES_ARRAY <<<"$EMAIL_TEMPLATES"

# Loop through the email IDs and corresponding templates
index=0
for email_id in $EMAIL_IDS; do
    template_path=${TEMPLATES_ARRAY[$index]}
    template_name=$(basename "$template_path" .html)

    # Create a directory for each template
    mkdir -p "${RENDERED_DIR}/${template_name}"

    # Make the curl request
    curl -X 'GET' "http://localhost:8000/api/matching/emails/templates/$template_name/test/" > "${RENDERED_DIR}/${template_name}/email.html"

    echo "Rendered $template_name to ${RENDERED_DIR}/${template_name}/email.html"

    # Extract and download images
    grep -oP '(?<=<img src=")[^"]*' "${RENDERED_DIR}/${template_name}/email.html" | while read -r img_url; do
        img_name=$(basename "$img_url")
        curl -X 'GET' "$img_url" -o "${RENDERED_DIR}/${template_name}/${img_name}"
        echo "Downloaded image $img_name from $img_url"
    done
    
    # zip the folder
    cd "$RENDERED_DIR"
    
    zip -r "$template_name.zip" "$template_name"
    rm -rf "$template_name"
    
    cd ..


    index=$((index + 1))
done

echo "All email templates and images have been rendered and stored in $ZIP_FILE."