# -*- mode: ruby -*-
# vi: set ft=ruby :

$script = <<SCRIPT
  cd /usr/local/src/
  pip install -r /home/Workspace/jupo/requirements.txt --quiet --use-mirrors
SCRIPT

Vagrant.configure("2") do |config|
  
  config.vm.box = "jupo"
  config.vm.box_url = "http://jupo.s3.amazonaws.com/vagrant-boxes/ubuntu-12.04_v5.box"
  
  config.vm.provision :shell, :inline => $script

  config.vm.network :forwarded_port, guest: 80, host: 8080      # nginx
  config.vm.network :forwarded_port, guest: 9000, host: 9001    # python
  config.vm.network :forwarded_port, guest: 9002, host: 9002    # python
  config.vm.network :forwarded_port, guest: 6379, host: 6379    # redis-server
  config.vm.network :forwarded_port, guest: 27017, host: 27017  # mongodb
  config.vm.network :forwarded_port, guest: 11211, host: 11211  # memcached
  config.vm.network :private_network, ip: "10.10.10.10"
  
  config.vm.synced_folder "../jupo", "/home/Workspace/jupo"
  
end
