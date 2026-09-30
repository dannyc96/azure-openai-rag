# Remote state backend.
#
# Local state is fine for a demo. For anything shared, uncomment the block
# below and point it at a storage account. Note that with this design the
# state file contains no data-plane secrets either way: local auth is
# disabled on both Azure OpenAI and AI Search, so there are no keys for
# Terraform to store.
#
# terraform {
#   backend "azurerm" {
#     resource_group_name  = "rg-tfstate"
#     storage_account_name = "sttfstate<unique>"
#     container_name       = "tfstate"
#     key                  = "azure-openai-rag.tfstate"
#     use_azuread_auth     = true
#   }
# }
