# environments/staging.mk — loaded by `make <target> ENV=staging`.
PROJECT_ID := fde-bootcamp
LOCATION   := us
# APP_ID is set once the app is created in fde-bootcamp/locations/us, or passed via APP_ID=<id>
APP_ID     ?=
AGENT_NAME := snehsm-FDEBootcamp-CHI-greenfield

# Voice model for CES composite voice. Defaults to gemini-composite-v2.
# Override with VOICE_MODEL=gemini-composite-v1 if fde-bootcamp requires v1 at push time.
VOICE_MODEL ?= gemini-composite-v2
