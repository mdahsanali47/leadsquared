#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Configuration ---
OCI_REGION_KEY="bom"
OCI_NAMESPACE="bm4vulrtwoqg"
IMAGE_NAME="leadsquared-gis-processor"
TARGET_PLATFORMS="linux/amd64,linux/arm64" 
FULL_IMAGE_URI="${OCI_REGION_KEY}.ocir.io/${OCI_NAMESPACE}/${IMAGE_NAME}"


# 1.multi-platform builder instance 
BUILDER_NAME="my-multi-arch-builder"
if ! docker buildx ls | grep -q "$BUILDER_NAME"; then
  echo "--- Creating new buildx builder instance: $BUILDER_NAME ---"
  docker buildx create --name "$BUILDER_NAME" --driver docker-container --use
else
  echo "--- Using existing buildx builder: $BUILDER_NAME ---"
  docker buildx use "$BUILDER_NAME"
fi
# Ensure the builder is running and ready to build.
docker buildx inspect --bootstrap


# 2. Get Git Hash for a unique, immutable image tag
GIT_HASH=$(git rev-parse --short HEAD)
if [ -z "$GIT_HASH" ]; then
  echo "Error: Not a git repository or no commits. Please run 'git init && git commit'"
  exit 1
fi

IMAGE_WITH_TAG="${FULL_IMAGE_URI}:${GIT_HASH}"
# Define a dedicated image tag for the remote build cache.
CACHE_IMAGE_URI="${FULL_IMAGE_URI}:build-cache"


# 3. Build and Push the multi-arch image using the remote cache
echo "--- Building and pushing image for platforms [${TARGET_PLATFORMS}] ---"
echo "Image Tag: ${IMAGE_WITH_TAG}"
echo "Cache Tag: ${CACHE_IMAGE_URI}"

docker buildx build \
  --platform "${TARGET_PLATFORMS}" \
  --tag "${IMAGE_WITH_TAG}" \
  --tag "${FULL_IMAGE_URI}:latest" \
  --push \
  --cache-from "type=registry,ref=${CACHE_IMAGE_URI}" \
  --cache-to "type=registry,ref=${CACHE_IMAGE_URI},mode=max" \
  .

# ECHO
echo ""
echo "Multi-arch image successfully built and pushed to OCI Registry."
echo " You can inspect it with: docker buildx imagetools inspect ${IMAGE_WITH_TAG}"
echo ""
echo "------------------------------------------------------------------"
echo "NEXT STEP: Update your Kubernetes manifest with the new image tag."
echo "File:      gitops/manifests/leadsquared/02-deployment.yaml"
echo "New Image: ${IMAGE_WITH_TAG}"
echo "------------------------------------------------------------------"