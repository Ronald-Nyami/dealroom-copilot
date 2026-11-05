# Two separate identities, each with the least privilege it needs.
#
# 1. Service principal "dealroom-ai" authenticates to Azure OpenAI and Document
#    Intelligence with a certificate (private key + X.509), never a secret. The
#    certificate is generated inside Key Vault; the private key is never exported
#    to Terraform state or to a developer machine. Pods mount it read-only through
#    the Secrets Store CSI driver.
# 2. A user-assigned managed identity, federated with the backend's Kubernetes
#    service account (workload identity), may only read that certificate.

data "azurerm_client_config" "current" {}

resource "azurerm_key_vault" "main" {
  name                          = "kv-${var.name}-${random_string.suffix.result}"
  location                      = azurerm_resource_group.main.location
  resource_group_name           = azurerm_resource_group.main.name
  tenant_id                     = data.azurerm_client_config.current.tenant_id
  sku_name                      = "standard"
  enable_rbac_authorization     = true
  purge_protection_enabled      = true
  soft_delete_retention_days    = 30
  public_network_access_enabled = length(var.deployer_ip_ranges) > 0

  network_acls {
    bypass         = "None"
    default_action = "Deny"
    ip_rules       = var.deployer_ip_ranges
  }

  tags = var.tags
}

resource "azurerm_private_endpoint" "vault" {
  name                = "pe-${azurerm_key_vault.main.name}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  subnet_id           = azurerm_subnet.endpoints.id

  private_service_connection {
    name                           = "vault"
    private_connection_resource_id = azurerm_key_vault.main.id
    subresource_names              = ["vault"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "vault"
    private_dns_zone_ids = [azurerm_private_dns_zone.zones["vault"].id]
  }

  tags = var.tags
}

resource "azurerm_role_assignment" "deployer_certificates" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Certificates Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_role_assignment" "deployer_secrets" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_key_vault_certificate" "ai_client" {
  name         = "dealroom-ai-client"
  key_vault_id = azurerm_key_vault.main.id

  certificate_policy {
    issuer_parameters {
      name = "Self"
    }

    key_properties {
      exportable = true # exportable to the pod through the CSI driver, not to Terraform
      key_type   = "RSA"
      key_size   = 3072
      reuse_key  = false
    }

    secret_properties {
      content_type = "application/x-pem-file"
    }

    x509_certificate_properties {
      subject            = "CN=dealroom-ai-client"
      validity_in_months = 6
      key_usage          = ["digitalSignature", "keyEncipherment"]
      extended_key_usage = ["1.3.6.1.5.5.7.3.2"]
    }

    lifetime_action {
      action {
        action_type = "AutoRenew"
      }
      trigger {
        days_before_expiry = 30
      }
    }
  }

  depends_on = [azurerm_role_assignment.deployer_certificates]
}

resource "azuread_application" "ai" {
  display_name = "${var.name}-ai-client"
  owners       = [data.azurerm_client_config.current.object_id]
}

resource "azuread_application_certificate" "ai" {
  application_id = azuread_application.ai.id
  type           = "AsymmetricX509Cert"
  encoding       = "hex"
  value          = azurerm_key_vault_certificate.ai_client.certificate_data
  end_date       = azurerm_key_vault_certificate.ai_client.certificate_attribute[0].expires
  start_date     = azurerm_key_vault_certificate.ai_client.certificate_attribute[0].not_before
}

resource "azuread_service_principal" "ai" {
  client_id = azuread_application.ai.client_id
  owners    = [data.azurerm_client_config.current.object_id]
}

resource "azurerm_role_assignment" "ai_openai" {
  scope                = azurerm_cognitive_account.openai.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = azuread_service_principal.ai.object_id
}

resource "azurerm_role_assignment" "ai_docintel" {
  scope                = azurerm_cognitive_account.docintel.id
  role_definition_name = "Cognitive Services User"
  principal_id         = azuread_service_principal.ai.object_id
}

resource "azurerm_user_assigned_identity" "backend" {
  name                = "id-${var.name}-backend"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = var.tags
}

resource "azurerm_federated_identity_credential" "backend" {
  name                = "aks-${var.kubernetes_namespace}-backend"
  resource_group_name = azurerm_resource_group.main.name
  parent_id           = azurerm_user_assigned_identity.backend.id
  audience            = ["api://AzureADTokenExchange"]
  issuer              = azurerm_kubernetes_cluster.main.oidc_issuer_url
  subject             = "system:serviceaccount:${var.kubernetes_namespace}:dealroom-backend"
}

# Read access to the certificate's secret (PEM with private key) and nothing else in the vault.
resource "azurerm_role_assignment" "backend_certificate" {
  scope                = "${azurerm_key_vault.main.id}/secrets/${azurerm_key_vault_certificate.ai_client.name}"
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.backend.principal_id
}

resource "azurerm_role_assignment" "backend_database_secret" {
  scope                = azurerm_key_vault_secret.database_url.resource_versionless_id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.backend.principal_id
}
