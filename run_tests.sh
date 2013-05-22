#!/bin/bash

# Start Xvfb if it is not running
if [ ! -f /tmp/.X0-lock ]; then
	Xvfb :0 -screen 0 1366x768x24 2>/dev/null &
fi

# Start Selenium server if it is not running
ps cax | grep httpd > /dev/null
if [ $? -ne 0 ]; then
  nohup xvfb-run java -jar src/tests/features/selenium-server-standalone-2.32.0.jar > /var/log/jupo/selenium.log &
fi

# Run tests
export DISPLAY=:0	
cd src/tests && lettuce