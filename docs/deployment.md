# Cloud deployment

This configuration passes `terraform validate` and `helm lint` in CI. It has not been applied to a real Azure subscription.

```bash
cd infra/terraform
cp example.tfvars terraform.tfvars          # subscription, region, runner IP for Key Vault
terraform init -backend-config=...          # remote state in your storage account
terraform apply
terraform output helm_values                # copy into values.cloud.example.yaml

az acr build -r <acr> -t dealroom-copilot-backend:0.1.0 -f backend/Dockerfile .
az acr build -r <acr> -t dealroom-copilot-web:0.1.0 web
helm upgrade --install dealroom infra/helm/dealroom-copilot -n dealroom --create-namespace \
  -f infra/helm/dealroom-copilot/values.cloud.example.yaml
```

Terraform creates a resource group, a virtual network with subnets for AKS, private endpoints and Postgres, private DNS zones, AKS (Azure CNI overlay with Cilium, workload identity, Key Vault CSI driver, Entra ID RBAC, local accounts disabled), Azure OpenAI with a chat and an embedding deployment, Document Intelligence, Postgres Flexible Server 16 with `vector` enabled, Key Vault holding the client certificate and the database URL, ACR, and the Entra ID application with its certificate credential and role assignments.

The Helm chart runs an ingest job, then the backend, the MCP server and the web app. `mode: offline` runs the same chart on any cluster without Azure.

## Environment variables (cloud mode)

`DEALROOM_EXTRACTOR=azure`, `DEALROOM_LLM=azure`, `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_KEY_PATH`, `AZURE_CLIENT_CERT_PATH`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, `AZURE_DOCINTEL_ENDPOINT`, `DATABASE_URL`.

For local experiments with a real model: `DEALROOM_LLM=openai` and `OPENAI_API_KEY`.
