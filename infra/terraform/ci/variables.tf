variable "region" {
  description = "Region projektu (ADR-0008)."
  type        = string
  default     = "eu-north-1"
}

variable "project" {
  description = "Prefiks nazw zasobów projektu. Rola wdrożeniowa może zarządzać tylko rolami IAM z tym prefiksem."
  type        = string
  default     = "ai-text-detector"
}

variable "github_repository" {
  description = "Repozytorium GitHub (owner/name), któremu ufają role CI."
  type        = string
  default     = "DeszczMikolaj/ai-detector-deployment"
}

variable "github_deploy_environment" {
  description = "GitHub Environment (z wymaganym zatwierdzeniem), z którego wolno przyjąć rolę wdrożeniową."
  type        = string
  default     = "dev"
}
