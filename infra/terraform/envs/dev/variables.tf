variable "region" {
  description = "Region projektu — jedyny dozwolony w new AWS experience (ADR-0008)."
  type        = string
  default     = "eu-north-1"
}

variable "project" {
  description = "Prefiks nazw i wartość tagu Project."
  type        = string
  default     = "ai-text-detector"
}

# --- Inference (ADR-0004, ADR-0012) ---

variable "inference_image_tag" {
  description = <<-EOT
    Tag obrazu Lambdy w ECR (np. krótki SHA commita). Dopóki null, Lambda i API Gateway
    nie są tworzone — najpierw powstaje samo repozytorium ECR, do którego wypychamy obraz.
  EOT
  type        = string
  default     = null
}

variable "inference_memory_mb" {
  description = "Pamięć Lambdy (MB). Moc CPU rośnie proporcjonalnie do pamięci. Do dostrojenia po pomiarach."
  type        = number
  default     = 3008
}

variable "inference_timeout_s" {
  description = "Maksymalny czas jednego wywołania (s)."
  type        = number
  default     = 30
}

variable "inference_max_text_chars" {
  description = "Twardy limit długości tekstu wejściowego (ochrona przed DoS — ADR-0002)."
  type        = number
  default     = 20000
}

variable "api_throttle_rate" {
  description = "Średni limit zapytań/s dla całego API (rate limit — ADR-0004)."
  type        = number
  default     = 10
}

variable "api_throttle_burst" {
  description = "Chwilowy szczyt zapytań ponad średni limit."
  type        = number
  default     = 20
}

variable "log_retention_days" {
  description = "Retencja logów CloudWatch."
  type        = number
  default     = 14
}

# --- Artefakty ML (ADR-0012, ADR-0014) ---

variable "artifacts_noncurrent_retention_days" {
  description = "Ile dni trzymamy poprzednie wersje nadpisanych lub usuniętych artefaktów w S3."
  type        = number
  default     = 90
}
