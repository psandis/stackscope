terraform {
  required_providers {
    aws = {
      source = "hashicorp/aws"
    }
  }
}

provider "aws" {
  region = "eu-west-1"
}

resource "aws_s3_bucket" "artifacts" {
  bucket = "sample-app-artifacts"
}

resource "aws_db_instance" "primary" {
  identifier = "sample-app-db"
}

