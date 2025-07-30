#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Configuration ---
OCI_REGION_KEY="bom"
OCI_NAMESPACE="bm4vulrtwoqg"
IMAGE_NAME="leadsquared-gis-processor"
TARGET_PLATFORM="linux/arm64" # The architecture you want to build
# --- End Configuration ---

# 1. Check for buildx and create a builder if needed
BUILDER_NAME="my-multi-arch-builder"
if ! docker buildx ls | grep -q "$BUILDER_NAME"; then
  echo "--- Creating new buildx builder instance: $BUILDER_NAME ---"
  docker buildx create --name "$BUILDER_NAME" --use
else
  echo "--- Using existing buildx builder: $BUILDER_NAME ---"
  docker buildx use "$BUILDER_NAME"
fi

# 2. Get Git Hash
GIT_HASH=$(git rev-parse --short HEAD)
if [ -z "$GIT_HASH" ]; then
  echo "Error: Not a git repository or no commits. Please run 'git init && git commit'"
  exit 1
fi

FULL_IMAGE_URI="${OCI_REGION_KEY}.ocir.io/${OCI_NAMESPACE}/${IMAGE_NAME}"
IMAGE_WITH_TAG="${FULL_IMAGE_URI}:${GIT_HASH}"

# 3. Build and Push the image using buildx
echo "--- Building and pushing image for ${TARGET_PLATFORM}: ${IMAGE_WITH_TAG} ---"
docker buildx build \
  --platform "${TARGET_PLATFORM}" \
  --tag "${IMAGE_WITH_TAG}" \
  --tag "${FULL_IMAGE_URI}:latest" \
  --push \
  .

# 4. Inform the user to update the manifest
echo ""
echo "✅ Image successfully built and pushed to OCI Registry."
echo ""
echo "------------------------------------------------------------------"
echo "NEXT STEP: Update your Kubernetes manifest with the new image tag."
echo "File:      gitops/manifests/leadsquared/02-deployment.yaml"
echo "New Image: ${IMAGE_WITH_TAG}"
echo "------------------------------------------------------------------"