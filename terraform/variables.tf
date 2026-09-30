variable "prefix" {
  description = "Short name prefix applied to every resource. Lowercase letters and digits only, it is also used in DNS names."
  type        = string
  default     = "nwrag"

  validation {
    condition     = can(regex("^[a-z][a-z0-9]{2,11}$", var.prefix))
    error_message = "prefix must be 3-12 chars, lowercase letters and digits, starting with a letter."
  }
}

variable "location" {
  description = "Azure region for all resources. Pick one where the gpt-4o and text-embedding-3-large models are available (for example swedencentral or eastus2)."
  type        = string
  default     = "swedencentral"
}

variable "developer_object_id" {
  description = "Entra ID object ID of the developer (or a group) who runs ingestion and local dev. Granted OpenAI User, Search Index Data Contributor, and Search Service Contributor. Find yours with: az ad signed-in-user show --query id -o tsv"
  type        = string
}

variable "container_image" {
  description = "Fully qualified container image for the chat app. Defaults to a public placeholder so the first apply succeeds before you have pushed an image. Build and push with 'make build-image', then re-apply with this set to your image."
  type        = string
  default     = "mcr.microsoft.com/k8se/quickstart:latest"
}

variable "chat_model_version" {
  description = "Model version for the gpt-4o deployment."
  type        = string
  default     = "2024-08-06"
}

variable "chat_deployment_capacity" {
  description = "Capacity (thousands of tokens per minute) for the gpt-4o deployment. Keep small for a demo."
  type        = number
  default     = 10
}

variable "embedding_deployment_capacity" {
  description = "Capacity (thousands of tokens per minute) for the embedding deployment."
  type        = number
  default     = 50
}

variable "search_index_name" {
  description = "Name of the AI Search index the app queries and ingestion writes to. Created by ingestion/ingest.py, not Terraform (index schemas are data plane)."
  type        = string
  default     = "northwind-docs"
}

variable "tags" {
  description = "Tags applied to every resource."
  type        = map(string)
  default = {
    project = "azure-openai-rag"
    owner   = "danny-chambers"
    managed = "terraform"
  }
}
