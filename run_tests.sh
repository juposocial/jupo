#!/bin/bash

# Setup
Xvfb :0 -screen 0 1366x768x24 2> /dev/null &
nohup xvfb-run java -jar src/tests/features/selenium-server-standalone-2.32.0.jar > /var/log/jupo/selenium.log &
export DISPLAY=:0

# Run tests
cd src/tests && lettuce

# Teardown
pkill -9 -f 'Xvfb'
pkill -9 -f 'selenium-server'