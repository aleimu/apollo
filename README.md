<!--
 * @Author: aleimu
 * @Date: 2020-12-11 16:29:14
 * @Description: file content
-->
# apollo

apollo client 使用方式与实例
没有做成pip包,用的话自己复制过去.

# 踩坑

翻了下大部分的apollo client库,发现都是设置了守护线程去长链接拉取服务端的更新, 其他语言一般部署都是独立进程配合多线程使用的, 守护线程更新了_cache后每个线程都能生效, 但是在uwsgi配合python多进程使用时, 因为uwsgi的python服务一般是多进程配合多线程使用,这样会有很多坑需要注意, ,这里记录了大致的使用方式, 注意uwsgi.ini的配置中有两个关键的配置:
```
enable-threads = true   # 必须
lazy-apps = true    # 必须
```

# 参考
 本项目的主要代码是引用了apollo-client-python中的实现,改了里面的一些东西,也在外侧做了浅浅的封装.

 - [其它语言客户端接入指南](https://github.com/ctripcorp/apollo/wiki/%E5%85%B6%E5%AE%83%E8%AF%AD%E8%A8%80%E5%AE%A2%E6%88%B7%E7%AB%AF%E6%8E%A5%E5%85%A5%E6%8C%87%E5%8D%97)
 - [pyapollo](https://github.com/BruceWW/pyapollo)
 - [apollo-client-python](https://github.com/xhrg-product/apollo-client-python)
 - [uWSGI的lazy-apps配置](https://blog.csdn.net/weixin_43262264/article/details/106078784)