resource "azurerm_container_registry" "main" {
  name                          = "acr${var.name}${random_string.suffix.result}"
  location                      = azurerm_resource_group.main.location
  resource_group_name           = azurerm_resource_group.main.name
  sku                           = "Premium"
  admin_enabled                 = false
  public_network_access_enabled = true # CI pushes images; pulls happen over the private endpoint
  tags                          = var.tags
}

resource "azurerm_private_endpoint" "registry" {
  name                = "pe-${azurerm_container_registry.main.name}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  subnet_id           = azurerm_subnet.endpoints.id

  private_service_connection {
    name                           = "registry"
    private_connection_resource_id = azurerm_container_registry.main.id
    subresource_names              = ["registry"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "registry"
    private_dns_zone_ids = [azurerm_private_dns_zone.zones["registry"].id]
  }

  tags = var.tags
}

resource "azurerm_kubernetes_cluster" "main" {
  name                              = "aks-${var.name}"
  location                          = azurerm_resource_group.main.location
  resource_group_name               = azurerm_resource_group.main.name
  dns_prefix                        = var.name
  private_cluster_enabled           = var.aks_private_cluster
  oidc_issuer_enabled               = true
  workload_identity_enabled         = true
  role_based_access_control_enabled = true
  azure_policy_enabled              = true
  local_account_disabled            = true
  sku_tier                          = "Standard"

  default_node_pool {
    name                         = "system"
    vm_size                      = var.aks_node_size
    node_count                   = var.aks_node_count
    vnet_subnet_id               = azurerm_subnet.aks.id
    only_critical_addons_enabled = false
    upgrade_settings {
      max_surge = "33%"
    }
  }

  identity {
    type = "SystemAssigned"
  }

  azure_active_directory_role_based_access_control {
    azure_rbac_enabled = true
    tenant_id          = data.azurerm_client_config.current.tenant_id
  }

  network_profile {
    network_plugin      = "azure"
    network_plugin_mode = "overlay"
    network_data_plane  = "cilium"
    network_policy      = "cilium"
    outbound_type       = "loadBalancer"
  }

  key_vault_secrets_provider {
    secret_rotation_enabled = true
  }

  oms_agent {
    log_analytics_workspace_id      = azurerm_log_analytics_workspace.main.id
    msi_auth_for_monitoring_enabled = true
  }

  tags = var.tags
}

resource "azurerm_role_assignment" "aks_pull" {
  scope                            = azurerm_container_registry.main.id
  role_definition_name             = "AcrPull"
  principal_id                     = azurerm_kubernetes_cluster.main.kubelet_identity[0].object_id
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "aks_network" {
  scope                = azurerm_subnet.aks.id
  role_definition_name = "Network Contributor"
  principal_id         = azurerm_kubernetes_cluster.main.identity[0].principal_id
}

# --------------------------------------------------------------------------- Postgres + pgvector

resource "random_password" "postgres" {
  length  = 32
  special = false
}

resource "azurerm_postgresql_flexible_server" "main" {
  name                          = "psql-${var.name}-${random_string.suffix.result}"
  location                      = azurerm_resource_group.main.location
  resource_group_name           = azurerm_resource_group.main.name
  version                       = "16"
  sku_name                      = var.postgres_sku
  storage_mb                    = 32768
  delegated_subnet_id           = azurerm_subnet.postgres.id
  private_dns_zone_id           = azurerm_private_dns_zone.zones["postgres"].id
  public_network_access_enabled = false
  administrator_login           = "dealroom"
  administrator_password        = random_password.postgres.result
  zone                          = "1"
  backup_retention_days         = 7

  authentication {
    active_directory_auth_enabled = true
    password_auth_enabled         = true
    tenant_id                     = data.azurerm_client_config.current.tenant_id
  }

  depends_on = [azurerm_private_dns_zone_virtual_network_link.links]
  tags       = var.tags
}

resource "azurerm_postgresql_flexible_server_configuration" "extensions" {
  name      = "azure.extensions"
  server_id = azurerm_postgresql_flexible_server.main.id
  value     = "VECTOR"
}

resource "azurerm_postgresql_flexible_server_database" "dealroom" {
  name      = "dealroom"
  server_id = azurerm_postgresql_flexible_server.main.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

resource "azurerm_key_vault_secret" "database_url" {
  name         = "database-url"
  key_vault_id = azurerm_key_vault.main.id
  content_type = "postgresql-dsn"
  value        = format(
    "postgresql://dealroom:%s@%s:5432/dealroom?sslmode=require",
    random_password.postgres.result,
    azurerm_postgresql_flexible_server.main.fqdn,
  )
  depends_on = [azurerm_role_assignment.deployer_secrets]
}
