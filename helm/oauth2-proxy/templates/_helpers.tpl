{{- define "helm.fullname" -}}
{{- .Values.applicationName | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "helm.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "helm.labels" -}}
helm.sh/chart: {{ include "helm.chart" . }}
{{ include "helm.selectorLabels" . }}
{{- end }}

{{- define "helm.selectorLabels" -}}
app: {{ include "helm.fullname" . }}
{{- end }}
