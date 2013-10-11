#! coding: utf-8

import re
from urllib import quote
from urlparse import urlsplit, urlunsplit

TRAILING_PUNCTUATION = ['.', ',', ':', ';', '.)']
WRAPPING_PUNCTUATION = [('(', ')'), ('<', '>'), ('[', ']'), ('&lt;', '&gt;')]

unquoted_percents_re = re.compile(r'%(?![0-9A-Fa-f]{2})')
word_split_re = re.compile(r'(\s+)')
simple_url_re = re.compile(r'^https?://\[?\w', re.IGNORECASE)
simple_url_2_re = re.compile(r'^www\.|^(?!http)\w[^@]+\.(com|edu|gov|int|mil|net|org)$', re.IGNORECASE)



def smart_urlquote(url):
  "Quotes a URL if it isn't already quoted."
  # Handle IDN before quoting.
  try:
    scheme, netloc, path, query, fragment = urlsplit(url)
    try:
      netloc = netloc.encode('idna').decode('ascii') # IDN -> ACE
    except UnicodeError: # invalid domain part
      pass
    else:
      url = urlunsplit((scheme, netloc, path, query, fragment))
  except ValueError:
    # invalid IPv6 URL (normally square brackets in hostname part).
    pass

  # An URL is considered unquoted if it contains no % characters or
  # contains a % not followed by two hexadecimal digits. See #9655.
  if '%' not in url or unquoted_percents_re.search(url):
    # See http://bugs.python.org/issue2637
    url = quote(url, safe=b'!*\'();:@&=+$,/?#[]~')

  return url

def extract_urls(text):
  """
  Works on http://, https://, www. links, and also on links ending in one of
  the original seven gTLDs (.com, .edu, .gov, .int, .mil, .net, and .org).
  Links can have trailing punctuation (periods, commas, close-parens) and
  leading punctuation (opening parens) and it'll still do the right thing.
  """
  words = word_split_re.split(text)
  urls = []
  for i, word in enumerate(words):
    if '.' in word or ':' in word:
      # Deal with punctuation.
      lead, middle, trail = '', word, ''
      for punctuation in TRAILING_PUNCTUATION:
        if middle.endswith(punctuation):
          middle = middle[:-len(punctuation)]
          trail = punctuation + trail
      for opening, closing in WRAPPING_PUNCTUATION:
        if middle.startswith(opening):
          middle = middle[len(opening):]
          lead = lead + opening
        # Keep parentheses at the end only if they're balanced.
        if (middle.endswith(closing)
          and middle.count(closing) == middle.count(opening) + 1):
          middle = middle[:-len(closing)]
          trail = closing + trail

      if ">" in middle:
        middle = middle[0:middle.find(">")]

      if simple_url_re.match(middle) or simple_url_2_re.match(middle):
        urls.append(smart_urlquote(middle))

  return urls
      

  
  
  
  
  