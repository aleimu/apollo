# !/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Author: aleimu
Date: 2020-12-09 21:19:27
Description: 使用示例
"""

from flask import Flask, jsonify, request
from apollo import Config

cf = Config(apo_url="http://127.0.0.1:3000", app_id="app", cluster="dev",
            namespaces={"camel.common", "application"})

print("----------use-----------")
print(cf.SQLALCHEMY_TRACK_MODIFICATIONS)
print(cf.LOG_NAME)
print("----------use-----------")

app = Flask(__name__)


@app.route('/')
def hello_world():
    key = request.values.get('key')
    new = getattr(cf, key)
    print(id(cf.apo))
    return jsonify({'data': new, 'apo': cf.apo.get_value(key), "my": cf.SQLALCHEMY_POOL_SIZE})


application = app  # for uwsgi.ini
if __name__ == "__main__":
    app.run(port=5000)

"""uwsgi.ini 配置
[uwsgi]
module = app
wsgi-file = app.py
master = true
processes = 2
#plugins = python
enable-threads = true   # 必须
lazy-apps = true    # 必须
http = :5000
die-on-term = true
pidfile = ./uwsgi.pid
#stats=127.0.0.1:9090
chdir = /home/app
disable-logging = true
log-maxsize = 50000000
daemonize = /home/app/log.log
"""
