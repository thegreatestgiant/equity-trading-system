#!/usr/bin/env nu

def main [...rest] {
    if ($rest | is-empty) {
        build trade-writer
        build db-syncer
        build price-cacher
        # build price-timeseries-cacher
        build redis-populator
    } else {
        $rest | each {build $in} | ignore
    }
}

def build [$name: string] {
    print $"building ($name) image..."

    let dirty = if (git status --porcelain | str trim | is-empty) { "" } else { "-dirty" }
    let commit = $"(git rev-parse --short HEAD | str trim)($dirty)"

    (
        docker build --file Containerfile
        --platform linux/amd64,linux/arm64
        --build-arg BIN_NAME=($name)
        --build-arg BUILD_SOURCE=dev-builder-script
        --build-arg BUILD_GIT_HASH=($commit)
        --tag ghcr.io/sm26-industrial-software-dev/($name):dev
        --push
        .
    )
}
