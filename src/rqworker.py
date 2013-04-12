#!/usr/bin/env python
#! coding: utf-8
# pylint: disable-msg=W0311

import sys
reload(sys)
sys.setdefaultencoding("utf-8")

  
import api
from rq import Queue, Worker, Connection


with Connection(api.QUEUE):
  q = Queue(sys.argv[1])
  Worker(q).work()