variable "aws_region" {
  description = "Region AWS primaria."
  default     = "us-east-1"
}

variable "project_name" {
  description = "Nombre del proyecto, utilizado en todos los tags"
  default     = "youprefer"
}

variable "environment" {
  description = "Entorno a desplegar (dev, staging, prod)"
  default     = "prod"
}

variable "db_username" {
  description = "Usuario admin de PostgreSQL"
  type        = string
  sensitive   = true
}

variable "db_password" {
  description = "Contraseña admin de PostgreSQL"
  type        = string
  sensitive   = true
}

variable "cloudflare_api_token" {
  description = "API Token para gestionar dominios y Cloudflare R2"
  type        = string
  sensitive   = true
}
