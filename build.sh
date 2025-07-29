#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Configuration ---
OCI_REGION_KEY="bom"
OCI_NAMESPACE="bm4vulrtwoqg"
IMAGE_NAME="leadsquared-gis-processor"
# --- End Configuration ---

# 1. Get Git Hash
GIT_HASH=$(git rev-parse --short HEAD)
if [ -z "$GIT_HASH" ]; then
  echo "Error: Not a git repository or no commits."
  exit 1
fi

FULL_IMAGE_URI="${OCI_REGION_KEY}.ocir.io/${OCI_NAMESPACE}/${IMAGE_NAME}"
IMAGE_WITH_TAG="${FULL_IMAGE_URI}:${GIT_HASH}"

# 2. Build the arm64 Image
echo "--- Building image: ${IMAGE_WITH_TAG} ---"
docker build --platform linux/arm64 --tag ${IMAGE_WITH_TAG} --tag ${FULL_IMAGE_URI}:latest .

# 3. Push to OCI Registry
echo "--- Pushing image to OCI Registry ---"
docker push ${IMAGE_WITH_TAG}
docker push ${FULL_IMAGE_URI}:latest

# 4. Inform the user to update the manifest
echo ""
echo "✅ Image successfully built and pushed."
echo ""
echo "------------------------------------------------------------------"
echo "NEXT STEP: Update your Kubernetes manifest with the new image tag."
echo "File:      gitops/manifests/leadsquared/02-deployment.yaml"
echo "New Image: ${IMAGE_WITH_TAG}"
echo "------------------------------------------------------------------"