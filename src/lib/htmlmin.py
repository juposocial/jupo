#! coding: utf-8
# pylint: disable-msg=W0311

#! coding: utf-8
# pylint: disable-msg=W0311

"""A simple script to minify HTML. It may have bugs. It does not handle
JavaScript or CSS; there are good programs available that do that.

Usage:

      minify.py somefile.html > somefile-minified.html
      minify.py < somefile.html > somefile-minified.html

Due to the fact that this is just a hack, sometimes it helps to minify a
file twice:

      minify.py somefile.html | minify.py > somefile-minified.html

$Id: minify.py 1745 2008-12-01 05:57:12Z chris $
"""

from HTMLParser import HTMLParser, HTMLParseError
from cStringIO import StringIO
import re
import sys


REMOVE_WS = re.compile(r"\s{2,}").sub

class HTMLMinifier(HTMLParser):
  """An HTML minifier."""
  def __init__(self, output):
    """output: This callback function will be called when there is
    data to output. A good candidate to use is sys.stdout.write."""

    HTMLParser.__init__(self)
    self.output = output
    self.inside_pre = False

  def error(self, message):
    sys.stderr.write("Warning: " + message + "\n")

  def handle_starttag(self, tag, attributes):
    if "pre" == tag.lower():
      self.inside_pre = True
    self.output.write(self.get_starttag_text())

  def handle_startendtag(self, tag, attributes):
    self.handle_starttag(tag, attributes)

  def handle_endtag(self, tag):
    if "pre" == tag.lower():
      self.inside_pre = False
    self.output.write("</" + tag + ">")

  def handle_data(self, data):
    if not self.inside_pre:
      data = REMOVE_WS("\n", data)
    self.output.write(data)

  def handle_charref(self, name):
    self.output.write("&#" + name + ";")

  def handle_entityref(self, name):
    self.output.write("&" + name + ";")

  def handle_comment(self, data):
    return

  def handle_decl(self, data):
    return

  def handle_pi(self, data):
    return

def remove_extra_spaces(data):
    p = re.compile(r'\s+')
    return p.sub(' ', data)

#def remove_html_tags(data):
#    p = re.compile(r'<.*?>')
#    return p.sub('', data)

def html_minify(html):
  out = StringIO()
  m = HTMLMinifier(out)
  m.feed(html)
  try:
    m.close()
  except HTMLParseError, e:
    sys.stderr.write("Warning: " + str(e) + "\n")
  out.seek(0)
  data = out.read()
  data = remove_extra_spaces(data)
  return data

if __name__ == "__main__":
  html = '''
  <!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta http-equiv="X-UA-Compatible" content="IE=edge,chrome=1" />
    <title>Ovenbirds</title>

    <meta name="description" content="Online Music Recommendation" />
    <meta name="author" content="AloneRoad" />

    <link rel="shortcut icon" href="http://static.ovenbirds.dev/static/favicon.ico" />

    <link rel="stylesheet" type="text/css" href="http://static.ovenbirds.dev/static/css/core.css">
    <link rel="stylesheet" media="screen and (min-width: 1200px)" href="http://static.ovenbirds.dev/static/css/wide.css">

    <!-- <script type="text/javascript" src="/static/js/jquery-1.4.2.min.js">
     </script> -->
    <!-- <script type="text/javascript" src="/static/js/jquery.backstretch.min.js">
    </script> -->
    <script type="text/javascript" src="http://static.ovenbirds.dev/static/js/lib.js"></script>
    <script type="text/javascript">
      $.backstretch("http://static.ovenbirds.dev/static/images/bg/default.jpg",
      {speed: 500});
    </script>
  </head>
  '''
  a = html_minify(html)
  print a
