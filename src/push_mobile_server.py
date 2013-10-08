# -*- coding: utf-8 -*-
import sys
import argparse
 
import tornado.ioloop
import tornado.web
import sockjs.tornado
import toredis

# https://github.com/mrjoes/sockjs-tornado
# https://gist.github.com/mrjoes/3284402 
# redis-cli publish "asdf"
# Our sockjs connection class.
# sockjs-tornado will create new instance for every connected client.
class BrokerConnection(sockjs.tornado.SockJSConnection):
  
  clients = set()
  
  def on_open(self, info):
    logging.info('Incoming client from %s' % info.ip)
    self.clients.add(self)
  
  def on_message(self, message):
    logging.debug('Received something from client: %s', message)
  
  def on_close(self):
    self.clients.remove(self)
  
  @classmethod
  def pubsub(cls, data):
    msg_type, msg_chan, msg = data
    if msg_type == 'message':
      logging.debug('Pushing: %s' % msg)
      for c in cls.clients:
        c.send(msg)
 
 
if __name__ == "__main__":
  # Logging
  import logging
  logging.getLogger().setLevel(logging.DEBUG)
  
  # Parse options. TODO: Use decent option parsing library.
  parser = argparse.ArgumentParser()
  parser.add_argument('--endpoint',
                      default='/push', dest='endpoint',
                      help='SockJS URL endpoint')
  parser.add_argument('--port',
                      type=int, default=8091, dest='port',
                      help='SockJS server port')
  parser.add_argument('--key',
                      default='push', dest='key',
                      help='Redis key')
  parser.add_argument('--redis_server',
                      default='localhost', dest='redis_server',
                      help='Redis host')
  parser.add_argument('--redis_port',
                      default=6379, dest='redis_port',
                      help='Redis port')
  v = parser.parse_args()
  # Initialize tornado-redis and subscribe to key
  rclient = toredis.Client()
  rclient.connect(v.redis_server, v.redis_port)
  rclient.subscribe(v.key, BrokerConnection.pubsub)
 
  # Initialize sockjs-tornado and start IOLoop
  BrokerRouter = sockjs.tornado.SockJSRouter(BrokerConnection, v.endpoint)
  
  app = tornado.web.Application(BrokerRouter.urls)
  app.listen(v.port)
  
  logging.info('Listening on port %d for redis key %s', v.port, v.key)
  
  tornado.ioloop.IOLoop.instance().start()
