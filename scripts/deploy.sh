#!/bin/bash

ENV=$1
COMPONENT=$2
CLEAN=false
NO_HOOKS=""

# Parse additional flags
while [[ $# -gt 2 ]]; do
    case "$3" in
        --clean)
            CLEAN=true
            ;;
        --no-hooks)
            NO_HOOKS="--no-hooks"
            ;;
        *)
            echo "Unknown option: $3"
            exit 1
            ;;
    esac
    shift
done

# Valid component names
VALID_ENVIRONMENTS=("dev" "prod")
VALID_COMPONENTS=("graphdb" "airflow" "neo4j" "supabase")

# Function to validate component name
validate_component() {
    local component=$1
    for valid in "${VALID_COMPONENTS[@]}"; do
        if [ "$component" = "$valid" ]; then
            return 0
        fi
    done
    echo "Error: Invalid component '$component'"
    echo "Valid components: ${VALID_COMPONENTS[*]}"
    exit 1
}

# Check if the environment and component are provided
if [ -z "$ENV" ] || [ -z "$COMPONENT" ]; then
    echo "Usage: ./deploy.sh <environment> <component>"
    echo "Examples:"
    echo "  ./deploy.sh dev graphdb    # Deploys as graphdb-dev"
    echo "  ./deploy.sh prod graphdb   # Deploys as graphdb-prod"
    echo "Environments: ${VALID_ENVIRONMENTS[*]}"
    echo "Components: ${VALID_COMPONENTS[*]}"
    exit 1
fi

# Validate component name before proceeding
validate_component "$COMPONENT"

# Get the project root directory (one level up from scripts/)
PROJECT_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"

# Currently, we only have one namespace for all environments
NAMESPACE="wifire-kg"
# if [ "$ENV" = "prod" ]; then
#     NAMESPACE="wifire-kg-prod" # Prod namespace
# fi

# Function to add helm repo if it doesn't exist
add_helm_repo() {
    local repo_name=$1
    local repo_url=$2
    
    if ! helm repo list | grep -q "^${repo_name}"; then
        echo "Adding ${repo_name} helm repository..."
        helm repo add $repo_name $repo_url
        helm repo update $repo_name
    fi
}

# Function to deploy a component
deploy_component() {
    local component=$1
    local chart=$2
    local release_name="${component}-${ENV}"
    
    # Clean up existing release if --clean flag is set (skip for airflow)
    if [ "$CLEAN" = true ] && [ "$component" != "airflow" ]; then
        echo "Cleaning up existing release $release_name..."
        helm uninstall $release_name --namespace $NAMESPACE ${NO_HOOKS:-} || true
        # Wait for resources to be cleaned up
        sleep 5
    fi
    
    # Add required repo based on component
    case $component in
        "airflow")
            echo "Deploying Airflow using manifests..."
            
            # Delete existing resources if --clean flag is set
            if [ "$CLEAN" = true ]; then
                echo "Cleaning up existing Airflow resources..."
                kubectl delete deployment postgres redis airflow-webserver airflow-scheduler airflow-worker --namespace $NAMESPACE --ignore-not-found
                kubectl delete service postgres redis airflow-webserver --namespace $NAMESPACE --ignore-not-found
                kubectl delete configmap airflow-config --namespace $NAMESPACE --ignore-not-found
                kubectl delete ingress airflow-ingress --namespace $NAMESPACE --ignore-not-found
                
                # Wait for resources to be cleaned up
                echo "Waiting for resources to be cleaned up..."
                sleep 5
            fi
            
            # Deploy Redis and Postgres first
            echo "Deploying Redis and Postgres..."
            kubectl apply -f ${PROJECT_ROOT}/iac/manifests/airflow/airflow.redis.yaml
            kubectl apply -f ${PROJECT_ROOT}/iac/manifests/airflow/airflow.postgres.yaml
            
            # Wait for Redis and Postgres to be ready
            echo "Waiting for Redis and Postgres deployments to be ready..."
            kubectl wait --for=condition=Available=True deployment/redis -n $NAMESPACE --timeout=300s
            kubectl wait --for=condition=Available=True deployment/postgres -n $NAMESPACE --timeout=300s
            
            # Deploy main Airflow configuration
            echo "Deploying Airflow components..."
            kubectl apply -f ${PROJECT_ROOT}/iac/manifests/airflow/airflow.yaml
            
            # Wait for Airflow deployments to be ready
            echo "Waiting for Airflow components..."
            kubectl wait --for=condition=Available=True deployment/airflow-webserver -n $NAMESPACE --timeout=300s
            kubectl wait --for=condition=Available=True deployment/airflow-scheduler -n $NAMESPACE --timeout=300s
            kubectl wait --for=condition=Available=True deployment/airflow-worker -n $NAMESPACE --timeout=300s
            
            echo "Airflow deployment completed successfully!"
            echo "You can access the Airflow UI at: https://wifire-kg-airflow.nrp-nautilus.io"
            ;;
        "graphdb")
            add_helm_repo "ontotext" "https://maven.ontotext.com/repository/helm-public/"
            chart="ontotext/graphdb"
            ;;
        "neo4j")
            add_helm_repo "neo4j" "https://helm.neo4j.com/neo4j"
            chart="neo4j/neo4j"
            ;;
        "supabase")
            # Clone the repo if it doesn't exist or update it
            if [ ! -d "${PROJECT_ROOT}/charts/supabase-kubernetes" ]; then
                echo "Cloning Supabase Kubernetes repository..."
                git clone https://github.com/supabase-community/supabase-kubernetes.git "${PROJECT_ROOT}/charts/supabase-kubernetes"
            else
                echo "Updating Supabase Kubernetes repository..."
                cd "${PROJECT_ROOT}/charts/supabase-kubernetes"
                git pull
                cd - > /dev/null
            fi

            # Create a temporary values file starting with example values
            TMP_VALUES=$(mktemp)
            cat "${PROJECT_ROOT}/charts/supabase-kubernetes/charts/supabase/values.example.yaml" > "$TMP_VALUES"
            
            # Append our custom values on top
            cat "${PROJECT_ROOT}/iac/helm/values/${ENV}/${COMPONENT}.${ENV}.values.yaml" >> "$TMP_VALUES"
            
            # Add RBAC, ServiceAccount, and resource configurations for essential components
            cat >> "$TMP_VALUES" <<EOF
# Disable RBAC and ServiceAccount creation for all components
rbac:
  create: false

db:
  enabled: true
  image:
    repository: supabase/postgres
    tag: 15.1.0.103
    pullPolicy: IfNotPresent
  serviceAccount:
    create: false
  resources:
    limits:
      memory: 2Gi
      cpu: 1
    requests:
      memory: 1Gi
      cpu: 500m
  persistence:
    enabled: false  # Disable persistence temporarily
    # Add init container configurations to ensure proper startup
    initContainers:
      - name: init-db-dir
        image: busybox
        command: ['sh', '-c', 'mkdir -p /var/lib/postgresql/data && chmod 700 /var/lib/postgresql/data']
        volumeMounts:
          - name: data
            mountPath: /var/lib/postgresql

studio:
  enabled: true
  image:
    repository: supabase/studio
    tag: "latest"
    pullPolicy: IfNotPresent
  serviceAccount:
    create: false
  resources:
    limits:
      memory: 1Gi
      cpu: 500m
    requests:
      memory: 512Mi
      cpu: 250m
  environment:
    SUPABASE_PUBLIC_URL: "https://supabase-studio-${ENV}-wildfire-kg.nrp-nautilus.io"
    NEXT_PUBLIC_SUPABASE_URL: "https://supabase-studio-${ENV}-wildfire-kg.nrp-nautilus.io"
    NEXT_PUBLIC_SITE_URL: "https://supabase-studio-${ENV}-wildfire-kg.nrp-nautilus.io"
  ingress:
    enabled: true
    className: haproxy
    hosts:
      - host: supabase-studio-${ENV}-wildfire-kg.nrp-nautilus.io
    tls:
      - secretName: supabase-studio-${ENV}-tls
        hosts:
          - supabase-studio-${ENV}-wildfire-kg.nrp-nautilus.io

auth:
  enabled: true
  image:
    repository: supabase/gotrue
    tag: "v2.127.0"
    pullPolicy: IfNotPresent
    imagePullSecrets: []
  serviceAccount:
    create: false
  resources:
    limits:
      memory: 1Gi
      cpu: 500m
    requests:
      memory: 512Mi
      cpu: 250m
  environment:
    API_EXTERNAL_URL: "https://supabase-api-${ENV}-wildfire-kg.nrp-nautilus.io"
    GOTRUE_SITE_URL: "https://supabase-studio-${ENV}-wildfire-kg.nrp-nautilus.io"
    GOTRUE_URI_ALLOW_LIST: "https://supabase-studio-${ENV}-wildfire-kg.nrp-nautilus.io,https://supabase-api-${ENV}-wildfire-kg.nrp-nautilus.io"
    DB_SSL: "disable"
    GOTRUE_DISABLE_SIGNUP: "false"
    GOTRUE_JWT_EXP: "3600"
    GOTRUE_JWT_AUD: "authenticated"
    GOTRUE_JWT_DEFAULT_GROUP_NAME: "authenticated"
    GOTRUE_MAILER_AUTOCONFIRM: "true"

# Disable all other services
rest:
  enabled: false
realtime:
  enabled: false
meta:
  enabled: false
storage:
  enabled: false
imgproxy:
  enabled: false
kong:
  enabled: false
analytics:
  enabled: false
vector:
  enabled: false
functions:
  enabled: false
EOF

            # Use local chart path
            chart="${PROJECT_ROOT}/charts/supabase-kubernetes/charts/supabase"
            
            # Deploy using local chart
            echo "Deploying $release_name to $NAMESPACE namespace..."
            helm upgrade --install $release_name $chart \
                --namespace $NAMESPACE \
                --values "$TMP_VALUES" \
                ${NO_HOOKS}

            # Cleanup temporary file
            rm -f "$TMP_VALUES"
            
            # Wait for pods to be ready
            echo "Waiting for Supabase pods to be ready..."
            for deployment in $(kubectl get deployments -n $NAMESPACE -l "app.kubernetes.io/instance=$release_name" -o name); do
                echo "Waiting for deployment $deployment to be ready..."
                kubectl wait --for=condition=Available=True "$deployment" -n $NAMESPACE --timeout=300s || true
            done

            echo "Supabase deployment completed!"
            echo "You can access:"
            echo "- Studio UI at: https://supabase-studio-${ENV}-wildfire-kg.nrp-nautilus.io"
            echo "- API at: https://supabase-api-${ENV}-wildfire-kg.nrp-nautilus.io"
            ;;
    esac
}

case $COMPONENT in
    "airflow")
        deploy_component "airflow"
        ;;
    "graphdb")
        deploy_component "graphdb"
        ;;
    "neo4j")
        deploy_component "neo4j"
        ;;
    "supabase")
        deploy_component "supabase"
        ;;
    *)
        echo "Invalid component. Valid components: ${VALID_COMPONENTS[*]}"
        exit 1
        ;;
esac 