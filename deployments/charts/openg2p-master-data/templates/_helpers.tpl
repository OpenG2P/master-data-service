{{/*
Create the name of the service account to use
*/}}
{{- define "gen2MasterData.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{ default (include "common.names.fullname" .) .Values.serviceAccount.name }}
{{- else -}}
{{ default "default" .Values.serviceAccount.name }}
{{- end -}}
{{- end -}}

{{/*
Return the proper Docker Image Secret Names
*/}}
{{- define "gen2MasterData.imagePullSecrets" -}}
{{- include "common.images.pullSecrets" (dict "images" (list .Values.image .Values.postgresCheckerInit.image) "global" .Values.global) -}}
{{- end -}}

{{/*
Render Env values section
*/}}
{{- define "gen2MasterData.baseEnvVars" -}}
{{- $context := .context -}}
{{- range $k, $v := .envVars }}
- name: {{ $k }}
{{- if or (kindIs "int64" $v) (kindIs "float64" $v) (kindIs "bool" $v) }}
  value: {{ $v | quote }}
{{- else if kindIs "string" $v }}
  value: {{ include "common.tplvalues.render" ( dict "value" $v "context" $context ) | squote }}
{{- else }}
  valueFrom: {{- include "common.tplvalues.render" ( dict "value" $v "context" $context ) | nindent 4}}
{{- end }}
{{- end }}
{{- end -}}

{{- define "gen2MasterData.envVars" -}}
{{- $envVars := merge (deepCopy .Values.envVars) (deepCopy .Values.envVarsFrom) -}}
{{- include "gen2MasterData.baseEnvVars" (dict "envVars" $envVars "context" $) }}
{{- end -}}

{{/*
Create the name of the service account to use
*/}}
{{- define "masterDataUi.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{ default (include "common.names.fullname" .) .Values.serviceAccount.name }}
{{- else -}}
{{ default "default" .Values.serviceAccount.name }}
{{- end -}}
{{- end -}}

{{/*
Return the proper Docker Image Secret Names
*/}}
{{- define "masterDataUi.imagePullSecrets" -}}
{{- include "common.images.pullSecrets" (dict "images" (list .Values.image) "global" .Values.global) -}}
{{- end -}}

{{- define "masterDataUi.envVars" -}}
{{- $envVars := merge (deepCopy .Values.envVars) (deepCopy .Values.envVarsFrom) -}}
{{- include "gen2MasterData.baseEnvVars" (dict "envVars" $envVars "context" .) }}
{{- end -}}

{{/*
Name prefix for the iam-register ConfigMap and Job: <release>-<chart>. The chart
name keeps them apart from other charts' iam-register resources in the same
release, but under an umbrella it is the dependency ALIAS — commons-services
aliases this chart as `masterData` — and Kubernetes names must be lowercase
RFC 1123, so the raw alias ("…-masterData-…") is rejected and the upgrade fails
at this hook. Lowercase it and replace anything else a name cannot hold.
*/}}
{{- define "gen2MasterData.iamRegisterPrefix" -}}
{{- printf "%s-%s" .Release.Name (regexReplaceAll "[^a-z0-9-]" (lower .Chart.Name) "-") | trunc 40 | trimSuffix "-" -}}
{{- end -}}
