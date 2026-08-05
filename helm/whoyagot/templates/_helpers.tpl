{{/*
The in-cluster Postgres DSN. Assembled from $(PGUSER)/$(PGPASSWORD), which
Kubernetes substitutes from the CloudNativePG app-user secret at container
start, so credentials never appear in the manifest.
*/}}
{{- define "whoyagot.databaseUrl" -}}
postgresql+psycopg2://$(PGUSER):$(PGPASSWORD)@{{ .Values.postgres.name }}-rw.{{ .Release.Namespace }}.svc.cluster.local:5432/{{ .Values.postgres.app.name }}
{{- end -}}

{{/*
Origins allowed to call the API directly.

The site itself never needs one — nginx proxies /api same-origin. These are for
the Android build, whose webview origin is https://localhost, plus the public
hostname so a direct browser call still works.
*/}}
{{- define "whoyagot.corsOrigins" -}}
https://{{ .Values.ingress.fqdn }},https://localhost,capacitor://localhost
{{- end -}}

{{/*
Google OAuth client IDs the API accepts, comma separated.

The web client ID plus any other client whose tokens should be honoured — an
Android build with its own OAuth client gets that client stamped into the
token's aud, so the API has to know about both. The web pod is deliberately not
given this list: GSI takes exactly one client_id, and a comma-joined value would
reach the browser as a single malformed ID.
*/}}
{{- define "whoyagot.googleClientIds" -}}
{{- $ids := list -}}
{{- if .Values.googleClientId -}}
{{- $ids = append $ids .Values.googleClientId -}}
{{- end -}}
{{- range .Values.extraGoogleClientIds -}}
{{- if . -}}
{{- $ids = append $ids . -}}
{{- end -}}
{{- end -}}
{{- join "," $ids -}}
{{- end -}}

{{/*
Environment shared by the API deployment and the sync CronJob.
*/}}
{{- define "whoyagot.apiEnv" -}}
- name: PGUSER
  valueFrom:
    secretKeyRef:
      name: {{ .Values.postgres.name }}-app-user
      key: username
- name: PGPASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ .Values.postgres.name }}-app-user
      key: password
- name: DATABASE_URL
  value: {{ include "whoyagot.databaseUrl" . | quote }}
- name: NFL_API_URL
  value: {{ .Values.api.nflApiUrl | quote }}
{{- if .Values.api.nflSeason }}
- name: NFL_SEASON
  value: {{ .Values.api.nflSeason | quote }}
{{- end }}
{{- end -}}
