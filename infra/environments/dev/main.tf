provider "aws" {

  region = "eu-central-1"

}

module "vpc" {

  source = "../../modules/vpc"

  project_name = "sentinel-dev"

  vpc_cidr = "10.10.0.0/16"

  azs = [

    "eu-central-1a",
    "eu-central-1b",
    "eu-central-1c"

  ]

  public_subnets = [

    "10.10.1.0/24",
    "10.10.2.0/24",
    "10.10.3.0/24"

  ]

  private_subnets = [

    "10.10.11.0/24",
    "10.10.12.0/24",
    "10.10.13.0/24"

  ]

  nat_gateway_count = 1

}
