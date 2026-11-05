# Values the Helm release needs. None of them is a secret.

output "resource_group" {
  value = azurerm_resource_group.main.name
}

output "aks_name" {
  value = azurerm_kubernetes_cluster.main.name
}

output "acr_login_server" {
  value = azurerm_container_registry.main.login_server
}

output "tenant_id" {
  value = data.azurerm_client_config.current.tenant_id
}

output "ai_client_id" {
  description = "Service principal that calls Azure OpenAI and Document Intelligence with its certificate."
  value       = azuread_application.ai.client_id
}

output "backend_identity_client_id" {
  description = "Managed identity federated with the backend service account; reads the certificate from Key Vault."
  value       = azurerm_user_assigned_identity.backend.client_id
}

output "key_vault_name" {
  value = azurerm_key_vault.main.name
}

output "ai_certificate_name" {
  value = azurerm_key_vault_certificate.ai_client.name
}

output "openai_endpoint" {
  value = azurerm_cognitive_account.openai.endpoint
}

output "openai_chat_deployment" {
  value = azurerm_cognitive_deployment.chat.name
}

output "openai_embedding_deployment" {
  value = azurerm_cognitive_deployment.embedding.name
}

output "docintel_endpoint" {
  value = azurerm_cognitive_account.docintel.endpoint
}

output "helm_values" {
  description = "Paste into infra/helm/dealroom-copilot/values.cloud.yaml or pass with --set."
  value = {
    "azure.tenantId"                     = data.azurerm_client_config.current.tenant_id
    "azure.aiClientId"                   = azuread_application.ai.client_id
    "azure.workloadIdentityClientId"     = azurerm_user_assigned_identity.backend.client_id
    "azure.keyVaultName"                 = azurerm_key_vault.main.name
    "azure.certificateName"              = azurerm_key_vault_certificate.ai_client.name
    "azure.openaiEndpoint"               = azurerm_cognitive_account.openai.endpoint
    "azure.openaiDeployment"             = azurerm_cognitive_deployment.chat.name
    "azure.documentIntelligenceEndpoint" = azurerm_cognitive_account.docintel.endpoint
    "image.registry"                     = azurerm_container_registry.main.login_server
  }
}
