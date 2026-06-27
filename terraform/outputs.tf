output "rappi_order_api_url" {
  description = "Public URL for rappi-order-api"
  value       = google_cloud_run_v2_service.order_api.uri
}

output "rappi_status_api_url" {
  description = "Public URL for rappi-status-api"
  value       = google_cloud_run_v2_service.status_api.uri
}

output "rappi_status_callback_url_for_aws" {
  description = "Copy this value into AWS RAPPI_STATUS_API_URL with the current AWS implementation"
  value       = "${google_cloud_run_v2_service.status_api.uri}/rappi/status"
}

output "aws_rappi_order_url_configured" {
  description = "AWS order endpoint configured in GCP"
  value       = var.aws_rappi_order_url
}

output "artifact_registry_repository_url" {
  description = "Artifact Registry repository URL"
  value       = local.artifact_registry
}
