terraform {
  required_version = ">= 1.10, < 2.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # Ten sam bucket stanu co envs/dev, osobny klucz. Stack stosuje WYŁĄCZNIE człowiek (ADR-0017):
  # CI nie może zmieniać własnych uprawnień.
  backend "s3" {
    bucket       = "ai-text-detector-tfstate-366366122547-eu-north-1"
    key          = "ci/terraform.tfstate"
    region       = "eu-north-1"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = var.project
      ManagedBy = "terraform"
      Component = "ci"
    }
  }
}

data "aws_caller_identity" "current" {}
