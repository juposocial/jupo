#! coding: utf-8
# pylint: disable-msg=W0311
from urllib import urlopen
from os import path

data = open('main.css').read()
lines = data.split("\n")
urls = []
for line in lines:
  if 'http://' in line:
    url = line.split("(", 1)[1].rsplit(")", 1)[0]
    urls.append(url)

for url in set(urls):
  name = path.basename(url)
  filename = path.join('/home/Workspace/5works/src/public/images/tmp', name)
  data = urlopen(url).read()
  open(filename, 'w').write(data)
print 'Done'
  