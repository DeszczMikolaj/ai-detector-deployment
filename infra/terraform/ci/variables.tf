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

# Repozytoria utworzone po 15.07.2026 (nasze: 30.10.2026) dostają w tokenie OIDC `sub` z niezmiennymi
# numerycznymi ID: repo:<owner>@<owner_id>/<repo>@<repo_id>:... ID nie zmienia się po zmianie nazwy, więc
# ktoś, kto założy repo o tej samej nazwie, nie przejmie zaufania. Odczyt:
#   gh api repos/DeszczMikolaj/ai-detector-deployment --jq '.owner.id, .id'
variable "github_owner_id" {
  description = "Niezmienne numeryczne ID właściciela repozytorium na GitHubie."
  type        = number
  default     = 47246350
}

variable "github_repository_id" {
  description = "Niezmienne numeryczne ID repozytorium na GitHubie."
  type        = number
  default     = 1439709252
}

variable "github_deploy_environment" {
  description = "GitHub Environment (z wymaganym zatwierdzeniem), z którego wolno przyjąć rolę wdrożeniową."
  type        = string
  default     = "dev"
}
