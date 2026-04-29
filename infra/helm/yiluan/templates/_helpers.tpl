{{/*
Expand the name of the chart.
*/}}
{{- define "yiluan.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "yiluan.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Chart name and version label.
*/}}
{{- define "yiluan.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Common labels
*/}}
{{- define "yiluan.labels" -}}
helm.sh/chart: {{ include "yiluan.chart" . }}
{{ include "yiluan.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: yiluan
{{- end -}}

{{/*
Selector labels
*/}}
{{- define "yiluan.selectorLabels" -}}
app.kubernetes.io/name: {{ include "yiluan.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
Component-scoped labels (usage: include "yiluan.componentLabels" (dict "ctx" . "component" "api"))
*/}}
{{- define "yiluan.componentLabels" -}}
{{ include "yiluan.labels" .ctx }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "yiluan.componentSelectorLabels" -}}
{{ include "yiluan.selectorLabels" .ctx }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{/*
ServiceAccount name
*/}}
{{- define "yiluan.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "yiluan.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{/*
Image reference helper. Usage: include "yiluan.image" (dict "img" .Values.api.image "ctx" .)
*/}}
{{- define "yiluan.image" -}}
{{- $tag := default .ctx.Chart.AppVersion .img.tag -}}
{{- printf "%s:%s" .img.repository $tag -}}
{{- end -}}
