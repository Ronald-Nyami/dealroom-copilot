variable "subscription_id" {
  description = "Azure subscription to deploy into."
  type        = string
}

variable "name" {
  description = "Short name used as a prefix for every resource."
  type        = string
  default     = "dealroom"

  validation {
    condition     = can(regex("^[a-z][a-z0-9]{2,11}$", var.name))
    error_message = "Use 3 to 12 lowercase letters or digits."
  }
}

variable "location" {
  description = "Azure region. Must offer Azure OpenAI and Document Intelligence."
  type        = string
  default     = "switzerlandnorth"
}

variable "address_space" {
  description = "Virtual network address space."
  type        = string
  default     = "10.40.0.0/16"
}

variable "deployer_ip_ranges" {
  description = "CIDR ranges allowed to reach Key Vault while Terraform runs (CI runner or admin IP). Empty when Terraform runs inside the virtual network."
  type        = list(string)
  default     = []
}

variable "aks_node_size" {
  type    = string
  default = "Standard_D4s_v5"
}

variable "aks_node_count" {
  type    = number
  default = 2
}

variable "aks_private_cluster" {
  description = "Private API server. Requires a runner inside the network for kubectl and helm."
  type        = bool
  default     = true
}

variable "chat_model" {
  type    = object({ name = string, version = string, capacity = number })
  default = {
    name     = "gpt-4o-mini"
    version  = "2024-07-18"
    capacity = 50
  }
}

variable "embedding_model" {
  type    = object({ name = string, version = string, capacity = number })
  default = {
    name     = "text-embedding-3-small"
    version  = "1"
    capacity = 50
  }
}

variable "postgres_sku" {
  type    = string
  default = "B_Standard_B2s"
}

variable "kubernetes_namespace" {
  type    = string
  default = "dealroom"
}

variable "tags" {
  type    = map(string)
  default = {
    project = "dealroom-copilot"
    data    = "synthetic"
  }
}
