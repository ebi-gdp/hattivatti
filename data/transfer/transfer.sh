#!/usr/bin/env bash

set -euxo pipefail

# A simple way to download a set of files from an INTERVENE globus collection
# using curl and HTTPS. Doesn't retry, resume, or do anything fancy.
# All configuration is done with environment variables.
# This script is kept here as a reference when deploying hattivatti to Puhti.

check_environment_variables () {
    # GLOBUS_BASE_URL https://docs.globus.org/globus-connect-server/v5/https-access-collections/#determining_the_collection_https_base_url
    # GLOBUS_SECRET_TOKEN: globus sdk client token
    # GLOBUS_GUEST_COLLECTION_ID: uuid, from message
    # JOB_MESSAGE: a validated JSON message sent by the backend
    env_vars=("GLOBUS_BASE_URL" "GLOBUS_SECRET_TOKEN" "GLOBUS_GUEST_COLLECTION_ID" "JOB_MESSAGE")
    for var in "${env_vars[@]}"; do
        echo "Checking environment variable $var"
        # print indirect reference, only errors correctly with set -u
        echo "${!var} OK"
    done
}

grab_access_token () {
    GLOBUS_ACCESS_TOKEN=$(curl -s -X POST -H "Authorization: Basic $GLOBUS_SECRET_TOKEN" \
                               -d "scope=https://auth.globus.org/scopes/$GLOBUS_GUEST_COLLECTION_ID/https&grant_type=client_credentials" \
                               https://auth.globus.org/v2/oauth2/token \
                              | jq -r '.access_token')
}

download_files () {
    GLOBUS_HEADER="\"Authorization: Bearer $GLOBUS_ACCESS_TOKEN\""

    # step 1: extract a list of file names and extensions from the job message
    # e.g. test.pgen
    FILE_PATHS=$(mktemp)
    jq -r '.pipeline_param.target_genomes[] | (.pgen, .pvar, .psam)' <(echo "$JOB_MESSAGE") > $FILE_PATHS
    DIRECTORY=$(echo $JOB_MESSAGE | jq -r '.globus_details.dir_path_on_guest_collection + "/"')
    CURL_CMD="curl -s -f -O -L -X GET \
                        -H "$GLOBUS_HEADER" \
                        --url "${GLOBUS_BASE_URL}/${DIRECTORY}/{PATH}" \
                        -w "%{json}" >> transfer_log.json"
    DOWNLOAD_PATH=$(mktemp)

    # step 2: print a list of curl commands to a temporary file
    xargs -I {PATH} echo $CURL_CMD < $FILE_PATHS > $DOWNLOAD_PATH

    # step 3: run the curl commands to stage the files locally over HTTPS
    source $DOWNLOAD_PATH
}

main () {
    # clean up old transfer logs before starting downloads
    rm -f transfer_log.json

    check_environment_variables
    grab_access_token
    download_files

    # clean up temporary files when exiting the script
    # mktemp is quite secure so not really needed, just being tidy
    trap 'rm -f $FILE_PATHS $DOWNLOAD_PATH' EXIT
}

main
