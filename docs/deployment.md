The service is deployed on JetBrains Cloud Console with kubernetes

Production urls:
- https://console.intellij.net/cicd-apps?clusterId=gke-europe-west1&namespace=csc-lms
- https://teamcity-it.intellij.net/project/KubernetesController_GkeBelgiumEuropeWest1_csc_lms

Staging urls:
- https://console.intellij.net/cicd-apps?clusterId=gke-europe-west1&namespace=csc-lms-staging
- https://teamcity-it.intellij.net/project/KubernetesController_GkeBelgiumEuropeWest1_csc_lms_staging

All CI pipelines are currently located in the TeamCity project.

The deployment consists of 4 helm charts:
1. The main app
    - Deployed by CI pipeline
    - From "simple-app" helm chart https://jetbrains.team/p/cb/repositories/helm-charts/files/simple-app
2. Background worker
    - Deployed by CI pipeline
    - From "simple-worker" helm chart https://jetbrains.team/p/cb/repositories/helm-charts/files/simple-worker
3. Redis
    - Deployed manually
    - From "redis" helm chart https://jetbrains.team/p/cb/repositories/helm-charts/files/redis
4. oauth2-proxy
    - Deployed by CI pipeline
    - From "oauth2-proxy" chart in this repository

### oauth2-proxy

The application is behind oauth2-proxy authorization until full security audit is completed.

The helm chart is based on https://jetbrains.team/p/kitd/repositories/kubernetes-deploy/files/k8s-handle/oauth2-proxy

All requests to the app first go through nginx in the Kubernetes ingress controller.
It makes a request to the oauth2-proxy service to check if the user is authenticated.
If not, user is redirected to /oauth2/..., which maps to the oauth2-proxy service.

### Redis

A single Redis instance is used for both django app (db 0) and oauth2-proxy (db 1).
oauth2-proxy data is encrypted, so there are no security implications.

Django app uses Redis as a queue for the background worker and for storing thumbnail data.
oauth2-proxy uses Redis to store full session data.
