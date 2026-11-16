#!/usr/bin/env bash
# Licensed to the .NET Foundation under one or more agreements.
# The .NET Foundation licenses this file to you under the MIT license.

set -euo pipefail

# emconfigure selects the real SDK tools using native Python paths. ICU's make
# helpers evaluate their command strings again, so backslashes must not become
# shell escapes. Change only path spelling, after the SDK has selected each tool.
original_cc="${CC-}"
for name in CC CXX AR LD NM RANLIB HOST_CC HOST_CXX; do
    value="${!name-}"
    if [[ -n "$value" ]]; then
        normalized="$(cygpath -m "$value")"
        if [[ ! -f "$value" || ! "$value" -ef "$normalized" ]]; then
            echo "Invalid SDK tool path for $name: $value" >&2
            exit 1
        fi
        printf -v "$name" '%s' "$normalized"
        export "$name"
        printf 'MSYS2 configure tool %s: %s -> %s\n' "$name" "$value" "$normalized" >&2
    fi
done

if [[ -v LDSHARED ]]; then
    if [[ -z "$original_cc" || "$LDSHARED" != "$original_cc -shared" ]]; then
        echo "Unsupported SDK LDSHARED command; cannot preserve its tool and suffix: $LDSHARED" >&2
        exit 1
    fi
    export LDSHARED="$CC -shared"
fi

exec /usr/bin/bash "$@"
