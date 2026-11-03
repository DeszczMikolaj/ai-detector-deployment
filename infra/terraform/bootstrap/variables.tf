variable "region" {
  description = "Region AWS projektu (ADR-0008)."
  type        = string
  default     = "eu-north-1"
}

variable "project" {
  description = "Prefiks nazw i wartość tagu Project."
  type        = string
  default     = "ai-text-detector"
}

variable "noncurrent_version_retention_days" {
  description = "Ile dni trzymamy poprzednie wersje plików stanu (odzyskiwanie po błędzie)."
  type        = number
  default     = 90
}
