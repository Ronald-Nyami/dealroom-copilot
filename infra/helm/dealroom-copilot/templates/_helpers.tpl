{{- define "dealroom.name" -}}
{{- .Release.Name | trunc 40 | trimSuffix "-" -}}
{{- end -}}

{{- define "dealroom.labels" -}}
app.kubernetes.io/part-of: dealroom-copilot
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end -}}

{{- define "dealroom.selector" -}}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "dealroom.image" -}}
{{- printf "%s/%s:%s" .root.Values.image.registry .name .root.Values.image.tag -}}
{{- end -}}

{{/* Environment shared by the backend, the MCP server and the ingest job. */}}
{{- define "dealroom.env" -}}
- name: DEALROOM_ROOT
  value: /app
{{- if eq .Values.mode "cloud" }}
- name: DEALROOM_EXTRACTOR
  value: azure
- name: DEALROOM_LLM
  value: azure
- name: AZURE_TENANT_ID
  value: {{ required "azure.tenantId is required in cloud mode" .Values.azure.tenantId | quote }}
- name: AZURE_CLIENT_ID
  value: {{ required "azure.aiClientId is required in cloud mode" .Values.azure.aiClientId | quote }}
- name: AZURE_CLIENT_KEY_PATH
  value: /mnt/secrets/ai-client.pem
- name: AZURE_CLIENT_CERT_PATH
  value: /mnt/secrets/ai-client.pem
- name: AZURE_OPENAI_ENDPOINT
  value: {{ required "azure.openaiEndpoint is required in cloud mode" .Values.azure.openaiEndpoint | quote }}
- name: AZURE_OPENAI_DEPLOYMENT
  value: {{ .Values.azure.openaiDeployment | quote }}
- name: AZURE_DOCINTEL_ENDPOINT
  value: {{ required "azure.documentIntelligenceEndpoint is required in cloud mode" .Values.azure.documentIntelligenceEndpoint | quote }}
- name: DATABASE_URL
  valueFrom:
    secretKeyRef:
      name: {{ include "dealroom.name" . }}-database
      key: url
{{- else }}
- name: DEALROOM_EXTRACTOR
  value: local
- name: DEALROOM_LLM
  value: stub
{{- end }}
{{- end -}}

{{- define "dealroom.volumes" -}}
- name: index
  persistentVolumeClaim:
    claimName: {{ include "dealroom.name" . }}-index
{{- if eq .Values.mode "cloud" }}
- name: secrets
  csi:
    driver: secrets-store.csi.k8s.io
    readOnly: true
    volumeAttributes:
      secretProviderClass: {{ include "dealroom.name" . }}-keyvault
{{- end }}
{{- end -}}

{{- define "dealroom.mounts" -}}
- name: index
  mountPath: /app/.cache
{{- if eq .Values.mode "cloud" }}
- name: secrets
  mountPath: /mnt/secrets
  readOnly: true
{{- end }}
{{- end -}}

{{- define "dealroom.securityContext" -}}
runAsNonRoot: true
runAsUser: 10001
allowPrivilegeEscalation: false
capabilities:
  drop: ["ALL"]
seccompProfile:
  type: RuntimeDefault
{{- end -}}
