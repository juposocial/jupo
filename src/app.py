#! coding: utf-8
# pylint: disable-msg=W0311, W0611, E1103, E1101
#@PydevCodeAnalysisIgnore

from datetime import timedelta
from flask import Flask, render_template
from werkzeug.contrib.cache import MemcachedCache

from lib import cache
from helpers import extensions
from helpers.converters import (SnowflakeIDConverter, 
                                RegexConverter, UUIDConverter)

import api
import filters
import settings



CURRENT_APP = Flask(__name__, 
                    static_folder='public', 
                    template_folder='templates')


#sslify = SSLify(CURRENT_APP)

CURRENT_APP.secret_key = settings.SECRET_KEY
CURRENT_APP.permanent_session_lifetime = timedelta(days=365*10)




#===============================================================================
# Template settings
#===============================================================================

CURRENT_APP.jinja_env.add_extension(extensions.FragmentCacheExtension)
CURRENT_APP.jinja_env.fragment_cache = MemcachedCache(servers=settings.MEMCACHED_SERVERS,
                                    default_timeout=3600)

CURRENT_APP.jinja_env.filters['split'] = filters.split
CURRENT_APP.jinja_env.filters['clean'] = filters.clean
CURRENT_APP.jinja_env.filters['title'] = filters.title
CURRENT_APP.jinja_env.filters['nl2br'] = filters.nl2br
CURRENT_APP.jinja_env.filters['exclude'] = filters.exclude
CURRENT_APP.jinja_env.filters['unmunge'] = filters.unmunge
CURRENT_APP.jinja_env.filters['to_text'] = filters.to_text
CURRENT_APP.jinja_env.filters['endswith'] = filters.endswith
CURRENT_APP.jinja_env.filters['autolink'] = filters.autolink
CURRENT_APP.jinja_env.filters['strftime'] = filters.strftime
CURRENT_APP.jinja_env.filters['isoformat'] = filters.isoformat
CURRENT_APP.jinja_env.filters['sanitize'] = filters.sanitize_html
CURRENT_APP.jinja_env.filters['description'] = filters.description
CURRENT_APP.jinja_env.filters['autoemoticon'] = filters.autoemoticon
CURRENT_APP.jinja_env.filters['lines_truncate'] = filters.lines_truncate
CURRENT_APP.jinja_env.filters['friendly_format'] = filters.friendly_format
CURRENT_APP.jinja_env.filters['remove_signature'] = filters.remove_signature
CURRENT_APP.jinja_env.filters['fix_unclosed_tags'] = filters.fix_unclosed_tags
CURRENT_APP.jinja_env.filters['fix_unicode_error'] = filters.fix_unicode_error
CURRENT_APP.jinja_env.filters['remove_empty_lines'] = filters.remove_empty_lines
CURRENT_APP.jinja_env.filters['unique_by_timestamp'] = filters.unique_by_timestamp
CURRENT_APP.jinja_env.filters['last_starred_user'] = filters.last_starred_user
CURRENT_APP.jinja_env.filters['remove_groups'] = filters.remove_groups
CURRENT_APP.jinja_env.filters['to_embed_code'] = filters.to_embed_code
CURRENT_APP.jinja_env.filters['parse_json'] = filters.parse_json

CURRENT_APP.url_map.converters['uuid'] = UUIDConverter
CURRENT_APP.url_map.converters['regex'] = RegexConverter
CURRENT_APP.url_map.converters['snowflake_id'] = SnowflakeIDConverter






#===============================================================================
# Renders
#===============================================================================


FEED_TEMPLATE = CURRENT_APP.jinja_env.get_template('feed.html')
NOTE_TEMPLATE = CURRENT_APP.jinja_env.get_template('note.html')
FILE_TEMPLATE = CURRENT_APP.jinja_env.get_template('file.html')

def render(info, post_type, owner, viewport=None, mode=None, **kwargs): 
  if isinstance(info, list):
    return ''.join([_render(i, post_type, owner, viewport, mode) for i in info])
  else:
    return _render(info, post_type, owner, viewport, mode, **kwargs)



def _render(info, post_type, owner, viewport, mode=None, **kwargs):  
  owner_id = 'public' if (not owner or not owner.id) else owner.id
  
  if post_type in ['note', 'feed', 'file']:
    if mode:
      key = '%s:%s' % (viewport, mode)
    else:
      key = viewport
      
    if (owner and 
        owner.id and 
        owner.id != info.last_action.owner.id and 
        owner.id not in info.read_receipt_ids and 
        viewport != "discover"):
      status = 'unread'
    elif viewport == 'news_feed' and owner.id and owner.id in info.pinned_by:
      status = 'pinned'
    elif viewport == 'news_feed' and owner.id and owner.id in info.archived_by:
      status = 'archived'
    else:
      status = None
      
    if status:
      key = key + ':' + status
      
    key += ':%s:%s' % (post_type, owner_id)
    namespace = info.id
    
  else:
    key = post_type
    namespace = owner_id
    
  html = cache.get(key, namespace)
  hit = False
  if not html:
    if post_type == 'note':
      html = NOTE_TEMPLATE.render(note=info, 
                                  owner=owner, 
                                  view=viewport, 
                                  mode=mode, **kwargs)
    elif post_type == 'file':
      html = FILE_TEMPLATE.render(file=info, 
                                  owner=owner, 
                                  view=viewport, 
                                  mode=mode, **kwargs)
    
    else:
      html = FEED_TEMPLATE.render(feed=info, 
                                  owner=owner, 
                                  view=viewport, 
                                  mode=mode, **kwargs)
    cache.set(key, html, 86400, namespace)
  else:
    hit = True

  html = html.replace('<li id="post', '<li data-key="%s" data-namespace="%s" data-cache-status="%s" id="post' % (key, namespace, "HIT" if hit else "MISS"))
    
  return html



#def _render(info, post_type, owner, viewport, mode=None, **kwargs):    
#  if post_type == 'note':
#    html = NOTE_TEMPLATE.render(note=info, 
#                                owner=owner, 
#                                view=viewport, 
#                                mode=mode, **kwargs)
#  elif post_type == 'file':
#    html = FILE_TEMPLATE.render(file=info, 
#                                owner=owner, 
#                                view=viewport, 
#                                mode=mode, **kwargs)
#  else:
#    html = FEED_TEMPLATE.render(feed=info, 
#                                owner=owner, 
#                                view=viewport, 
#                                mode=mode, **kwargs)
#
#  return html



CURRENT_APP.jinja_env.filters['render'] = render






#===============================================================================
# Replace default error pages
#===============================================================================

@CURRENT_APP.errorhandler(500)
def internal_server_error(e):  
  return render_template('500.html'), 500


@CURRENT_APP.errorhandler(400)
def bad_request(e):  
  return render_template('400.html'), 404


@CURRENT_APP.errorhandler(403)
def forbidden(e):  
  return render_template('403.html'), 403


@CURRENT_APP.errorhandler(404)
def page_not_found(e):  
  return render_template('404.html'), 404


@CURRENT_APP.errorhandler(405)
def method_not_allowed(e):  
  return render_template('400.html'), 405
























