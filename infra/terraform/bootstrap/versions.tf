terraform {
  required_version = ">= 1.10, < 2.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # Krok 1: pierwsze `apply` ze stanem lokalnym (bucket jeszcze nie istnieje).
  # Krok 2: odkomentuj blok poniżej, wpisz nazwę bucketa z outputu `state_bucket_name`
  #         i uruchom `terraform init -migrate-state` — stan bootstrapu trafi do bucketa.
  #
  backend "s3" {
    bucket       = "ai-text-detector-tfstate-366366122547-eu-north-1"
    key          = "bootstrap/terraform.tfstate"
    region       = "eu-north-1"
    encrypt      = true
    use_lockfile = true
  }
}
