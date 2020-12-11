#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
Author: aleimu
Date: 2020-12-09 21:18:07
Description: apollo client

'''

import os
import sys
import json
import time
import traceback
import threading
import logging
import hashlib
import socket
import requests

# 定义常量
CONFIGURATIONS = "configurations"
NOTIFICATION_ID = "notificationId"
NAMESPACE_NAME = "namespaceName"
NAMESPACE = "application"

version = sys.version_info.major

# if version == 2:
#     reload = reload
#
# if version == 3:
#     from importlib import reload

# logging.basicConfig()
logging.basicConfig(format='%(asctime)s,%(msecs)d %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s',
                    datefmt='%d-%m-%Y:%H:%M:%S',
                    level=logging.DEBUG)
logger = logging.getLogger(__name__)
s = requests.session()


class ApolloClient(object):

    # 当做模块的使用的话,不需要单例
    # _instance_lock = threading.Lock()
    #
    # def __new__(cls, *args, **kwargs):
    #     if not hasattr(ApolloClient, "_instance"):
    #         with ApolloClient._instance_lock:
    #             if not hasattr(ApolloClient, "_instance"):
    #                 ApolloClient._instance = object.__new__(cls)
    #     return ApolloClient._instance

    def __init__(self, apo_url, app_id, cluster='default', namespaces=None, secret='', hot_update=True,
                 change_callback=None, filepath=None):

        # 核心路由参数
        self.apo_url = apo_url
        self.cluster = cluster
        self.app_id = app_id
        self._cache = {}
        # namespace合集
        if namespaces:
            self.namespaces = set(namespaces)
        else:
            self.namespaces = set(NAMESPACE)
        # 记录key与namespace的对应关系
        self.maps = {}
        # 检查参数变量
        self._notification_map = {NAMESPACE: -1}
        # 非核心参数
        self.ip = init_ip()
        self.secret = secret
        # 私有控制变量
        self._cycle_time = 2
        self._stopping = False
        self._no_key = {}
        self._hash = {}
        self._pull_timeout = 75  # 要大于60
        self._cache_file_path = os.path.expanduser('~') + '/data/apollo/cache/' \
            if filepath is None else filepath
        self._long_poll_thread = None
        self._change_listener = change_callback  # "add" "delete" "update"
        # 私有启动方法
        self._path_checker()
        if hot_update:
            self._start_hot_update()
        self._init_maps()

    # 分层获取单个配置
    def get_value(self, key, default_val=None, namespace=None):
        if not namespace:
            namespace = self.maps.get(key)
        try:
            # 读取内存配置
            namespace_cache = self._cache.get(namespace)
            val = get_value_from_dict(namespace_cache, key)
            logger.debug("------------get_value---------------0")
            if val is not None:
                return val
            logger.debug("------------get_value---------------1")
            no_key = lack_key(namespace, key)
            if no_key in self._no_key:
                return default_val
            logger.debug("-------------get_value--------------2")
            # 读取网络配置
            data = self.get_json_from_net(namespace)
            val = get_value_from_dict(data, key)
            if val is not None:
                self._update_cache_file(data, namespace)
                return val
            logger.debug("--------------get_value-------------3")
            # 读取文件配置
            namespace_cache = self._get_file(namespace)
            val = get_value_from_dict(namespace_cache, key)
            if val is not None:
                self._update_cache_file(namespace_cache, namespace)
                return val
            logger.debug("-------------get_value--------------4")
            # 如果全部没有获取，则把默认值返回，设置本地缓存为None
            self._set_local_cache_none(namespace, key)
            return default_val
        except Exception as e:
            logger.error("get_value has error, [key is %s], [namespace is %s], [error is %s], ", key, namespace, e)
            return default_val

    # 获取配置
    def get_json_from_net(self, namespace=NAMESPACE):
        """获取远程配置,此方法是带缓存的"""
        url = '{}/configfiles/json/{}/{}/{}?ip={}'.format(self.apo_url, self.app_id, self.cluster, namespace, self.ip)
        try:
            req = s.get(url, timeout=3, headers=self._sign_headers(url))
            if req.status_code == 200:
                data = req.json()
                data = {CONFIGURATIONS: data}
                # if data is not None:
                #     self._update_cache_file(data, namespace)
                return data
            else:
                return None
        except Exception as e:
            logger.warning(str(e))
            return None

    # 停止更新
    def stop(self):
        self._stopping = True
        logger.info("Stopping listener...")

    # 初始化分组
    def _init_maps(self):
        """避免可能会在遍历过程中修改字典"""
        for space in self.namespaces:
            try:
                data = self.get_json_from_net(space)
                if data:
                    data = data.get(CONFIGURATIONS, {})
                for key in data:
                    self.maps[key] = space
            except Exception:
                traceback.print_exc()

    # 设置守护线程,更新配置
    def _start_hot_update(self):
        logger.debug("--------poll_thread----------")
        self._long_poll_thread = threading.Thread(target=self._listener)
        # 启动异步线程为守护线程，主线程推出的时候，守护线程会自动退出。
        self._long_poll_thread.setDaemon(True)
        self._long_poll_thread.start()
        logger.debug("--------poll_thread----------")

    # 调用设置的回调函数，如果异常，直接try掉
    def _call_listener(self, namespace, old_kv, new_kv):
        if self._change_listener is None:
            return
        if old_kv is None:
            old_kv = {}
        if new_kv is None:
            new_kv = {}
        try:
            for key in old_kv:
                new_value = new_kv.get(key)
                old_value = old_kv.get(key)
                if new_value is None:
                    # 如果newValue 是空，则表示key，value被删除了。
                    self._change_listener("delete", namespace, key, old_value)
                    continue
                if new_value != old_value:
                    self._change_listener("update", namespace, key, new_value)
                    continue
            for key in new_kv:
                new_value = new_kv.get(key)
                old_value = old_kv.get(key)
                if old_value is None:
                    self._change_listener("add", namespace, key, new_value)
        except BaseException as e:
            logger.warning(str(e))

    # 更新本地缓存和文件缓存
    def _update_cache_file(self, data, namespace=NAMESPACE):
        logger.debug("update {}'s cache!".format(namespace))
        # 更新本地缓存
        self._cache[namespace] = data
        # 更新文件缓存
        new_string = json.dumps(data)
        new_hash = hashlib.md5(new_string.encode('utf-8')).hexdigest()
        if self._hash.get(namespace) == new_hash:
            pass
        else:
            logger.debug("update {}'s file!".format(namespace))
            cache_path = os.path.join(self._cache_file_path, '%s_configuration_%s.txt' % (self.app_id, namespace))
            with open(cache_path, 'w') as f:
                f.write(new_string)
            self._hash[namespace] = new_hash

    # 从本地文件获取配置
    def _get_file(self, namespace=NAMESPACE):
        cache_path = os.path.join(self._cache_file_path, '%s_configuration_%s.txt' % (self.app_id, namespace))
        if os.path.isfile(cache_path):
            with open(cache_path, 'r') as f:
                result = json.loads(f.readline())
            return result
        return {}

    # 获取网络变更通知
    def _pull_net_notices(self, notices):
        try:
            url = '{}/notifications/v2/'.format(self.apo_url)
            params = {
                'appId': self.app_id,
                'cluster': self.cluster,
                'notifications': json.dumps(notices, ensure_ascii=False)
            }
            req = s.get(url, params=params, timeout=self._pull_timeout, headers=self._sign_headers(url))
            if req.status_code == 304:
                logger.debug('No change, Keep looping')
                return
            if req.status_code == 400:
                logger.debug('notifications error, Keep looping')
                return
            if req.status_code == 200:
                return req.json()
            else:
                logger.warning('Sleep...')
        except Exception as e:
            logger.warning(str(e))

    # 解析变更通知,更新本地
    def _update_by_notices(self, data):
        for entry in data:
            namespace = entry[NAMESPACE_NAME]
            notice_id = entry[NOTIFICATION_ID]
            self._notification_map[namespace] = notice_id
            self.namespaces.add(namespace)
            logger.info("%s has changes: notificationId=%d", namespace, notice_id)
            self._update_local(namespace, notice_id, call_change=True)

    # 更新本地
    def _update_local(self, namespace, n_id, call_change=False):
        data = self.get_json_from_net(namespace)
        data[NOTIFICATION_ID] = n_id
        old_namespace = self._cache.get(namespace)
        self._update_cache_file(data, namespace)
        if self._change_listener is not None and call_change and old_namespace:
            old_kv = old_namespace.get(CONFIGURATIONS)
            new_kv = data.get(CONFIGURATIONS)
            self._call_listener(namespace, old_kv, new_kv)

    # 长连接,检查更新数据
    def _long_poll(self):
        try:
            notices = []
            for key in self._notification_map:
                notification_id = self._notification_map[key]
                notices.append({
                    NAMESPACE_NAME: key,
                    NOTIFICATION_ID: notification_id
                })
            # 如果长度为0直接返回
            if not notices:
                return
            content = self._pull_net_notices(notices)
            if content:
                self._update_by_notices(content)
        except Exception:
            traceback.print_exc()

    # 循环检查
    def _listener(self):
        logger.info('start long_poll')
        while not self._stopping:
            self._long_poll()
            time.sleep(self._cycle_time)
        logger.info("stopped, long_poll")

    # 设置某个namespace的key为none，这里不设置default_val，是为了保证函数调用实时的正确性。假设用户2次default_val不一样，然而这里却用default_val填充，则可能会有问题。
    def _set_local_cache_none(self, namespace, key):
        no_key = lack_key(namespace, key)
        self._no_key[no_key] = key

    # 给header增加加签需求
    def _sign_headers(self, url):
        headers = {}
        if self.secret == '':
            return headers
        uri = url[len(self.apo_url):len(url)]
        time_unix_now = str(int(round(time.time() * 1000)))
        headers['Authorization'] = 'Apollo ' + self.app_id + ':' + signature(time_unix_now, uri, self.secret)
        headers['Timestamp'] = time_unix_now
        return headers

    # 检查路径
    def _path_checker(self):
        if not os.path.isdir(self._cache_file_path):
            if version == 3:
                os.makedirs(self._cache_file_path, exist_ok=True)
            else:
                os.makedirs(self._cache_file_path)


# 对时间戳，uri，秘钥进行加签
def signature(timestamp, uri, secret):
    import hmac
    import base64
    string_to_sign = '' + timestamp + '\n' + uri
    hmac_code = hmac.new(secret.encode(), string_to_sign.encode(), hashlib.sha1).digest()
    return base64.b64encode(hmac_code).decode()


def lack_key(namespace, key):
    return "{}{}{}".format(namespace, len(namespace), key)


# 返回是否获取到的值，不存在则返回None
def get_value_from_dict(namespace_cache, key):
    if namespace_cache:
        kv_data = namespace_cache.get(CONFIGURATIONS)
        return kv_data.get(key, None)
    return None


# 获取当前服务器ip
def init_ip():
    """获取当前服务器ip"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 53))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception as e:
        logger.error(str(e))
        return "127.0.0.1"


# 重载服务
def reload_server(oper, namespace, key, new_value):
    """重载服务"""
    try:
        print('-----------------reload_server----------------------')
        relaod_uwsgi("")
    except Exception:
        traceback.print_exc()


# 重载uwsgi
def relaod_uwsgi(pid_path):
    """选用方案1"""
    print("------------relaod_uwsgi---------------")
    val = os.system('uwsgi --reload {}'.format(pid_path))
    print(val)
    if val:
        print("重启可能遇到了问题...")

# 重载py模块
# def reload_module(name):
#     """选用方案2"""
#     print("------------reload_module---------------")
#     try:
#         reload(name)
#     except Exception:
#         traceback.print_exc()
