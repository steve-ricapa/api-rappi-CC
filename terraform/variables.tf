variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for Cloud Run, Artifact Registry and Firestore"
  type        = string
  default     = "us-central1"
}

variable "artifact_registry_repository" {
  description = "Artifact Registry repository name"
  type        = string
  default     = "rappi-fake-images"
}

variable "firestore_collection" {
  description = "Firestore collection for Rappi orders"
  type        = string
  default     = "rappi_orders"
}

variable "aws_rappi_order_url" {
  description = "AWS endpoint for POST /orders/rappi"
  type        = string
}

variable "rappi_api_key" {
  description = "Shared API key used when GCP calls AWS /orders/rappi"
  type        = string
  sensitive   = true
}

variable "order_api_service_name" {
  description = "Cloud Run service name for rappi-order-api"
  type        = string
  default     = "rappi-order-api"
}

variable "status_api_service_name" {
  description = "Cloud Run service name for rappi-status-api"
  type        = string
  default     = "rappi-status-api"
}
