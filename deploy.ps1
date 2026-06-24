$REGION = "asia-south1"
$FUNCTION_NAME = "send-morning-news"
$SCHEDULER_JOB = "morning-news-job"
$PROJECT = gcloud config get-value project

Write-Host "Project: $PROJECT  |  Region: $REGION"
Write-Host ""

Write-Host "[1/3] Deploying Cloud Function..."
gcloud functions deploy $FUNCTION_NAME `
    --gen2 `
    --runtime python311 `
    --region $REGION `
    --source . `
    --entry-point send_morning_news `
    --trigger-http `
    --allow-unauthenticated `
    --env-vars-file env.yaml `
    --timeout 120s `
    --memory 256Mi

if (-not $?) { Write-Error "Function deploy failed. Stopping."; exit 1 }

Write-Host ""
Write-Host "[2/3] Reading function URL..."
$FUNCTION_URL = gcloud functions describe $FUNCTION_NAME --gen2 --region $REGION --format="value(serviceConfig.uri)"
Write-Host "URL: $FUNCTION_URL"

Write-Host ""
Write-Host "[3/3] Setting up Cloud Scheduler (8:00 AM IST daily)..."
$jobExists = gcloud scheduler jobs describe $SCHEDULER_JOB --location $REGION 2>$null
if ($jobExists) {
    gcloud scheduler jobs update http $SCHEDULER_JOB `
        --location $REGION `
        --schedule "0 8 * * *" `
        --time-zone "Asia/Kolkata" `
        --uri $FUNCTION_URL `
        --http-method POST `
        --attempt-deadline 120s
} else {
    gcloud scheduler jobs create http $SCHEDULER_JOB `
        --location $REGION `
        --schedule "0 8 * * *" `
        --time-zone "Asia/Kolkata" `
        --uri $FUNCTION_URL `
        --http-method POST `
        --attempt-deadline 120s
}

Write-Host ""
Write-Host "Deployed. WhatsApp news fires daily at 8:00 AM IST."
Write-Host ""
Write-Host "To trigger manually right now:"
Write-Host "  gcloud scheduler jobs run $SCHEDULER_JOB --location $REGION"
