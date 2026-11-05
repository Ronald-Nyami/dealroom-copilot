# Azure OpenAI and Document Intelligence.
# Both: public network access disabled, local (key) authentication disabled,
# reachable only through private endpoints, callable only with an Entra ID token.

resource "random_string" "suffix" {
  length  = 5
  upper   = false
  special = false
}

resource "azurerm_cognitive_account" "openai" {
  name                          = "oai-${var.name}-${random_string.suffix.result}"
  location                      = azurerm_resource_group.main.location
  resource_group_name           = azurerm_resource_group.main.name
  kind                          = "OpenAI"
  sku_name                      = "S0"
  custom_subdomain_name         = "oai-${var.name}-${random_string.suffix.result}"
  public_network_access_enabled = false
  local_auth_enabled            = false

  network_acls {
    default_action = "Deny"
  }

  tags = var.tags
}

resource "azurerm_cognitive_deployment" "chat" {
  name                 = var.chat_model.name
  cognitive_account_id = azurerm_cognitive_account.openai.id

  model {
    format  = "OpenAI"
    name    = var.chat_model.name
    version = var.chat_model.version
  }

  sku {
    name     = "GlobalStandard"
    capacity = var.chat_model.capacity
  }
}

resource "azurerm_cognitive_deployment" "embedding" {
  name                 = var.embedding_model.name
  cognitive_account_id = azurerm_cognitive_account.openai.id

  model {
    format  = "OpenAI"
    name    = var.embedding_model.name
    version = var.embedding_model.version
  }

  sku {
    name     = "Standard"
    capacity = var.embedding_model.capacity
  }

  depends_on = [azurerm_cognitive_deployment.chat]
}

resource "azurerm_cognitive_account" "docintel" {
  name                          = "di-${var.name}-${random_string.suffix.result}"
  location                      = azurerm_resource_group.main.location
  resource_group_name           = azurerm_resource_group.main.name
  kind                          = "FormRecognizer"
  sku_name                      = "S0"
  custom_subdomain_name         = "di-${var.name}-${random_string.suffix.result}"
  public_network_access_enabled = false
  local_auth_enabled            = false

  network_acls {
    default_action = "Deny"
  }

  tags = var.tags
}

resource "azurerm_private_endpoint" "openai" {
  name                = "pe-${azurerm_cognitive_account.openai.name}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  subnet_id           = azurerm_subnet.endpoints.id

  private_service_connection {
    name                           = "openai"
    private_connection_resource_id = azurerm_cognitive_account.openai.id
    subresource_names              = ["account"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "openai"
    private_dns_zone_ids = [azurerm_private_dns_zone.zones["openai"].id]
  }

  tags = var.tags
}

resource "azurerm_private_endpoint" "docintel" {
  name                = "pe-${azurerm_cognitive_account.docintel.name}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  subnet_id           = azurerm_subnet.endpoints.id

  private_service_connection {
    name                           = "docintel"
    private_connection_resource_id = azurerm_cognitive_account.docintel.id
    subresource_names              = ["account"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "docintel"
    private_dns_zone_ids = [azurerm_private_dns_zone.zones["cognitive"].id]
  }

  tags = var.tags
}
