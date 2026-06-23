resource "aws_vpc" "this" {

  cidr_block = var.vpc_cidr

  enable_dns_support = true

  enable_dns_hostnames = true

  tags = {
    Name = "${var.project_name}-vpc"
  }

}

resource "aws_internet_gateway" "this" {

  vpc_id = aws_vpc.this.id

}

resource "aws_subnet" "public" {

  count = length(var.public_subnets)

  vpc_id = aws_vpc.this.id

  cidr_block = var.public_subnets[count.index]

  availability_zone = var.azs[count.index]

  map_public_ip_on_launch = true

}

resource "aws_subnet" "private" {

  count = length(var.private_subnets)

  vpc_id = aws_vpc.this.id

  cidr_block = var.private_subnets[count.index]

  availability_zone = var.azs[count.index]

}

resource "aws_eip" "nat" {

  count = var.nat_gateway_count

  domain = "vpc"

}

resource "aws_nat_gateway" "this" {

  count = var.nat_gateway_count

  subnet_id = aws_subnet.public[count.index].id

  allocation_id = aws_eip.nat[count.index].id

}
