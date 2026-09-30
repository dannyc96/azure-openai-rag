# Azure OpenAI RAG reference app.
#
# One root module, four moving parts:
#   1. Azure OpenAI account with gpt-4o (chat) and text-embedding-3-large deployments
#   2. Azure AI Search (basic tier, semantic ranking enabled)
#   3. A Container App running the FastAPI chat service
#   4. Role assignments wiring it together with managed identity only
#
# Security posture: local_auth is disabled on both AI services, so API keys
# do not exist. Every caller (the Container App and the developer) is an
# Entra ID principal with a scoped RBAC role. Nothing in code, env vars,
# or Terraform state can grant data access.

resource "random_string" "suffix" {
  length  = 5
  lower   = true
  upper   = false
  numeric = true
  special = false
}

locals {
  suffix = random_string.suffix.result

  # Deployment names are referenced by the app and ingestion via env vars.
  chat_deployment_name      = "gpt-4o"
  embedding_deployment_name = "text-embedding-3-large"
}

resource "azurerm_resource_group" "main" {
  name     = "rg-${var.prefix}"
  location = var.location
  tags     = var.tags
}

# ---------------------------------------------------------------------------
# Azure OpenAI
# ---------------------------------------------------------------------------

resource "azurerm_cognitive_account" "openai" {
  name                = "oai-${var.prefix}-${local.suffix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  kind                = "OpenAI"
  sku_name            = "S0"

  # Required for the OpenAI data-plane endpoint and for Entra ID auth.
  custom_subdomain_name = "oai-${var.prefix}-${local.suffix}"

  # No API keys. Entra ID (managed identity or az login) is the only way in.
  local_auth_enabled = false

  tags = var.tags
}

resource "azurerm_cognitive_deployment" "chat" {
  name                 = local.chat_deployment_name
  cognitive_account_id = azurerm_cognitive_account.openai.id

  model {
    format  = "OpenAI"
    name    = "gpt-4o"
    version = var.chat_model_version
  }

  sku {
    name     = "GlobalStandard"
    capacity = var.chat_deployment_capacity
  }
}

resource "azurerm_cognitive_deployment" "embedding" {
  name                 = local.embedding_deployment_name
  cognitive_account_id = azurerm_cognitive_account.openai.id

  model {
    format  = "OpenAI"
    name    = "text-embedding-3-large"
    version = "1"
  }

  sku {
    name     = "Standard"
    capacity = var.embedding_deployment_capacity
  }

  # Serialize deployment creation, the API rejects concurrent updates
  # to the same account.
  depends_on = [azurerm_cognitive_deployment.chat]
}

# ---------------------------------------------------------------------------
# Azure AI Search
# ---------------------------------------------------------------------------

resource "azurerm_search_service" "main" {
  name                = "srch-${var.prefix}-${local.suffix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "basic"

  # No admin or query keys. RBAC only.
  local_authentication_enabled = false

  # Semantic ranking, free tier covers a demo comfortably.
  semantic_search_sku = "free"

  tags = var.tags
}

# ---------------------------------------------------------------------------
# Container App (FastAPI chat service)
# ---------------------------------------------------------------------------

# Minimal workspace for Container Apps console logs. The full observability
# story (dashboards, alerts, budgets) lives in the azure-observability-stack
# repo in this portfolio.
resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-${var.prefix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = var.tags
}

resource "azurerm_container_app_environment" "main" {
  name                       = "cae-${var.prefix}"
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  tags                       = var.tags
}

resource "azurerm_container_app" "chat" {
  name                         = "ca-${var.prefix}-chat"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"
  tags                         = var.tags

  # The system-assigned identity is the app's only credential.
  # DefaultAzureCredential picks it up automatically inside the container.
  identity {
    type = "SystemAssigned"
  }

  ingress {
    external_enabled = true
    target_port      = 8000

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = 0
    max_replicas = 2

    container {
      name   = "chat"
      image  = var.container_image
      cpu    = 0.5
      memory = "1Gi"

      # Endpoints and deployment names only. There are no keys to leak.
      env {
        name  = "AZURE_OPENAI_ENDPOINT"
        value = azurerm_cognitive_account.openai.endpoint
      }
      env {
        name  = "AZURE_OPENAI_CHAT_DEPLOYMENT"
        value = azurerm_cognitive_deployment.chat.name
      }
      env {
        name  = "AZURE_OPENAI_EMBEDDING_DEPLOYMENT"
        value = azurerm_cognitive_deployment.embedding.name
      }
      env {
        name  = "AZURE_SEARCH_ENDPOINT"
        value = "https://${azurerm_search_service.main.name}.search.windows.net"
      }
      env {
        name  = "AZURE_SEARCH_INDEX"
        value = var.search_index_name
      }
    }
  }
}

# ---------------------------------------------------------------------------
# Role assignments: the entire auth story
# ---------------------------------------------------------------------------

# Container App -> Azure OpenAI: call chat completions and embeddings.
resource "azurerm_role_assignment" "app_openai_user" {
  scope                = azurerm_cognitive_account.openai.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = azurerm_container_app.chat.identity[0].principal_id
}

# Container App -> AI Search: query the index (read only, the app never writes).
resource "azurerm_role_assignment" "app_search_reader" {
  scope                = azurerm_search_service.main.id
  role_definition_name = "Search Index Data Reader"
  principal_id         = azurerm_container_app.chat.identity[0].principal_id
}

# Developer -> Azure OpenAI: run the app and ingestion locally via az login.
resource "azurerm_role_assignment" "dev_openai_user" {
  scope                = azurerm_cognitive_account.openai.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = var.developer_object_id
}

# Developer -> AI Search: ingestion writes documents into the index.
resource "azurerm_role_assignment" "dev_search_data_contributor" {
  scope                = azurerm_search_service.main.id
  role_definition_name = "Search Index Data Contributor"
  principal_id         = var.developer_object_id
}

# Developer -> AI Search: ingestion creates and updates the index schema.
resource "azurerm_role_assignment" "dev_search_service_contributor" {
  scope                = azurerm_search_service.main.id
  role_definition_name = "Search Service Contributor"
  principal_id         = var.developer_object_id
}
