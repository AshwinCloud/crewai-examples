terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  required_version = ">= 1.3.0"

  backend "s3" {
    # optional if using remote state
    bucket = "your-terraform-state-bucket"
    key    = "aurora-postgres/terraform.tfstate"
    region = "us-east-1"
  }
}

provider "aws" {
  region = "us-east-1"
}

module "aurora_postgres" {
  source = "tfe.mycompany.com/MODULE-REGISTRY/rds-aurora-postgres/aws"

  name                = "my-aurora-db"
  engine              = "aurora-postgresql"
  engine_version      = "15.3"
  instance_class      = "db.r6g.large"
  vpc_id              = "vpc-xxxxxxx"
  subnets             = ["subnet-xxxxxx1", "subnet-xxxxxx2"]
  db_username         = "admin"
  db_password         = "supersecurepassword"
  skip_final_snapshot = true
}