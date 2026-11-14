#!/bin/sh
# Spin Count: `./run.sh` is `make run`; `./run.sh test-all` etc. pass any make target.
# Uses Apple's Command Line Tools for make/git, so an unaccepted Xcode license (no sudo) doesn't block it.
if [ -d /Library/Developer/CommandLineTools ]; then
  export DEVELOPER_DIR=/Library/Developer/CommandLineTools
fi
cd "$(dirname "$0")" && exec make "${@:-run}"
