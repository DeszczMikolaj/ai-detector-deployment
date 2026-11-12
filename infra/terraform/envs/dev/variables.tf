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

variable "inference_model_version" {
  description = <<-EOT
    Wersja modelu championa w buckecie artefaktów (prefiks models/<wersja>/) — ADR-0012.
    Zmiana = nowa wersja Lambdy z nowym MODEL_URI. Docelowo promocję wykonuje admin-api.
  EOT
  type        = string
  default     = "v1"
}

variable "inference_shap_method" {
  description = "Metoda wyjaśnienia wyniku (ADR-0016): exact = TreeSHAP, approx = Saabas (~5× szybsza, mniej wiarygodna)."
  type        = string
  default     = "exact"

  validation {
    condition     = contains(["exact", "approx"], var.inference_shap_method)
    error_message = "inference_shap_method musi mieć wartość exact albo approx."
  }
}

variable "inference_memory_mb" {
  description = "Pamięć Lambdy (MB). Moc CPU rośnie proporcjonalnie do pamięci. Do dostrojenia po pomiarach."
  type        = number
  default     = 3008
}

variable "inference_timeout_s" {
  description = <<-EOT
    Maksymalny czas jednego wywołania (s). Klient i tak czeka maks. 29 s (limit API Gateway), ale dłuższy
    timeout pozwala dokończyć powtórzony init po timeoucie fazy init (pierwszy start nowego obrazu: ~34 s)
    — środowisko staje się ciepłe zamiast ginąć w pętli. Spike 2026-11-03, pomiar 2.
  EOT
  type        = number
  default     = 60
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
