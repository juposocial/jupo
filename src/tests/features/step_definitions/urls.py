#! coding: utf-8
# pylint: disable-msg=W0311, W0611, E1103, E1101
#@PydevCodeAnalysisIgnore

import re

def url_for(page_name):
  urls = {
    'the home page': '/',
    'the login page': '/sign_in',
    'the signup page': '/sign_up',
  }
  
  path = urls.get(page_name)
  if not path:
    page = re.findall('the (.*) page', page_name)
    if page:
      path = '/%s' % page[0].replace(' ', '_')
      
  if path:
    return 'http://play.jupo.dev%s' % path
  else:
    raise """\
    Can't find mapping from "%s" to an url.
    Now, go and add a mapping in %s
    """ % (page_name, __file__)
    
    