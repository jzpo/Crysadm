__author__ = 'powergx'
from flask import Flask,render_template
import config, socket, redis
import time
import random
from login import login
from datetime import datetime, timedelta
from multiprocessing import Process
from multiprocessing.dummy import Pool as ThreadPool
import threading


conf = None
if socket.gethostname() == 'GXMBP.local':
    conf = config.DevelopmentConfig
elif socket.gethostname() == 'iZ23bo17lpkZ':
    conf = config.ProductionConfig
else:
    conf = config.TestingConfig

redis_conf = conf.REDIS_CONF
pool = redis.ConnectionPool(host=redis_conf.host, port=redis_conf.port, db=redis_conf.db, password=redis_conf.password)
r_session = redis.Redis(connection_pool=pool)

collector_id = conf.COLLECTOR_ID
default_collector = conf.DEFAULT_COLLECTOR
backup_collector = conf.BACKUP_COLLECTOR
online_process_num = conf.ONLINE_PROCESS_NUM
offline_process_num = conf.OFFLINE_PROCESS_NUM
multiple_process = conf.MULTIPLE_PROCESS
collector_alive = set()
from api import *

# 获取用户数据
def get_data(username):
    print(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'get_data')

    start_time = datetime.now()
    try:
        account_data_list=[]
        for user_id in r_session.smembers('accounts:%s' % username):
            time.sleep(1)
            account_key = 'account:%s:%s' % (username, user_id.decode('utf-8'))
            account_info = json.loads(r_session.get(account_key).decode('utf-8'))

            if not account_info.get('active'): continue
            print("start get_data with userID:", user_id)

            this_speed = 0
            session_id = account_info.get('session_id')
            user_id = account_info.get('user_id')
            cookies = dict(sessionid=session_id, userid=str(user_id))

            mine_info = get_mine_info(cookies)
            if is_api_error(mine_info):
                print('get_data:', user_id, mine_info, 'error')
                return

            if mine_info.get('r') != 0:

                success, account_info = __relogin(account_info.get('account_name'), account_info.get('password'), account_info, account_key)
                if not success:
                    print('get_data:', user_id, 'relogin failed')
                    continue
                session_id = account_info.get('session_id')
                user_id = account_info.get('user_id')
                cookies = dict(sessionid=session_id, userid=str(user_id))
                mine_info = get_mine_info(cookies)

            if mine_info.get('r') != 0:
                print('get_data:', user_id, mine_info, 'error')
                continue

            device_info = ubus_cd(session_id, user_id, ["server", "get_devices", {}])
            #print("Print Device_info:", device_info)
            red_zqb = device_info['result'][1]

            account_data_key = account_key + ':data'
            exist_account_data = r_session.get(account_data_key)
            #print("1",exist_account_data)
            if exist_account_data is None:
                account_data = dict()
                account_data['privilege'] = get_privilege(cookies)
            else:
                account_data = json.loads(exist_account_data.decode('utf-8'))
            ioi_update_key = 'ioi_update:%s:%s' % (username, user_id)
            if r_session.get(ioi_update_key) is not None:
                time.sleep(1)
                balance_log = get_balance_log(cookies)
                if balance_log.get('r') == 0 and 'ioi' in balance_log.keys():
                    account_data['ioi'] = balance_log['ioi']
                    r_session.delete(ioi_update_key)

            account_data['device_info'] = red_zqb.get('devices')

            #新速度统计
            this_speed = 0
            for device in account_data.get('device_info'):
                #print("2",device)
                if account_data.get('zqb_speed_stat') is None:
                    account_data['zqb_speed_stat'] = [0] * 24
                #print(device.get('dcdn_upload_speed'))
                this_speed += int(int(device.get('dcdn_upload_speed')) / 1024)

                if account_data.get('updated_time') is not None:
                    last_updated_time = datetime.strptime(account_data.get('updated_time'), '%Y-%m-%d %H:%M:%S')
                    if last_updated_time.hour == datetime.now().hour:
                        if account_data.get('zqb_speed_stat')[23] != 0:
                            this_speed = int((this_speed + account_data.get('zqb_speed_stat')[23] / 8) / 2) # 计算平均值
                        account_data.get('zqb_speed_stat')[23] = this_speed * 8
                        #account_data['zqb_speed_stat'] = get_speed_stat(cookies)
                    else:
                        del account_data['zqb_speed_stat'][0]
                        account_data.get('zqb_speed_stat').append(this_speed * 8)
                else:
                    del account_data['zqb_speed_stat'][0]
                    account_data.get('zqb_speed_stat').append(this_speed * 8)
                    #account_data['zqb_speed_stat'] = get_speed_stat(cookies)
            #新速度统计
			
            account_data['income'] = get_balance_info(cookies)
            account_data['produce_info'] = get_produce_stat(cookies)
            account_data['updated_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            account_data['mine_info'] = mine_info
            if is_api_error(account_data.get('income')):
                print('get_data:', user_id, 'income', 'error')
                return

            r_session.set(account_data_key, json.dumps(account_data))
            account_data_list.append(account_data)
            if not r_session.exists('can_drawcash'):
                r = get_can_drawcash(cookies=cookies)
                if r.get('r') == 0:
                    r_session.setex('can_drawcash', 60, r.get('is_tm'))

        if start_time.day == datetime.now().day:
            save_history(username,account_data_list)

        r_session.setex('user:%s:cron_queued' % username, 60, '1')
        print(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), username.encode('utf-8'), 'successed')

    except Exception as ex:
        print(username.encode('utf-8'), 'failed', datetime.now().strftime('%Y-%m-%d %H:%M:%S'), ex)


# 保存历史数据
def save_history(username,account_data_list):
    from user import get_id_map
    from user import get_mid_to_uid
    from user import account_log
    print(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'save_history')
    str_today = datetime.now().strftime('%Y-%m-%d')
    key = 'user_data:%s:%s' % (username, str_today)
    b_today_data = r_session.get(key)
    today_data = dict()

    if b_today_data is not None:
        today_data = json.loads(b_today_data.decode('utf-8'))

    today_data['updated_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    today_data['pdc'] = 0
    today_data['last_speed'] = 0
    today_data['deploy_speed'] = 0
    today_data['uncollect'] = 0
    today_data['balance'] = 0
    today_data['income'] = 0
    today_data['speed_stat'] = list()
    today_data['pdc_detail'] = []
    today_data['produce_stat'] = [] 
    today_data['ioi_all'] = [] 
    if 'award_income' not in today_data.keys():
        today_data['award_income'] = 0
    award_income = 0

    # 获取账号所有数据
    for data in account_data_list:
        if datetime.strptime(data.get('updated_time'), '%Y-%m-%d %H:%M:%S').day != datetime.now().day:
            continue
        today_data.get('speed_stat').append(dict(mid=data.get('privilege').get('mid'),dev_speed=data.get('zqb_speed_stat') if data.get('zqb_speed_stat') is not None else [0] * 24))
        this_pdc = data.get('mine_info').get('dev_m').get('pdc')

        today_data['pdc'] += this_pdc
        today_data.get('pdc_detail').append(dict(mid=data.get('privilege').get('mid'), pdc=this_pdc))
        today_data['uncollect'] += data.get('mine_info').get('td_not_in_a')
        today_data['balance'] += data.get('income').get('r_can_use')
        today_data['income'] += data.get('income').get('r_h_a')
        today_data.get('produce_stat').append(dict(mid=data.get('privilege').get('mid'),phone=data.get('privilege').get('phone'), hourly_list=data.get('produce_info').get('hourly_list')))
        if 'ioi' in data.keys():
            today_data['ioi_all'].append(data['ioi'])
            for ioi in data['ioi']:
                if 'cn' in ioi.keys() and 'ct' in ioi.keys() and time.localtime(ioi['ct']).tm_mday == datetime.now().day:
                    if ioi['cn'].find('宝箱') != -1 or ioi['cn'].find('转盘') != -1:
                        award_income += ioi['c']
        if today_data['award_income'] < award_income:
            today_data['award_income'] = award_income
        for device in data.get('device_info'):
            today_data['last_speed'] += int(int(device.get('dcdn_upload_speed')) / 1024)
            today_data['deploy_speed'] += int(device.get('dcdn_download_speed') / 1024)
    today_data['pdc'] += today_data['award_income'] 
    r_session.setex(key, 3600 * 24 * 35, json.dumps(today_data))

    extra_info_key='extra_info:%s' % (username)
    b_extra_info=r_session.get(extra_info_key)
    if b_extra_info is None:
        extra_info={}
    else:
        extra_info=json.loads(b_extra_info.decode('utf-8'))
    if 'last_adjust_date' not in extra_info.keys():
        extra_info['last_adjust_date'] = '1997-1-1 1:1:1'
    if datetime.now().hour >= 1 and datetime.now().hour < 20 and datetime.strptime(extra_info['last_adjust_date'],'%Y-%m-%d %H:%M:%S').day != datetime.now().day:
        str_yesterday = (datetime.now() + timedelta(days=-1)).strftime('%Y-%m-%d')
        yesterday_key = 'user_data:%s:%s' % (username, str_yesterday)
        b_yesterday_data = r_session.get(yesterday_key)
        if b_yesterday_data is None: return
        yesterday_data = json.loads(b_yesterday_data.decode('utf-8'))
        id_map=get_id_map(username)
        mid_to_uid=get_mid_to_uid(username)
        if 'produce_stat' in yesterday_data.keys():
            td_produce={}
            for td_stat in today_data['produce_stat']:
                td_produce[td_stat['mid']]=td_stat['hourly_list']
            detail_adjust_dict={}
            yesterday_data['pdc'] = 0
            for stat in yesterday_data['produce_stat']:
                if stat['mid'] in td_produce.keys():
                    stat['hourly_list'][24] = td_produce[stat['mid']][23-datetime.strptime(today_data['updated_time'],'%Y-%m-%d %H:%M:%S').hour]
                    stat['hourly_list'][23] = td_produce[stat['mid']][22-datetime.strptime(today_data['updated_time'],'%Y-%m-%d %H:%M:%S').hour]
                    stat['hourly_list'][0] = 0
                    stat['display_name']=id_map.get(mid_to_uid.get(str(stat['mid'])))
                    detail_adjust_dict[stat['mid']] = sum(stat['hourly_list'])
                yesterday_data['pdc'] += detail_adjust_dict[stat['mid']]
            a_income = 0
            for data in today_data['ioi_all']:
                for ioi in data:
                    if 'cn' in ioi.keys() and 'ct' in ioi.keys() and time.localtime(ioi['ct']).tm_mday == (datetime.now() + timedelta(days=-1)).day:
                        if ioi['cn'].find('宝箱') != -1 or ioi['cn'].find('转盘') != -1:
                            a_income += ioi['c']
            if a_income > yesterday_data['award_income']:
                yesterday_data['pdc'] += a_income
                yesterday_data['award_income'] = a_income
            else:
                yesterday_data['pdc'] += yesterday_data['award_income']
            pdc_detail=[]
            if 'pdc_detail' in yesterday_data.keys():
                for pdc_info in yesterday_data['pdc_detail']:
                    if pdc_info['mid'] in detail_adjust_dict.keys():
                        pdc_detail.append(dict(mid=pdc_info['mid'], pdc=detail_adjust_dict[pdc_info['mid']]))
                    else:
                        pdc_detail.append(pdc_info)
                yesterday_data['pdc_detail'] = pdc_detail
        user_key = '%s:%s' % ('user', username)
        user_info = json.loads(r_session.get(user_key).decode('utf-8'))
        if 'total_account_point' in user_info.keys():
            user_info['total_account_point'] -= user_info['max_account_no']
            account_log(user_info.get('username'),'每日收费','消费','扣除:%d 结余:%d' % (user_info['max_account_no'],user_info['total_account_point']))
            accounts_key = 'accounts:%s' % user_info.get('username')
            account_no = r_session.scard(accounts_key)
            if account_no == 0:
                account_no = 1
            user_info['max_account_no'] = account_no
            if account_no > 0:
                days=int(user_info.get('total_account_point')/account_no)
                if days<36500:
                    user_info['expire_date'] = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
                else:
                    user_info['expire_date'] = (datetime.now() + timedelta(days=36500)).strftime('%Y-%m-%d')
            r_session.set(user_key,json.dumps(user_info))
        r_session.setex(yesterday_key, 3600 * 24 * 34, json.dumps(yesterday_data))
        extra_info['last_adjust_date']=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        r_session.set(extra_info_key,json.dumps(extra_info))

# 重新登录
def __relogin(username, password, account_info, account_key):
    print(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), username.encode('utf-8'), 'relogin')
    login_result = login(username, password, conf.ENCRYPT_PWD_URL)

    if login_result.get('errorCode') != 0:
        account_info['status'] = login_result.get('errorDesc')
        account_info['active'] = False
        r_session.set(account_key, json.dumps(account_info))
        return False, account_info

    account_info['session_id'] = login_result.get('sessionID')
    account_info['status'] = 'OK'
    r_session.set(account_key, json.dumps(account_info))
    return True, account_info

# 获取在线用户数据
def get_online_user_data():
    print(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'get_online_user_data')
    if r_session.exists('api_error_info'): return

    pool = ThreadPool(processes=online_process_num)
    users = r_session.smembers('global:online.users')
    username_list=[]
    for u in users:
        user_key = '%s:%s' % ('user', u.decode('utf-8'))
        user_info = json.loads(r_session.get(user_key).decode('utf-8'))
        if 'collector' in user_info.keys():
            if user_info['collector'] == collector_id or (user_info['collector'] not in collector_alive and backup_collector):
                username_list.append(user_info.get('username'))
            else:
                print('auto skip:',user_info.get('username'))                
        elif default_collector:
            username_list.append(user_info.get('username'))
        else:
            print('auto skip:',user_info.get('username'))

    pool.map(get_data, (u for u in username_list))
    pool.close()
    pool.join()

# 获取离线用户数据
def get_offline_user_data():
    print(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'get_offline_user_data')
    if r_session.exists('api_error_info'): return

    offline_users = []
    for b_user in r_session.mget(*['user:%s' % name.decode('utf-8') for name in r_session.sdiff('users', *r_session.smembers('global:online.users'))]):
        user_info = json.loads(b_user.decode('utf-8'))
        username = user_info.get('username')
        if not user_info.get('active'): continue
        if 'collector' not in user_info.keys():
            if not default_collector:
                print('auto skip:',user_info.get('username'))
                continue
        elif user_info['collector'] != collector_id and (not backup_collector or user_info['collector'] in collector_alive):
            print('auto skip:',user_info.get('username'))
            continue

        every_hour_key = 'user:%s:cron_queued' % username   #1分钟内刷新过一次则自动取消本次刷新
        if r_session.exists(every_hour_key): continue

        offline_users.append(username)

    pool = ThreadPool(processes=offline_process_num)

    pool.map(get_data, offline_users)
    pool.close()
    pool.join()

# 从在线用户列表中清除离线用户
def clear_offline_user():
    print(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'clear_offline_user')
    for b_username in r_session.smembers('global:online.users'):
        username = b_username.decode('utf-8')
        if not r_session.exists('user:%s:is_online' % username):
            r_session.srem('global:online.users', username)

# 刷新选择自动任务的用户
def select_auto_task_user():
    from admin import del_user
    print(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'select_auto_task_user')
    auto_collect_accounts = []
    auto_drawcash_accounts = []
    auto_giftbox_accounts = []
    auto_searcht_accounts = []
    auto_revenge_accounts = []
    auto_getaward_accounts = []
    auto_detect_accounts = []
    auto_report_accounts = []
    config_key = '%s:%s' % ('user', 'system')
    config_info = json.loads(r_session.get(config_key).decode('utf-8'))
    if 'trial_period' not in config_info.keys():
        config_info['trial_period'] = 14
    for b_user in r_session.mget(*['user:%s' % name.decode('utf-8') for name in r_session.smembers('users')]):
        user_info = json.loads(b_user.decode('utf-8'))
        if not user_info.get('active'):
            if 'expire_date' not in user_info.keys():
                user_info['expire_date'] = (datetime.now() + timedelta(days=-1)).strftime('%Y-%m-%d')
                r_session.set('user:%s' % user_info.get('username'), json.dumps(user_info))
            elif False and datetime.strptime(user_info['expire_date'],'%Y-%m-%d').date() < (datetime.now()+timedelta(days=-7)).date():
                del_user(user_info.get('username'))
            continue
        if 'is_admin' not in user_info.keys() or not user_info['is_admin']:
            if user_info['total_account_point'] <= 0:
                user_info['active'] = False
                r_session.set('user:%s' % user_info.get('username'), json.dumps(user_info))
        username = user_info.get('username')
        account_keys = ['account:%s:%s' % (username, user_id.decode('utf-8')) for user_id in r_session.smembers('accounts:%s' % username)]
        if len(account_keys) == 0: continue
        for b_account in r_session.mget(*account_keys):
            account_info = json.loads(b_account.decode('utf-8'))
            if not (account_info.get('active')): continue
            session_id = account_info.get('session_id')
            user_id = account_info.get('user_id')
            cookies = json.dumps(dict(sessionid=session_id, userid=user_id, user_info=user_info))
            if user_info.get('auto_collect'): auto_collect_accounts.append(cookies)
            if user_info.get('auto_drawcash'): auto_drawcash_accounts.append(cookies)
            if user_info.get('auto_giftbox'): auto_giftbox_accounts.append(cookies)
            if user_info.get('auto_searcht'): auto_searcht_accounts.append(cookies)
            if user_info.get('auto_revenge'): auto_revenge_accounts.append(cookies)
            if user_info.get('auto_getaward'): auto_getaward_accounts.append(cookies)
            if user_info.get('auto_detect'): auto_detect_accounts.append(cookies)
            if user_info.get('auto_report'): auto_report_accounts.append(cookies)
    r_session.delete('global:auto.collect.cookies')
    if len(auto_collect_accounts) != 0:
        r_session.sadd('global:auto.collect.cookies', *auto_collect_accounts)
    r_session.delete('global:auto.drawcash.cookies')
    if len(auto_drawcash_accounts) != 0:
        r_session.sadd('global:auto.drawcash.cookies', *auto_drawcash_accounts)
    r_session.delete('global:auto.giftbox.cookies')
    if len(auto_giftbox_accounts) != 0:
        r_session.sadd('global:auto.giftbox.cookies', *auto_giftbox_accounts)
    r_session.delete('global:auto.searcht.cookies')
    if len(auto_searcht_accounts) != 0:
        r_session.sadd('global:auto.searcht.cookies', *auto_searcht_accounts)
    r_session.delete('global:auto.revenge.cookies')
    if len(auto_revenge_accounts) != 0:
        r_session.sadd('global:auto.revenge.cookies', *auto_revenge_accounts)
    r_session.delete('global:auto.getaward.cookies')
    if len(auto_getaward_accounts) != 0:
        r_session.sadd('global:auto.getaward.cookies', *auto_getaward_accounts)
    r_session.delete('global:auto.detect.cookies')
    if len(auto_detect_accounts) != 0:
        r_session.sadd('global:auto.detect.cookies', *auto_detect_accounts)
    r_session.delete('global:auto.report.cookies')
    if len(auto_report_accounts) != 0:
        r_session.sadd('global:auto.report.cookies', *auto_report_accounts)

# 执行检测收益报告函数
def check_report(user, cookies, user_info):
    from mailsand import validateEmail
    config_key = '%s:%s' % ('user', 'system')
    r_config_info = r_session.get(config_key)
    if r_config_info is not None:
        config_info = json.loads(r_config_info.decode('utf-8'))

    print(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'check_report')
    extra_info_key='extra_info:%s' % (user_info.get('username'))
    b_extra_info=r_session.get(extra_info_key)
    if b_extra_info is None:
        extra_info={}
    else:
        extra_info=json.loads(b_extra_info.decode('utf-8'))
    if 'last_adjust_date' not in extra_info.keys() or datetime.strptime(extra_info['last_adjust_date'],'%Y-%m-%d %H:%M:%S').day != datetime.now().day:
        return
    if 'last_report_date' not in extra_info.keys():
        extra_info['last_report_date'] = '1997-1-1 1:1:1'
    if datetime.strptime(extra_info['last_report_date'],'%Y-%m-%d %H:%M:%S').day == datetime.now().day: return
    str_yesterday = (datetime.now() + timedelta(days=-1)).strftime('%Y-%m-%d')
    yesterday_key = 'user_data:%s:%s' % (user_info.get('username'), str_yesterday)
    b_yesterday_data = r_session.get(yesterday_key)
    if b_yesterday_data is None: return
    yesterday_data = json.loads(b_yesterday_data.decode('utf-8'))
    if 'produce_stat' in yesterday_data.keys():
        if validateEmail(user_info['email']) != 1: return
        mail = dict()
        mail['to'] = user_info['email']
        mail['subject'] = '云监工-收益报告(PS:请将该邮箱添加到联系人)'
        mail['text'] = """
<DIV style="BACKGROUND-COLOR: #e6eae9">
    <TABLE style="WIDTH: 100%; COLOR: #4f6b72; PADDING-BOTTOM: 0px; PADDING-TOP: 0px; PADDING-LEFT: 0px; MARGIN: 0px; PADDING-RIGHT: 0px" cellSpacing=0 summary="The technical specifications of the Apple PowerMac G5 series">
        <CAPTION style="WIDTH: 700px; PADDING-BOTTOM: 5px; TEXT-ALIGN: center; PADDING-TOP: 0px; FONT: italic 11px 'Trebuchet MS', Verdana, Arial, Helvetica, sans-serif; PADDING-LEFT: 0px; PADDING-RIGHT: 0px">
            """ + str_yesterday + """　收益报告
        </CAPTION>
        <TBODY>
            <TR>
                <TH style="BORDER-LEFT-WIDTH: 0px; BORDER-RIGHT: #c1dad7 1px solid; BACKGROUND: none transparent scroll repeat 0% 0%; BORDER-BOTTOM: #c1dad7 1px solid; TEXT-TRANSFORM: uppercase; COLOR: #4f6b72; PADDING-BOTTOM: 6px; TEXT-ALIGN: left; PADDING-TOP: 6px; FONT: bold 11px 'Trebuchet MS', Verdana, Arial, Helvetica, sans-serif; PADDING-LEFT: 12px; LETTER-SPACING: 2px; PADDING-RIGHT: 6px; BORDER-TOP-WIDTH: 0px" scope=col>
                    显示名
                </TH>
                <TH style="BORDER-TOP: #c1dad7 1px solid; BORDER-RIGHT: #c1dad7 1px solid; BACKGROUND: #cae8ea; BORDER-BOTTOM: #c1dad7 1px solid; TEXT-TRANSFORM: uppercase; COLOR: #4f6b72; PADDING-BOTTOM: 6px; TEXT-ALIGN: left; PADDING-TOP: 6px; FONT: bold 11px 'Trebuchet MS', Verdana, Arial, Helvetica, sans-serif; PADDING-LEFT: 12px; LETTER-SPACING: 2px; PADDING-RIGHT: 6px" scope=col>
                    平均速度(KB/S)
                </TH>
                <TH style="BORDER-TOP: #c1dad7 1px solid; BORDER-RIGHT: #c1dad7 1px solid; BACKGROUND: #cae8ea; BORDER-BOTTOM: #c1dad7 1px solid; TEXT-TRANSFORM: uppercase; COLOR: #4f6b72; PADDING-BOTTOM: 6px; TEXT-ALIGN: left; PADDING-TOP: 6px; FONT: bold 11px 'Trebuchet MS', Verdana, Arial, Helvetica, sans-serif; PADDING-LEFT: 12px; LETTER-SPACING: 2px; PADDING-RIGHT: 6px" scope=col>
                    上传估量(GB)
                </TH>
                <TH style="BORDER-TOP: #c1dad7 1px solid; BORDER-RIGHT: #c1dad7 1px solid; BACKGROUND: #cae8ea; BORDER-BOTTOM: #c1dad7 1px solid; TEXT-TRANSFORM: uppercase; COLOR: #4f6b72; PADDING-BOTTOM: 6px; TEXT-ALIGN: left; PADDING-TOP: 6px; FONT: bold 11px 'Trebuchet MS', Verdana, Arial, Helvetica, sans-serif; PADDING-LEFT: 12px; LETTER-SPACING: 2px; PADDING-RIGHT: 6px" scope=col>
                    今日收益(￥)
                </TH>
            </TR>
    """
        td_speed={}
        td_produce={}
        s_sum=0
        p_sum=0
        for stat in yesterday_data['speed_stat']:
            s=0
            for i in range(0,24):
               s+=stat['dev_speed'][i]
            td_speed[stat['mid']]=s/24/8
            s_sum+=td_speed[stat['mid']]
        for j,stat in enumerate(yesterday_data['produce_stat']):
            s=0
            for i in range(1,25):
               s+=stat['hourly_list'][i]
            td_produce[stat['mid']]=s/10000
            p_sum+=td_produce[stat['mid']]
            if 'display_name' not in stat.keys() or stat['display_name'] is None or stat['display_name'] == '未配置':
                stat['display_name'] = stat.get('phone')
            if stat['display_name'] is None:
                stat['display_name']='未配置'
            if j % 2 == 0:
                mail['text']=mail['text'] + """
            <TR>
                <TH style="BORDER-RIGHT: #c1dad7 1px solid; BACKGROUND: #fff; BORDER-BOTTOM: #c1dad7 1px solid; TEXT-TRANSFORM: uppercase; COLOR: #4f6b72; PADDING-BOTTOM: 6px; TEXT-ALIGN: left; PADDING-TOP: 6px; FONT: bold 10px 'Trebuchet MS', Verdana, Arial, Helvetica, sans-serif; PADDING-LEFT: 12px; BORDER-LEFT: #c1dad7 1px solid; LETTER-SPACING: 2px; PADDING-RIGHT: 6px; BORDER-TOP-WIDTH: 0px" scope=row>
                    """ + ('%s' % (stat['display_name'])) + """
                </TH>
                <TD style="FONT-SIZE: 11px; BORDER-RIGHT: #c1dad7 1px solid; BACKGROUND: #fff; BORDER-BOTTOM: #c1dad7 1px solid; COLOR: #4f6b72; PADDING-BOTTOM: 6px; PADDING-TOP: 6px; PADDING-LEFT: 12px; PADDING-RIGHT: 6px">
                    """ + ('%.1f' % (td_speed[stat['mid']])) + """
                </TD>
                <TD style="FONT-SIZE: 11px; BORDER-RIGHT: #c1dad7 1px solid; BACKGROUND: #fff; BORDER-BOTTOM: #c1dad7 1px solid; COLOR: #4f6b72; PADDING-BOTTOM: 6px; PADDING-TOP: 6px; PADDING-LEFT: 12px; PADDING-RIGHT: 6px">
                    """ + ('%.1f' % (td_speed[stat['mid']]*86400/1024/1024)) + """
                </TD>
                <TD style="FONT-SIZE: 11px; BORDER-RIGHT: #c1dad7 1px solid; BACKGROUND: #fff; BORDER-BOTTOM: #c1dad7 1px solid; COLOR: #4f6b72; PADDING-BOTTOM: 6px; PADDING-TOP: 6px; PADDING-LEFT: 12px; PADDING-RIGHT: 6px">
                    """ + ('%.2f' % (td_produce[stat['mid']])) + """
                </TD>
            </TR>
    """
            else:
                mail['text']=mail['text'] + """
                <TH style="BORDER-RIGHT: #c1dad7 1px solid; BACKGROUND: #f5fafa; BORDER-BOTTOM: #c1dad7 1px solid; TEXT-TRANSFORM: uppercase; COLOR: #797268; PADDING-BOTTOM: 6px; TEXT-ALIGN: left; PADDING-TOP: 6px; FONT: bold 10px 'Trebuchet MS', Verdana, Arial, Helvetica, sans-serif; PADDING-LEFT: 12px; BORDER-LEFT: #c1dad7 1px solid; LETTER-SPACING: 2px; PADDING-RIGHT: 6px; BORDER-TOP-WIDTH: 0px" scope=row>
                    """ + ('%s' % (stat['display_name'])) + """
                </TH>
                <TD style="FONT-SIZE: 11px; BORDER-RIGHT: #c1dad7 1px solid; BACKGROUND: #f5fafa; BORDER-BOTTOM: #c1dad7 1px solid; COLOR: #797268; PADDING-BOTTOM: 6px; PADDING-TOP: 6px; PADDING-LEFT: 12px; PADDING-RIGHT: 6px">
                    """ + ('%.1f' % (td_speed[stat['mid']])) + """
                </TD>
                <TD style="FONT-SIZE: 11px; BORDER-RIGHT: #c1dad7 1px solid; BACKGROUND: #f5fafa; BORDER-BOTTOM: #c1dad7 1px solid; COLOR: #797268; PADDING-BOTTOM: 6px; PADDING-TOP: 6px; PADDING-LEFT: 12px; PADDING-RIGHT: 6px">
                    """ + ('%.1f' % (td_speed[stat['mid']]*86400/1024/1024)) + """
                </TD>
                <TD style="FONT-SIZE: 11px; BORDER-RIGHT: #c1dad7 1px solid; BACKGROUND: #f5fafa; BORDER-BOTTOM: #c1dad7 1px solid; COLOR: #797268; PADDING-BOTTOM: 6px; PADDING-TOP: 6px; PADDING-LEFT: 12px; PADDING-RIGHT: 6px">
                    """ + ('%.2f' % (td_produce[stat['mid']])) + """
                </TD>
            </TR>
    """
        mail['text']=mail['text'] + """
            <TR>
                <TH style="BORDER-LEFT-WIDTH: 0px; BORDER-RIGHT: #c1dad7 1px solid; BACKGROUND: none transparent scroll repeat 0% 0%; TEXT-TRANSFORM: uppercase; COLOR: #4f6b72; PADDING-BOTTOM: 6px; TEXT-ALIGN: left; PADDING-TOP: 6px; FONT: bold 11px 'Trebuchet MS', Verdana, Arial, Helvetica, sans-serif; PADDING-LEFT: 12px; LETTER-SPACING: 2px; PADDING-RIGHT: 6px; BORDER-TOP-WIDTH: 0px" scope=col>
                    总计
                </TH>
                <TD style="FONT-SIZE: 11px; BORDER-RIGHT: #c1dad7 1px solid; BACKGROUND: none transparent scroll repeat 0% 0%; COLOR: #4f6b72; PADDING-BOTTOM: 6px; PADDING-TOP: 6px; PADDING-LEFT: 12px; PADDING-RIGHT: 6px">
                    """ + ('%.1f' % (s_sum)) + """
                </TD>
                <TD style="FONT-SIZE: 11px; BORDER-RIGHT: #c1dad7 1px solid; BACKGROUND: none transparent scroll repeat 0% 0%; COLOR: #4f6b72; PADDING-BOTTOM: 6px; PADDING-TOP: 6px; PADDING-LEFT: 12px; PADDING-RIGHT: 6px">
                    """ + ('%.1f' % (s_sum*86400/1024/1024)) + """
                </TD>
                <TD style="FONT-SIZE: 11px; BORDER-RIGHT: #c1dad7 1px solid; BACKGROUND: none transparent scroll repeat 0% 0%; COLOR: #4f6b72; PADDING-BOTTOM: 6px; PADDING-TOP: 6px; PADDING-LEFT: 12px; PADDING-RIGHT: 6px">
                    """ + ('%.2f' % (p_sum)) + """
                </TD>
            </TR>
        </TBODY>
        <TFOOT style="FONT-SIZE: 11px; BACKGROUND: none transparent scroll repeat 0% 0%">
            <TR>
                <TD colSpan=4 align=right>
                """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """
                </TD>
            </TR>
        </TFOOT>
    </TABLE>
</DIV>
    """
        json_mail=json.dumps(mail)
        r_session.rpush('mail_queue',json_mail)
        extra_info['last_report_date']=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        r_session.set(extra_info_key,json.dumps(extra_info))
        r_session.setex('user_income_mail:%s' % user_info.get('username'), 3600 * 24, json_mail)

def reboot_device(username, userid, dev):
    account_key = 'account:%s:%s' % (username, userid)
    b_account = r_session.get(account_key)
    if b_account is None: return
    account = json.loads(b_account.decode('utf-8'))
    print('reboot')
    ubus_cd(account['session_id'], dev['account_id'], ["mnt", "reboot", {}], '&device_id=%s' % dev['device_id'])

# 执行检测异常矿机函数
def detect_exception(user, cookies, user_info):
    from mailsand import send_email
    from mailsand import validateEmail
    print(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'detect_exception:', user.get('userid'))
    config_key = '%s:%s' % ('user', 'system')
    config_info = json.loads(r_session.get(config_key).decode('utf-8'))
    account_data_key = 'account:%s:%s:data' % (user_info.get('username'), user.get('userid'))        
    exist_account_data = r_session.get(account_data_key)
    if exist_account_data is None: return
    account_data = json.loads(exist_account_data.decode('utf-8'))

    if not 'device_info' in account_data.keys(): return
    status_cn={'offline':'离线','online':'在线','exception':'异常'}
    warn_list=[]
    warn_list_ip=[]
    for dev in account_data['device_info']:
        if 'device_id' not in dev.keys():
            continue
        detect_info_key='detect_info:%s:%s' % (user_info.get('username'),dev['device_id'])
        b_detect_info=r_session.get(detect_info_key)
        if b_detect_info is None:
            detect_info={}
        else:
            detect_info=json.loads(b_detect_info.decode('utf-8'))
        if 'updated_time' in detect_info.keys() and detect_info['updated_time'] == account_data['updated_time']: continue
        detect_info['updated_time'] = account_data['updated_time']
        if 'last_status' not in detect_info.keys():
            detect_info['last_status']='online'
        elif dev['status'] != detect_info['last_status']:
            red_log(user, '矿机状态', '状态', '%s:%s -> %s' % (dev['device_name'], status_cn[detect_info['last_status']], status_cn[dev['status']]))
            detect_info['last_status']=dev['status']
            if 'exception_occured_time' not in detect_info.keys() and dev['status'] != 'online':
                detect_info['exception_occured_time'] = detect_info['updated_time']
            if dev['status'] == 'online':
                detect_info.pop('exception_occured_time','^.^')
                detect_info.pop('last_reboot','^.^')
        elif dev['status'] != 'online':
            if 'exception_occured_time' in detect_info.keys():
                exception_occured_time=datetime.strptime(detect_info['exception_occured_time'],'%Y-%m-%d %H:%M:%S')
                if exception_occured_time + timedelta(minutes=10) < datetime.strptime(detect_info['updated_time'],'%Y-%m-%d %H:%M:%S'):
                    if 'last_reboot' not in detect_info.keys():
                        reboot_device(user_info.get('username'), user.get('userid'), dev)
                        detect_info['last_reboot']=detect_info['updated_time']
                    elif 'last_warn' not in detect_info.keys():
                        detect_info['last_warn'] = account_data['updated_time']
                        warn_list.append(dev)
        else:
            detect_info.pop('last_warn','^.^');
        if 'ip_warn_enabled' in user_info.keys() and user_info['ip_warn_enabled'] and dev['status'] == 'online':
            if 'last_ip' not in detect_info.keys():
                detect_info['last_ip']=dev.get('ip')
            elif dev['ip'] != detect_info['last_ip']:
                warn_list_ip.append(dev)
                red_log(user, 'IP变动', '状态', '%s:%s -> %s' % (dev['device_name'], detect_info['last_ip'], dev.get('ip')))
                detect_info['last_ip']=dev.get('ip')
        if dev['status'] == 'online' and 'dcdn_clients' in dev.keys():
            for i,client in enumerate(dev['dcdn_clients']):
                space_last_key='space_%s' % i
                if space_last_key in detect_info.keys():
                    last_space=detect_info[space_last_key]
                    if last_space - 100*1024*1024 > int(client['space_used']):
                        red_log(user, '缓存变动', '状态', '%s:%.1fGB->%.1fGB，删除了:%.1fGB' % (dev['device_name'],float(last_space)/1024/1024/1024,float(client['space_used'])/1024/1024/1024,float(last_space)/1024/1024/1024-float(client['space_used'])/1024/1024/1024))
                        detect_info[space_last_key] = int(client['space_used'])
                    elif last_space < int(client['space_used']):
                        detect_info[space_last_key] = int(client['space_used'])
                else:
                    detect_info[space_last_key] = int(client['space_used'])
                skip_clean=False
                if 'auto_clean_cache_time_from' in user_info.keys() and 'auto_clean_cache_time_to' in user_info.keys():
                    if datetime.now().hour < user_info['auto_clean_cache_time_from'] or datetime.now().hour >= user_info['auto_clean_cache_time_to']:
                        skip_clean=True
                    elif 'auto_clean_cache_reserve_days' in user_info.keys() and 'last_clean_date' in detect_info.keys():
                        if (datetime.strptime(detect_info['last_clean_date'],'%Y-%m-%d %H:%M:%S') + timedelta(days=user_info['auto_clean_cache_reserve_days'])).day > datetime.now().day:
                            skip_clean=True
                if not skip_clean and 'auto_clean_cache_enabled' in user_info.keys() and user_info['auto_clean_cache_enabled']:
                    if 'clean_trigger_limit' in user_info.keys() and 'clean_target_limit' in user_info.keys():
                        if int(dev['disk_quota'])!=10995116277760:
                            account_key = 'account:%s:%s' % (user_info.get('username'), user.get('userid'))        
                            b_account = r_session.get(account_key)
                            if b_account is None: return
                            account = json.loads(b_account.decode('utf-8'))
                            ubus_cd(account['session_id'], dev['account_id'], ["dcdn","set_quota",{"disk_space":"10995116277760"}], '&device_id=%s' % dev['device_id'])
                            red_log(user, '缓存清理', '状态', '%s:%s' % (dev['device_name'], '缓存清理完成'))
                            print('recover_cache_to:10TB');
                        elif (int(client['space_used'])/float(client['space_quota'])) > user_info['clean_trigger_limit']/100:
                            if (int(client['space_used'])==int(client['space_quota'])):
                                red_log(user, '缓存', '状态', '%s:缓存挂载异常，重启矿机' % (dev['device_name']))
                                reboot_device(user_info.get('username'), user.get('userid'), dev)
                                detect_info['last_reboot']=detect_info['updated_time']                            
                            else:
                                account_key = 'account:%s:%s' % (user_info.get('username'), user.get('userid'))
                                b_account = r_session.get(account_key)
                                if b_account is None: return
                                account = json.loads(b_account.decode('utf-8'))
                                target=int(float(client['space_quota'])*user_info['clean_target_limit']/100/1024/1024)*1024*1024
                                print('clear_cache_to:',target/1024/1024,'MB');
                                ubus_cd(account['session_id'], dev['account_id'], ["dcdn","set_quota",{"disk_space":"%d" % target}], '&device_id=%s' % dev['device_id'])
                                red_log(user, '缓存清理', '状态', '%s:%.1fGB -> %.1fGB' % (dev['device_name'], int(client['space_used'])/1024/1024/1024, target/1024/1024/1024))
                                detect_info['last_clean_date']=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                elif skip_clean and 'auto_clean_cache_enabled' in user_info.keys() and user_info['auto_clean_cache_enabled']:
                    if int(dev['disk_quota'])!=10995116277760:
                        account_key = 'account:%s:%s' % (user_info.get('username'), user.get('userid'))
                        b_account = r_session.get(account_key)
                        if b_account is None: return
                        account = json.loads(b_account.decode('utf-8'))
                        ubus_cd(account['session_id'], dev['account_id'], ["dcdn","set_quota",{"disk_space":"10995116277760"}], '&device_id=%s' % dev['device_id'])
                        red_log(user, '缓存清理', '状态', '%s:%s' % (dev['device_name'], '缓存清理完成'))
                        print('recover_cache_to:10TB');
                space_quota_last_key='space_quota_%s' % i
                if space_quota_last_key in detect_info.keys():
                    if 'nas_judge_enabled' in user_info.keys() and user_info['nas_judge_enabled'] and 'nas_reboot_time' in detect_info.keys():
                        nas_reboot_time=datetime.strptime(detect_info['nas_reboot_time'],'%Y-%m-%d %H:%M:%S')
                        if nas_reboot_time + timedelta(minutes=10) <= datetime.strptime(detect_info['updated_time'],'%Y-%m-%d %H:%M:%S'):
                            if 'nas_judge_limit' in user_info.keys():
                                nas_judge_limit=user_info['nas_judge_limit']
                            else:
                                nas_judge_limit=16
                            last_space_quota=detect_info[space_quota_last_key]
                            if last_space_quota > 1024 and last_space_quota < int(1024*1024*1024*nas_judge_limit):
                                reboot_device(user_info.get('username'), user.get('userid'), dev)
                                detect_info['nas_reboot_time']=detect_info['updated_time']
                else:
                    detect_info[space_quota_last_key]=int(client['space_quota'])
                skip_auto_reboot = False
                try:
                    if 'auto_reboot_time' in user_info.keys():
                        reboot_settings = user_info['auto_reboot_time'].split()
                        now = datetime.now()
                        if len(reboot_settings) < 3:
                            raise RuntimeError
                        elif 'last_reboot' in detect_info.keys():
                            if now < last_reboot + timedelta(hours=1):
                                raise RuntimeError
                        if not reboot_settings[2].startswith('*'):
                            if now.isoweekday() != int(reboot_settings[2]):
                                raise RuntimeError
                        if reboot_settings[1].startswith('/'):
                            if 'last_reboot' in detect_info.keys():
                                last_reboot = datetime.strptime(detect_info['last_reboot'],'%Y-%m-%d %H:%M:%S')
                                if now < last_reboot + timedelta(days=int(reboot_settings[1][1:])):
                                    raise RuntimeError
                        elif not reboot_settings[1].startswith('*'):
                            if now.day != int(reboot_settings[1]):
                                raise RuntimeError
                        if reboot_settings[0].startswith('/'):
                            if 'last_reboot' in detect_info.keys():
                                last_reboot = datetime.strptime(detect_info['last_reboot'],'%Y-%m-%d %H:%M:%S')
                                if now < last_reboot + timedelta(hours=int(reboot_settings[0][1:])):
                                    raise RuntimeError
                        elif not reboot_settings[0].startswith('*'):
                            if now.hour != int(reboot_settings[0]):
                                skip_auto_reboot = True
                    else:
                        skip_auto_reboot = True
                except RuntimeError:
                    skip_auto_reboot = True
                if not skip_auto_reboot:
                    reboot_device(user_info.get('username'), user.get('userid'), dev)
                    red_log(user, '定时重启', '状态', '%s:%s' % (dev['device_name'], '已下发定时重启命令'))
                    detect_info['last_reboot']=detect_info['updated_time']
                    
        r_session.set(detect_info_key, json.dumps(detect_info))
    if validateEmail(user_info['email']) == 1:
        mail = dict()
        mail['to'] = user_info['email']
        mail['subject'] = '云监工-矿机异常'
        mail['text'] = ''
        if warn_list:
            for dev in warn_list:
                mail['text'] = ''.join([mail['text'],'您的矿机：',dev['device_name'],'<br />状态：',status_cn[dev['status']] ,'<br />时间：',datetime.now().strftime('%Y-%m-%d %H:%M:%S'),'<br />详情：', dev['exception_message'],'<br />==================<br />'])
        if warn_list_ip:
            for dev in warn_list_ip:
                mail['text'] = ''.join([mail['text'],'您的矿机：',dev['device_name'],'<br />IP变动为：',dev['ip'] ,'<br />时间：',datetime.now().strftime('%Y-%m-%d %H:%M:%S'),'<br />==================<br />'])
        if warn_list or warn_list_ip:
            r_session.rpush('mail_queue',json.dumps(mail))


# 执行收取水晶函数
def check_collect(user, cookies, user_info):
    print(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'check_collect')
    mine_info = get_mine_info(cookies)
    time.sleep(2)
    if mine_info.get('r') != 0: return
    if 'collect_crystal_modify' in user_info.keys():
        limit=user_info.get('collect_crystal_modify')
    else:
        limit=16000;

    if mine_info.get('td_not_in_a') > limit:
        r = collect(cookies)
        if r.get('rd') != 'ok':
            log = '%s' % r.get('rd')
        else:
            log = '收取:%s水晶.' % mine_info.get('td_not_in_a')
        red_log(user, '自动执行', '收取', log)
    time.sleep(3)

# 执行自动提现的函数
def check_drawcash(user, cookies, user_info):
    print(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'check_drawcash')
    if 'draw_money_modify' in user_info.keys():
        limit=user_info.get('draw_money_modify')
    else:
        limit=10.0
    r = exec_draw_cash(cookies=cookies, limits=limit)
    if r.get('rd').find('下限') == -1:
        red_log(user, '自动执行', '提现', r.get('rd'))
    time.sleep(3)

# 执行免费宝箱函数
def check_giftbox(user, cookies, user_info):
    print(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'check_giftbox')
    box_info = api_giftbox(cookies)
    time.sleep(2)
    if box_info.get('r') != 0: return
    for box in box_info.get('ci'):
        if box.get('cnum') == 0:
            r_info = api_openStone(cookies=cookies, giftbox_id=box.get('id'), direction='3')
            if r_info.get('r') != 0:
                log = r_info.get('rd')
            else:
                r = r_info.get('get')
                log = '开启:获得:%s水晶.' % r.get('num')
                ioi_update_key = 'ioi_update:%s:%s' % (user_info.get('username'), user.get(userid))
                r_session.set(ioi_update_key,'updated')
        else:
            r_info = api_giveUpGift(cookies=cookies, giftbox_id=box.get('id'))
            if r_info.get('r') != 0:
                log = r_info.get('rd')
            else:
                log = '丢弃:收费:%s水晶.' % box.get('cnum')
        red_log(user, '自动执行', '宝箱', log)
        time.sleep(3)

# 执行秘银进攻函数
def check_searcht(user, cookies, user_info):
    print(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'check_searcht')
    r = api_sys_getEntry(cookies)
    time.sleep(2)
    if r.get('r') != 0: return
    if r.get('steal_free') > 0:
        steal_info = api_steal_search(cookies)
        if steal_info.get('r') != 0:
            log = regular_html(r.get('rd'))
        else:
            time.sleep(3)
            t = api_steal_collect(cookies=cookies, searcht_id=steal_info.get('sid'))
            if t.get('r') != 0:
                log = 'Forbidden'
            else:
                log = '获得:%s秘银.' % t.get('s')
                time.sleep(1)
                api_steal_summary(cookies=cookies, searcht_id=steal_info.get('sid'))
        red_log(user, '自动执行', '进攻', log)
    time.sleep(3)

# 执行秘银复仇函数
def check_revenge(user, cookies, user_info):
    print(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'check_revenge')
    r = api_steal_stolenSilverHistory(cookies)
    time.sleep(2)
    if r.get('r') != 0: return
    for q in r.get('list'):
        if q.get('st') == 0:
            steal_info = api_steal_search(cookies, q.get('sid'))
            if steal_info.get('r') != 0:
                log = regular_html(r.get('rd'))
            else:
                time.sleep(3)
                t = api_steal_collect(cookies=cookies, searcht_id=steal_info.get('sid'))
                if t.get('r') != 0:
                    log = 'Forbidden'
                else:
                    log = '获得:%s秘银.' % t.get('s')
                    time.sleep(1)
                    api_steal_summary(cookies=cookies, searcht_id=steal_info.get('sid'))
            red_log(user, '自动执行', '复仇', log)
    time.sleep(3)

# 执行幸运转盘函数
def check_getaward(user, cookies, user_info):
    print(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'check_getaward')
    r = api_getconfig(cookies)
    time.sleep(2)
    if r.get('rd') != 'ok': return
    if r.get('cost') == 5000:
        t = api_getaward(cookies)
        if t.get('rd') != 'ok':
            log = t.get('rd')
        else:
            log = '获得:%s' % regular_html(t.get('tip'))
            ioi_update_key = 'ioi_update:%s:%s' % (user_info.get('username'), user.get(userid))
            r_session.set(ioi_update_key,'updated')
        red_log(user, '自动执行', '转盘', log)
    time.sleep(3)

# 收取水晶
def collect_crystal():
    print(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'collect_crystal')

    cookies_auto(check_collect, 'global:auto.collect.cookies')
#    for cookie in r_session.smembers('global:auto.collect.cookies'):
#        check_collect(json.loads(cookie.decode('utf-8')))

# 自动提现
def drawcash_crystal():
    print(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'drawcash_crystal')
    time_now = datetime.now()
    if int(time_now.isoweekday()) != 2: return
    if int(time_now.hour) < 12 or int(time_now.hour) >= 18: return

    cookies_auto(check_drawcash, 'global:auto.drawcash.cookies')
#    for cookie in r_session.smembers('global:auto.drawcash.cookies'):
#        check_drawcash(json.loads(cookie.decode('utf-8')))

# 免费宝箱
def giftbox_crystal():
    print(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'giftbox_crystal')

    cookies_auto(check_giftbox, 'global:auto.giftbox.cookies')
#    for cookie in r_session.smembers('global:auto.giftbox.cookies'):
#        check_giftbox(json.loads(cookie.decode('utf-8')))

# 秘银进攻
def searcht_crystal():
    print(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'searcht_crystal')

    cookies_auto(check_searcht, 'global:auto.searcht.cookies')
#    for cookie in r_session.smembers('global:auto.searcht.cookies'):
#        check_searcht(json.loads(cookie.decode('utf-8')))

# 秘银复仇
def revenge_crystal():
    print(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'revenge_crystal')

    cookies_auto(check_revenge, 'global:auto.revenge.cookies')
#    for cookie in r_session.smembers('global:auto.searcht.cookies'):
#        check_searcht(json.loads(cookie.decode('utf-8')))

# 幸运转盘
def getaward_crystal():
    print(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'getaward_crystal')

    cookies_auto(check_getaward, 'global:auto.getaward.cookies')
#    for cookie in r_session.smembers('global:auto.getaward.cookies'):
#        check_getaward(json.loads(cookie.decode('utf-8')))

# 自动监测
def auto_detect():
    print(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'auto_detect')

    cookies_auto(detect_exception, 'global:auto.detect.cookies')

# 自动报告
def auto_report():
    print(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'auto_report')
    cookies_auto(check_report, 'global:auto.report.cookies')

# 处理函数[重组]
def cookies_auto(func, cookiename):
    users = r_session.smembers(cookiename)
    if users is not None and len(users) > 0:
        for user in users:
            try:
                cookies = json.loads(user.decode('utf-8'))
                session_id=cookies.get('sessionid')
                user_id=cookies.get('userid')
                user_info=cookies.get('user_info')
                if 'collector' in user_info.keys():
                    if user_info['collector'] == collector_id or (user_info['collector'] not in collector_alive and backup_collector):
                        func(cookies, dict(sessionid=session_id, userid=user_id), user_info)
                    else:
                        print('auto skip:',user_info.get('username'))
                elif default_collector:
                    func(cookies, dict(sessionid=session_id, userid=user_id), user_info)
                else:
                    print('auto skip:',user_info.get('username'))
            except Exception as e:
                print(e)
                continue

# 正则过滤+URL转码
def regular_html(info):
    import re
    from urllib.parse import unquote
    regular = re.compile('<[^>]+>')
    url = unquote(info)
    return regular.sub("", url)

# 自动日记记录
def red_log(cook, clas, type, gets):
    user = cook.get('user_info')

    record_key = '%s:%s' % ('record', user.get('username'))
    if r_session.get(record_key) is None:
        record_info = dict(diary=[])
    else:
        record_info = json.loads(r_session.get(record_key).decode('utf-8'))

    id = cook.get('userid')

    log_as_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    body = dict(time=log_as_time, clas=clas, type=type, id=id, gets=gets)

    log_as_body = record_info.get('diary')
    log_trimed = []
    for item in log_as_body:
       if (datetime.now() - datetime.strptime(item.get('time'), '%Y-%m-%d %H:%M:%S')).days < 31:
           log_trimed.append(item)
    log_trimed.append(body)

    record_info['diary'] = log_trimed

    r_session.set(record_key, json.dumps(record_info))

def mail_send():
    from mailsand import send_email
    if not default_collector:
        return
    print(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'mail_send')
    config_key = '%s:%s' % ('user', 'system')
    r_config_info = r_session.get(config_key)
    if r_config_info is not None:
        config_info = json.loads(r_config_info.decode('utf-8'))
        b_mail=r_session.lpop('mail_queue')
        if b_mail is not None:
            mail=json.loads(b_mail.decode('utf-8'))
            if send_email(mail,config_info) != True:
                if not r_session.sismember('mail_send_failed_address',mail['to']):
                    r_session.lpush('mail_queue',b_mail)
                    r_session.sadd('mail_send_failed_address',mail['to'])
                else:
                    print('send mail failed:', mail['to'])
            else:
                r_session.srem('mail_send_failed_address',mail['to'])

config_info = {
    'collect_crystal_interval':30*60,
    'drawcash_crystal_interval':60*60,
    'giftbox_crystal_interval':40*60,
    'searcht_crystal_interval':360*60,
    'revenge_crystal_interval':300*60,
    'getaward_crystal_interval':240*60,
    'get_online_user_data_interval':30,
    'get_offline_user_data_interval':600,
    'clear_offline_user_interval':60,
    'select_auto_task_user_interval':10*60,
    'auto_detect_interval':5*60,
    'master_mail_smtp':'smtp.163.com',
    'master_email':'xxxxxxxx@163.com',
    'master_mail_password':'xxxxxxxxxxxxxx',
    'mail_send_interval':60,
}
task_schedule={}
terminate_flag=False
# 计时器函数，定期执行某个线程，时间单位为秒
def timer():
    global task_schedule
    global terminate_flag
    proc_list={}
    while not terminate_flag:
        for k,v in task_schedule.items():
            now = datetime.now()
            if v < now:
                try:
                    if k not in proc_list.keys():
                        proc_list[k] = []
                    if len(proc_list[k]) < multiple_process:
                        proc = threading.Thread(target=eval(k))
                        proc.start()
                        proc_list[k].append(proc)
                    else:
                        for i,proc in enumerate(proc_list[k]):
                            if proc.isAlive():
                                continue
                            else:
                                proc = threading.Thread(target=eval(k))
                                proc.start()
                                break
                    task_schedule[k] = now + timedelta(seconds=config_info['%s%s'%(k,'_interval')])
                except Exception as e:
                    e = random.randint(5,10)
                    print(now.strftime('%Y-%m-%d %H:%M:%S'),' fork thread %s failed,retry after %d seconds' % (k,e))
                    task_schedule[k] = now + timedelta(seconds=random.randint(5,10))
        time.sleep(1)

def init_task_list():
    global task_schedule
    now=datetime.now()
    task_schedule={
        'collect_crystal': now + timedelta(seconds=random.randint(3,15)),
        'drawcash_crystal': now + timedelta(seconds=random.randint(3,15)),
        'giftbox_crystal': now + timedelta(seconds=random.randint(3,15)),
        'searcht_crystal': now + timedelta(seconds=random.randint(3,15)),
        'revenge_crystal': now + timedelta(seconds=random.randint(3,15)),
        'getaward_crystal': now + timedelta(seconds=random.randint(3,15)),
        'auto_report': now + timedelta(seconds=random.randint(3,15)),
        'auto_detect': now + timedelta(seconds=random.randint(3,15)),
        'get_online_user_data': now + timedelta(seconds=random.randint(3,15)),
        'get_offline_user_data': now + timedelta(seconds=random.randint(3,15)),
        'clear_offline_user': now + timedelta(seconds=random.randint(3,15)),
        'select_auto_task_user': now + timedelta(seconds=random.randint(3,15)),
        'mail_send': now + timedelta(seconds=random.randint(3,15)),
    }
    
if __name__ == '__main__':
    config_key = '%s:%s' % ('user', 'system')
    r_config_info = r_session.get(config_key)
    if r_config_info is None:
        r_session.set(config_key, json.dumps(config_info))
    else:
        config_info = json.loads(r_config_info.decode('utf-8'))
    config_info['auto_report_interval'] = 30*60

    r_session.sadd('collector_working', collector_id)
    # 如有任何疑问及Bug欢迎加入L.k群讨论
    # 将自动任务添加到调度表，启动时间随机分配到3-15秒后
    init_task_list()
    thread_timer = threading.Thread(target=timer)
    thread_timer.start()
    next_check_server = datetime.now() + timedelta(seconds=random.randint(60,120))
    while True:
        now = datetime.now()
        r_session.setex(('server_alive:%s' % collector_id), 120, '在线')
        if now > next_check_server:
            r_session.sadd('collector_working', collector_id)
            for server in r_session.smembers('collector_working'):
                server=server.decode('utf-8')
                if r_session.get('server_alive:%s' % server) is None:
                    r_session.srem('collector_working',server)
                    if server in collector_alive:
                        collector_alive.remove(server)
                else:
                    collector_alive.add(server)
            next_check_server = now + timedelta(seconds=random.randint(60,120))
        r_config_info = r_session.get(config_key)
        if r_config_info is not None:
            config_info = json.loads(r_config_info.decode('utf-8'))
            config_info['auto_report_interval'] = 30*60
        if 'restart_flag' in config_info and config_info['restart_flag']:
            print('all process start restarting')
            terminate_flag = True
            thread_timer.join()
            terminate_flag = False
            init_task_list()
            thread_timer = threading.Thread(target=timer)
            thread_timer.start()
            print('all process restarted')
            config_info['restart_flag']=False
            time.sleep(2)
            r_session.set(config_key, json.dumps(config_info))
        time.sleep(1)

