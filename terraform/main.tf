terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.36"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.2"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  repo_root            = abspath("${path.module}/..")
  order_service_dir    = "${local.repo_root}/services/rappi-order-api"
  status_service_dir   = "${local.repo_root}/services/rappi-status-api"
  order_service_hash   = substr(sha256(join("", [for file_name in ["main.py", "requirements.txt", "Dockerfile"] : file("${local.order_service_dir}/${file_name}")])), 0, 12)
  status_service_hash  = substr(sha256(join("", [for file_name in ["main.py", "requirements.txt", "Dockerfile"] : file("${local.status_service_dir}/${file_name}")])), 0, 12)
  artifact_registry    = "${var.region}-docker.pkg.dev/${var.project_id}/${var.artifact_registry_repository}"
  order_image          = "${local.artifact_registry}/${var.order_api_service_name}:${local.order_service_hash}"
  status_image         = "${local.artifact_registry}/${var.status_api_service_name}:${local.status_service_hash}"
}

resource "google_project_service" "required_apis" {
  for_each = toset([
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com",
    "firestore.googleapis.com",
    "iam.googleapis.com",
  ])

  project                    = var.project_id
  service                    = each.value
  disable_dependent_services = false
  disable_on_destroy         = false
}

resource "google_artifact_registry_repository" "docker_repo" {
  project       = var.project_id
  location      = var.region
  repository_id = var.artifact_registry_repository
  description   = "Docker images for gcp-rappi-fake"
  format        = "DOCKER"

  depends_on = [google_project_service.required_apis]
}

resource "google_firestore_database" "default" {
  project                     = var.project_id
  name                        = "(default)"
  location_id                 = var.region
  type                        = "FIRESTORE_NATIVE"

  depends_on = [google_project_service.required_apis]
}

resource "null_resource" "build_order_api_image" {
  triggers = {
    image        = local.order_image
    service_hash = local.order_service_hash
  }

  provisioner "local-exec" {
    command = "gcloud builds submit \"${local.order_service_dir}\" --project=\"${var.project_id}\" --tag=\"${local.order_image}\""
  }

  depends_on = [google_artifact_registry_repository.docker_repo]
}

resource "null_resource" "build_status_api_image" {
  triggers = {
    image        = local.status_image
    service_hash = local.status_service_hash
  }

  provisioner "local-exec" {
    command = "gcloud builds submit \"${local.status_service_dir}\" --project=\"${var.project_id}\" --tag=\"${local.status_image}\""
  }

  depends_on = [google_artifact_registry_repository.docker_repo]
}

resource "google_cloud_run_v2_service" "order_api" {
  name     = var.order_api_service_name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    timeout = "30s"

    containers {
      image = local.order_image

      ports {
        container_port = 8080
      }

      env {
        name  = "AWS_RAPPI_ORDER_URL"
        value = var.aws_rappi_order_url
      }

      env {
        name  = "RAPPI_API_KEY"
        value = var.rappi_api_key
      }

      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }

      env {
        name  = "FIRESTORE_COLLECTION"
        value = var.firestore_collection
      }
    }
  }

  depends_on = [null_resource.build_order_api_image, google_firestore_database.default]
}

resource "google_cloud_run_v2_service" "status_api" {
  name     = var.status_api_service_name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    timeout = "30s"

    containers {
      image = local.status_image

      ports {
        container_port = 8080
      }

      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }

      env {
        name  = "FIRESTORE_COLLECTION"
        value = var.firestore_collection
      }
    }
  }

  depends_on = [null_resource.build_status_api_image, google_firestore_database.default]
}

resource "google_cloud_run_v2_service_iam_member" "order_api_public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.order_api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "status_api_public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.status_api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
