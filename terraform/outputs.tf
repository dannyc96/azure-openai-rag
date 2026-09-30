output "app_url" {
  description = "Public URL of the chat app."
  value       = "https://${azurerm_container_app.chat.ingress[0].fqdn}"
}

output "azure_openai_endpoint" {
  description = "Azure OpenAI endpoint (data access still requires an RBAC role, this is not a secret)."
  value       = azurerm_cognitive_account.openai.endpoint
}

output "azure_search_endpoint" {
  description = "Azure AI Search endpoint (data access still requires an RBAC role, this is not a secret)."
  value       = "https://${azurerm_search_service.main.name}.search.windows.net"
}

output "chat_deployment_name" {
  description = "Name of the gpt-4o deployment."
  value       = azurerm_cognitive_deployment.chat.name
}

output "embedding_deployment_name" {
  description = "Name of the embedding deployment."
  value       = azurerm_cognitive_deployment.embedding.name
}

output "search_index_name" {
  description = "Index name the app queries and ingestion populates."
  value       = var.search_index_name
}

output "resource_group_name" {
  description = "Resource group containing everything, handy for az CLI commands."
  value       = azurerm_resource_group.main.name
}
