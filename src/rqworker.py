#!/usr/bin/env python
#! coding: utf-8
# pylint: disable-msg=W0311

import sys
reload(sys)
sys.setdefaultencoding("utf-8")

  
import api
from rq import Queue, Worker, Connection
from trello_api import get_notifications_trello

with Connection(api.TASKQUEUE):
  q = Queue(sys.argv[1])
  Worker(q, default_result_ttl=0).work()
  