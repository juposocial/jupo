#!/bin/bash
# Create workspace
# Install required packages
sudo apt-get install supervisor vim curl vim build-essential git libpcre3-dev libssl-dev python-dev libevent-dev python-setuptools libxslt-dev python-gevent python-virtualenv  

# Install selenium
sudo apt-get update
sudo apt-get install openjdk-6-jre-headless xfonts-100dpi xfonts-75dpi xfonts-scalable xfonts-cyrillic xserver-xorg-core firefox

# Download selenium server
wget http://selenium.googlecode.com/files/selenium-server-standalone-2.31.0.jar

# Run selenium server
Xvfb :0 -screen 0 1024x768x24 2>&1 >/dev/null &
export DISPLAY=:0
nohup xvfb-run java -jar selenium-server-standalone-2.31.0.jar > selenium.log &

#Install nginx
wget http://nginx.org/download/nginx-1.2.8.tar.gz
tar xvzf nginx-1.2.8.tar.gz
cd nginx-1.2.8
./configure --with-http_ssl_module --with-http_stub_status_module
sudo make
sudo make install
sudo cp /usr/local/nginx/sbin/nginx /usr/sbin/
sudo mkdir /var/log/nginx/
sudo useradd nginx