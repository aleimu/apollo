'''
Author: aleimu
Date: 2020-12-11 16:29:40
Description: 初始化ApolloClient ,项目中直接继承Config,使用Config实例即可
'''
#!/usr/bin/env python
# -*- coding: utf-8 -*-


from .apollo import ApolloClient


class Config(object):
    """配置初始化"""

    def __init__(self, apo_url, app_id, cluster, namespaces, secret="", filepath="config"):
        """
        项目中的config.py文件中使用,继承此Config类
        :param apo_url:apollo服务地址
        :type apo_url:str
        :param app_id:项目id
        :type app_id:str
        :param cluster:集群
        :type cluster:str
        :param namespaces:集群中的应用名
        :type namespaces:set
        :param secret:秘钥
        :type secret:str
        :param filepath:缓存文件路径
        :type filepath:str
        """
        self.apo = ApolloClient(apo_url, app_id, cluster,
                                namespaces=namespaces, change_callback=self.reload,
                                secret=secret, filepath=filepath)  # reload=True,

    def __getattr__(self, item):
        return self.apo.get_value(item)

    # 重载服务的方式,待实现
    def reload(self, oper, namespace, key, new_value):
        """子类自己实现"""
        print("********************reload********************")
