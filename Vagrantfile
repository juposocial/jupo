# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.configure("2") do |config|
  
  config.vm.box = "jupo"
  config.vm.box_url = "http://jupo.s3.amazonaws.com/vagrant-boxes/ubuntu-12.04_v4.box"

  config.vm.network :forwarded_port, guest: 80, host: 8080      # nginx
  config.vm.network :forwarded_port, guest: 6379, host: 6379    # redis-server
  config.vm.network :forwarded_port, guest: 27017, host: 27017  # mongodb
  config.vm.network :forwarded_port, guest: 11211, host: 11211  # memcached
  config.vm.network :private_network, ip: "10.0.0.10"

  config.vm.synced_folder "../jupo", "/home/Workspace/jupo"
  
end
