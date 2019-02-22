__author__ = 'powergx'


class RedisConfig():
    def __init__(self, host, port, db, password=None):
        self.host = host
        self.port = port
        self.db = db
        self.password = password


class Config(object):
    DEBUG = False
    TESTING = False
    DATABASE_URI = ''
    ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif'}
    SESSION_TYPE = 'memcached'
#私钥设置，请自行修改该私钥，以免被入侵(请保持所有设备使用同样的Key)
    SECRET_KEY = 'abcdefgh-IJKL-0123-MNOP-QrStUvWxYz45'
#数据库配置。host填数据库IP地址，port为端口号，password为密码(对于密码123456，设置为password='123456')
    REDIS_CONF = RedisConfig(host='127.0.0.1', port=6379, db=0, password=None)
    PASSWORD_PREFIX = "08b3db21-d120-11e4-9ttd-10ddb199c373"
    ENCRYPT_PWD_URL = None
    SERVER_IP = '0.0.0.0'
    SERVER_PORT = 4000
#采集器ID，不同的采集器请指派不同的ID
    COLLECTOR_ID = '采集器1'
#默认采集器设置。未配置从属采集器的账户将会使用该采集器采集数据(请保持仅有一个采集器为True，其它采集器为False)
    DEFAULT_COLLECTOR = True
#故障转移采集器设置。当有采集器出现故障时，其管理的账户自动转移到该采集器下进行数据采集(请保持至多一个采集器为True。)
    BACKUP_COLLECTOR = True
#同时进行在线数据采集的监工账户数量(建议设置1-3之间的数值，并发太高容易封IP)
    ONLINE_PROCESS_NUM = 2
#同时进行离线数据采集的监工账户数量(建议设置1-3之间的数值，并发太高容易封IP)
    OFFLINE_PROCESS_NUM = 1
#最大允许的同时执行的自动任务数量
    MULTIPLE_PROCESS = 1

class ProductionConfig(Config):
    DEBUG = True


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    DEBUG = True
    TESTING = True
