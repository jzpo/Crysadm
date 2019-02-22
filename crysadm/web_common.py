__author__ = 'powergx'
from flask import request, Response, render_template, session, url_for, redirect
from crysadm import app, r_session
from auth import requires_admin, requires_auth
from datetime import datetime, timedelta
import json
import socket
import struct
from message import send_msg

def convert_to_yuan(crystal_values):
    if crystal_values is None:
        return '-'
    try:
        if int(crystal_values) >= 10000:
            return str(int(crystal_values / 1000) / 10) + '元'
        return str(int(crystal_values)) + '个'
    except ValueError:
        return '-'

def miner_summary(username):
    miner_summary_key = 'miner_summary:%s' % username;
    b_miner_summary = r_session.get(miner_summary_key)
    if b_miner_summary is not None:
        return json.loads(b_miner_summary.decode('utf-8'))
    miner_summary={
        'offline_count':0,
        'online_count':0,
        'pause_count':0,
        'exception_count':0,
        'total_count':0,
		'pause_account':0,
		'exception_account':0,
		'total_account':0,
		'disabled_upnp':0,
		'connecting_upnp':0,
		'failed_upnp':0,
		'success_upnp':0,
		'connecting_dcdn':0,
		'failed_dcdn':0,
		'success_dcdn':0
    }
    for user_id in r_session.smembers('accounts:%s' % username):
        account_data_key = 'account:%s:%s' % (username, user_id.decode('utf-8'))
        exist_account_data = r_session.get(account_data_key)
        if exist_account_data is None:
            return miner_summary
        account_data = json.loads(exist_account_data.decode('utf-8'))
        if account_data['active'] == False:
            miner_summary['pause_account'] = miner_summary['pause_account'] + 1
        elif  account_data['active'] == True:
            miner_summary['total_account'] = miner_summary['total_account'] + 1
        else:
            miner_summary['exception_account'] = miner_summary['exception_account'] + 1
        account_data_key = 'account:%s:%s:data' % (username, user_id.decode('utf-8'))
        exist_account_data = r_session.get(account_data_key)
        if exist_account_data is None:
            return miner_summary
        account_data = json.loads(exist_account_data.decode('utf-8'))
        for dev in account_data['device_info']:
            if dev['paused'] == True:
            	miner_summary['pause_count']=miner_summary['pause_count'] + 1
            elif dev['status'] == 'online':
            	miner_summary['online_count']=miner_summary['online_count'] + 1
            elif dev['status'] == 'offline':
            	miner_summary['offline_count']=miner_summary['offline_count'] + 1
            elif dev['dcdn_upnp_status'] == 'failed':
            	miner_summary['success_upnp']=miner_summary['success_upnp'] + 1
            else:
            	miner_summary['exception_count']=miner_summary['exception_count'] + 1
            miner_summary['total_count']=miner_summary['total_count'] + 1
            if dev['dcdn_upnp_status'] == 'success':
            	miner_summary['success_upnp']=miner_summary['success_upnp'] + 1
            elif dev['dcdn_upnp_status'] == 'failed':
            	miner_summary['failed_upnp']=miner_summary['failed_upnp'] + 1
            elif dev['dcdn_upnp_status'] == 'mapping':
            	miner_summary['connecting_upnp']=miner_summary['connecting_upnp'] + 1
            else:
            	miner_summary['disabled_upnp']=miner_summary['disabled_upnp'] + 1
            for devs in dev['dcdn_clients']:
            	if devs['login_status'] == 'connecting':
            		miner_summary['connecting_dcdn']=miner_summary['connecting_dcdn'] + 1
            	elif devs['login_status'] == 'success':
            		miner_summary['success_dcdn']=miner_summary['success_dcdn'] + 1
            	else:
            		miner_summary['failed_dcdn']=miner_summary['failed_dcdn'] + 1
    return miner_summary

# 获取前一日收益
def __get_yesterday_pdc(username):
    today = datetime.now()
    month_start_date = datetime(year=today.year, month=today.month, day=1).date()
    week_start_date = (today + timedelta(days=-today.weekday())).date()
    begin_date = month_start_date if month_start_date < week_start_date else week_start_date
    begin_date = begin_date + timedelta(days=-1)

    yesterday_m_pdc = 0
    yesterday_w_pdc = 0
    yesterday_m_award_income = 0
    yesterday_w_award_income = 0

    while begin_date < today.date():
        begin_date = begin_date + timedelta(days=1)

        key = 'user_data:%s:%s' % (username, begin_date.strftime('%Y-%m-%d'))

        b_data = r_session.get(key)
        if b_data is None:
            continue

        history_data = json.loads(b_data.decode('utf-8'))
        if begin_date >= month_start_date and begin_date < today.date():
            yesterday_m_pdc += history_data.get('pdc')
            if 'award_income' in history_data.keys():
                yesterday_m_award_income += history_data.get('award_income')
        if begin_date >= week_start_date and begin_date < today.date():
            yesterday_w_pdc += history_data.get('pdc')
            if 'award_income' in history_data.keys():
                yesterday_w_award_income += history_data.get('award_income')

    return yesterday_m_pdc, yesterday_w_pdc, yesterday_m_award_income, yesterday_w_award_income

# 显示控制面板
@app.route('/dashboard')
@requires_auth
def dashboard():
    user = session.get('user_info')
    username = user.get('username')
    user_key = 'user:%s' % username

    config_key = '%s:%s' % ('user', 'system')
    config_info = json.loads(r_session.get(config_key).decode('utf-8'))
    info_msg = None
    if session.get('info_message') is not None:
        info_msg = session.get('info_message')
        session['info_message'] = None

    user_info = json.loads(r_session.get(user_key).decode('utf-8'))
    if 'boxes_sel' not in user_info.keys():
        user_info['boxes_sel'] = ["实时上传速度", "实时下载速度", "实时账号状态", "实时矿机状态", "实时UPNP状态", "实时DCDN状态"]
    return render_template('dashboard.html', user_info=user_info, config_info=config_info, info_msg=info_msg)

# 刷新控制面板数据
@app.route('/dashboard_data')
@requires_auth
def dashboard_data():
    user = session.get('user_info')
    username = user.get('username')
    str_today = datetime.now().strftime('%Y-%m-%d')
    key = 'user_data:%s:%s' % (username, str_today)
    b_data = r_session.get(key)

    user_key = '%s:%s' % ('user', user.get('username'))
    user_info = json.loads(r_session.get(user_key).decode('utf-8'))

    if b_data is None:
        empty_data = {
            'updated_time': '2015-01-01 00:00:00',
            'm_pdc': 0,
            'last_speed': 0,
            'deploy_speed' : 0,
            'w_pdc': 0,
            'yesterday_m_pdc': 0,
            'speed_stat': [],
            'yesterday_w_pdc': 0,
            'pdc': 0,
            'balance': 0,
            'w_award_income': 0
        }
        return Response(json.dumps(dict(today_data=empty_data)), mimetype='application/json')
    today_data = json.loads(b_data.decode('utf-8'))
    need_save = False
    if today_data.get('yesterday_m_pdc') is None or today_data.get('yesterday_w_pdc') is None or today_data.get('yesterday_w_award_income') is None or today_data.get('yesterday_m_award_income') is None:
        yesterday_m_pdc, yesterday_w_pdc, yesterday_m_award_income, yesterday_w_award_income = __get_yesterday_pdc(username)
        today_data['yesterday_m_pdc'] = yesterday_m_pdc
        today_data['yesterday_w_pdc'] = yesterday_w_pdc
        today_data['yesterday_m_award_income'] = yesterday_m_award_income
        today_data['yesterday_w_award_income'] = yesterday_w_award_income
        need_save = True

    today_data['m_pdc'] = today_data.get('yesterday_m_pdc') + today_data.get('pdc')
    today_data['w_pdc'] = today_data.get('yesterday_w_pdc') + today_data.get('pdc')
    today_data['m_award_income'] = today_data.get('yesterday_m_award_income') + today_data.get('award_income')
    today_data['w_award_income'] = today_data.get('yesterday_w_award_income') + today_data.get('award_income')

    if need_save:
        r_session.set(key, json.dumps(today_data))
    today_data['pdc'] -= today_data.get('award_income')
    return Response(json.dumps(dict(today_data=today_data, device_summary=miner_summary(username))), mimetype='application/json')

# 刷新控制面板图表速度数据
@app.route('/dashboard/speed_share')
@requires_auth
def dashboard_speed_share():
    from user import get_id_map
    user = session.get('user_info')
    username = user.get('username')
    accounts_key = 'accounts:%s' % username
    user_key = '%s:%s' % ('user', user.get('username'))
    user_info = json.loads(r_session.get(user_key).decode('utf-8'))
 
    account_key = ['account:%s:%s:data' % (username, name.decode('utf-8')) for name in sorted(r_session.smembers(accounts_key))]
    if len(account_key) == 0:
        return Response(json.dumps(dict(data=[])), mimetype='application/json')
    accounts_key = 'accounts:%s' % user.get('username')
    id_map = get_id_map(user.get('username'))
    drilldown_data = []    
    for acct in sorted(r_session.smembers(accounts_key)):
        account_key = 'account:%s:%s' % (user.get('username'), acct.decode("utf-8"))
        account_info = json.loads(r_session.get(account_key).decode("utf-8"))

        account_data_key = account_key + ':data'
        account_data_value = r_session.get(account_data_key)
        if account_data_value is not None:
            account_info_data=json.loads(account_data_value.decode("utf-8"))
        else:
            continue
        mid = str(account_info_data.get('privilege').get('mid'))

        total_speed = 0
        device_speed = []

        for device_info in account_info_data.get('device_info'):
            if device_info.get('status') != 'online':
                continue
            uploadspeed = int(int(device_info.get('dcdn_upload_speed')) / 1024)            
            #downloadspeed = int(int(device_info.get('dcdn_deploy_speed')) / 1024)
            # total_speed += downloadspeed
            total_speed += uploadspeed            
            device_speed.append(dict(name=device_info.get('device_name'), value=uploadspeed))            
            # device_speed.append(dict(name=device_info.get('device_name'), value=total_speed))

        # 显示在速度分析器圆形图表上的设备ID
        if id_map[account_info.get('user_id')] is None:
            drilldown_data.append(dict(name='账户名:未知', value=total_speed, drilldown_data=device_speed))
        else:
            drilldown_data.append(dict(name='账户名:' + id_map[account_info.get('user_id')], value=total_speed, drilldown_data=device_speed))
        #drilldown_data.append(dict(name='设备名:' + device_info.get('device_name'), value=total_speed, drilldown_data=device_speed))

    return Response(json.dumps(dict(data=drilldown_data)), mimetype='application/json')

# 显示控制面板速度详情
@app.route('/dashboard/speed_detail')
@requires_auth
def dashboard_speed_detail():
    user = session.get('user_info')
    username = user.get('username')
    accounts_key = 'accounts:%s' % username

    account_key = ['account:%s:%s:data' % (username, name.decode('utf-8')) for name in sorted(r_session.smembers(accounts_key))]
    if len(account_key) == 0:
        return Response(json.dumps(dict(data=[])), mimetype='application/json')

    device_speed = []
    for b_acct in r_session.mget(*['account:%s:%s:data' % (username, name.decode('utf-8'))
                                   for name in sorted(r_session.smembers(accounts_key))]):

        account_info = json.loads(b_acct.decode("utf-8"))

        for device_info in account_info.get('device_info'):
            if device_info.get('status') != 'online':
                continue
            upload_speed = int(int(device_info.get('dcdn_upload_speed')) / 1024)
            deploy_speed = int(device_info.get('dcdn_download_speed') / 1024)

            device_speed.append(dict(name=device_info.get('device_name'), upload_speed=upload_speed, deploy_speed=deploy_speed))

    device_speed = sorted(device_speed, key=lambda k: k.get('name'))
    categories = []
    upload_series = dict(name='上传速度', data=[], pointPadding=0.3, pointPlacement=-0.2)
    deploy_series = dict(name='下载速度', data=[], pointPadding=0.4, pointPlacement=-0.2)
    for d_s in device_speed:
        categories.append(d_s.get('name'))
        upload_series.get('data').append(d_s.get('upload_speed'))
        deploy_series.get('data').append(d_s.get('deploy_speed'))

    return Response(json.dumps(dict(categories=categories, series=[upload_series, deploy_series])), mimetype='application/json')

# 刷新今日收益
@app.route('/dashboard/today_income_share')
@requires_auth
def dashboard_today_income_share():
    from user import get_id_map
    user = session.get('user_info')
    username = user.get('username')
    accounts_key = 'accounts:%s' % username
    user_key = '%s:%s' % ('user', user.get('username'))
    user_info = json.loads(r_session.get(user_key).decode('utf-8'))

    account_key = ['account:%s:%s:data' % (username, name.decode('utf-8')) for name in sorted(r_session.smembers(accounts_key))]
    if len(account_key) == 0:
        return Response(json.dumps(dict(data=[])), mimetype='application/json')

    pie_data = []
    id_map = get_id_map(user.get('username'))

    for acct in sorted(r_session.smembers(accounts_key)):
        account_key = 'account:%s:%s' % (user.get('username'), acct.decode("utf-8"))
        account_info = json.loads(r_session.get(account_key).decode("utf-8"))
        account_data_key = account_key + ':data'
        account_data_value = r_session.get(account_data_key)
        if account_data_value is not None:
            account_info_data=json.loads(account_data_value.decode("utf-8"))
        else:
            continue
        mid = str(account_info_data.get('privilege').get('mid'))

        total_value = 0
        total_value += account_info_data.get('mine_info').get('dev_m').get('pdc')
        if id_map[account_info.get('user_id')] is None:
            pie_data.append(dict(name='账户名:未知', y=total_value))
        else:
            pie_data.append(dict(name='账户名:' + id_map[account_info.get('user_id')], y=total_value))

    return Response(json.dumps(dict(data=pie_data)), mimetype='application/json')

# 同比产量
@app.route('/dashboard/DoD_income')
@requires_auth
def dashboard_DoD_income():
    user = session.get('user_info')
    username = user.get('username')
    user_key = 'user:%s' % username

    user_info = json.loads(r_session.get(user_key).decode('utf-8'))
    dod_income = DoD_income_xunlei()

    return dod_income

# 迅雷统计
def DoD_income_xunlei():
    user = session.get('user_info')
    username = user.get('username')

    today_series = dict(name='今日', data=[], pointPadding=0.2, pointPlacement=0, color='#676A6C', yAxis = 0)
    yesterday_series = dict(name='昨日', data=[], pointPadding=-0.1, pointPlacement=0, color='#1AB394', yAxis = 0)
    today_speed_series = dict(name='今日', data=[], type = 'spline', pointPadding=0.2, pointPlacement=0, color='#B8DD22', tooltip=dict(valueSuffix=' KB/s'), yAxis = 1)
    yesterday_speed_series = dict(name='昨日', data=[], type = 'spline', pointPadding=-0.1, pointPlacement=0, color='#66CCFF', tooltip=dict(valueSuffix=' KB/s'), yAxis = 1)

    now = datetime.now()

    key = 'user_data:%s:%s' % (username, now.strftime('%Y-%m-%d'))
    b_today_data_new = r_session.get(key)
    device_count = 0
    s_sum=0
    if b_today_data_new is None:
        today_series['data'] = []
    else:
        today_data = json.loads(b_today_data_new.decode('utf-8'))
        today_series['data'] = []
        # 产量柱子开始
        for i in range(24-now.hour, 25):
            temp = 0 
            for hourly_produce in today_data.get('produce_stat'):
                if hourly_produce.get('hourly_list') is not None:
                    temp +=  hourly_produce.get('hourly_list')[i]
            today_series['data'].append(temp)
        # 产量柱子结束
            today_speed_data = today_data.get('speed_stat')
        # 速度曲线开始
        for i in range(0, 24):
            if i + now.hour < 24:
                continue
            if today_speed_data is not None:
                today_speed_series['data'].append(sum(row.get('dev_speed')[i] for row in today_speed_data) / 8)
            else:
                today_speed_series['data'] = []
        for speed in today_speed_series['data']:
            s_sum+=speed
        today_speed_series['data'].append(today_data.get('last_speed'))
        # 速度曲线结束

    key = 'user_data:%s:%s' % (username, (now + timedelta(days=-1)).strftime('%Y-%m-%d'))
    b_yesterday_data_new = r_session.get(key)
    if b_yesterday_data_new is None:
        yesterday_series['data'] = []
    else:
        yesterday_data = json.loads(b_yesterday_data_new.decode('utf-8'))
        yesterday_series['data'] = []
        if 'produce_stat' in yesterday_data.keys() and len(yesterday_data['produce_stat'])!=0:
            # 产量柱子开始
            for i in range(1, 25): 
                if yesterday_data.get('produce_stat')[0].get('hourly_list') is None:
                    break
                temp = 0
                for hourly_produce in yesterday_data.get('produce_stat'):
                    if hourly_produce.get('hourly_list') is not None:
                        if len(hourly_produce.get('hourly_list')) > i:
                            temp += hourly_produce.get('hourly_list')[i]
                yesterday_series['data'].append(temp)
            # 产量柱子结束
            yesterday_speed_data = yesterday_data.get('speed_stat')
            # 速度曲线开始
            for i in range(0, 24):
                if yesterday_speed_data is not None:
                    yesterday_speed_series['data'].append(sum(row.get('dev_speed')[i] for row in yesterday_speed_data) / 8)
                else:
                    yesterday_speed_series['data'] = []
            # 速度曲线结束

    now_income_value = sum(today_series['data'][0:now.hour]) #今日产量
    dod_income_value = sum(yesterday_series['data'][0:now.hour]) #昨日同比产量
    yesterday_last_value = sum(yesterday_series['data'][:]) #昨日总产量
    device_count = miner_summary(username)['total_count']
    if device_count != 0:
        ave_income_value = now_income_value / device_count #今日每宝产量 = 今日总产量 / 今日上线台数
    else:
        ave_income_value = 0
    upload_data_value = str(int(3600*s_sum/1024/10.24)/100) + 'GB' #预计今日上传数据量

    expected_income = 0
    if dod_income_value > 0:
        expected_income = int((yesterday_last_value / dod_income_value) * now_income_value)

    if len(yesterday_series['data']) != 0:
        dod_income_value += int((yesterday_series['data'][now.hour]) / 60 * now.minute)

    zr_income_value = 0
    if yesterday_last_value > 0:
        if device_count != 0:
            zr_income_value = yesterday_last_value / device_count
#    if yesterday_last_value > 0:
#        if miner_summary(username)['total_count'] != 0:
#            zr_income_value = yesterday_last_value / miner_summary(username)['total_count']

    jr_income_value = 0
    if now_income_value > 0:
        if device_count != 0:
            jr_income_value = expected_income / device_count
#    if now_income_value > 0:
#        if miner_summary(username)['total_count'] != 0:
#            jr_income_value = expected_income / miner_summary(username)['total_count']
 
    user_key = '%s:%s' % ('user', user.get('username'))
    user_info = json.loads(r_session.get(user_key).decode('utf-8'))
    if 'is_show_speed_data' in user_info.keys() and user_info['is_show_speed_data'] == False:
        return Response(json.dumps(dict(series=[yesterday_series, today_series, yesterday_speed_series, today_speed_series],data=dict(last_day_income=convert_to_yuan(yesterday_last_value), dod_income_value=convert_to_yuan(dod_income_value),expected_income=convert_to_yuan(expected_income),jr_income_value=convert_to_yuan(jr_income_value), zr_income_value=convert_to_yuan(zr_income_value), ave_income_value=convert_to_yuan(ave_income_value), upload_data_value=upload_data_value))), mimetype='application/json')
    else:
        return Response(json.dumps(dict(series=[yesterday_series, today_series],data=dict(last_day_income=convert_to_yuan(yesterday_last_value), dod_income_value=convert_to_yuan(dod_income_value),expected_income=convert_to_yuan(expected_income),jr_income_value=convert_to_yuan(jr_income_value), zr_income_value=convert_to_yuan(zr_income_value), ave_income_value=convert_to_yuan(ave_income_value),  upload_data_value=upload_data_value))), mimetype='application/json')

# 显示登录界面
@app.route('/')
def index():
    return redirect(url_for('login'))

# 显示crysadm管理员界面（初次登录）
@app.route('/install')
def install():
    import random, uuid
    from util import hash_password

    if r_session.scard('users') == 0:
        _chars = "0123456789ABCDEF"
        username = ''.join(random.sample(_chars, 6))
        password = ''.join(random.sample(_chars, 6))

        user = dict(username=username, password=hash_password(password), id=str(uuid.uuid1()),
                    active=True, is_admin=True, max_account_no=5,
                    created_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        r_session.set('%s:%s' % ('user', username), json.dumps(user))
        r_session.set('%s:%s' % ('record', username), json.dumps(dict(diary=[])))
        r_session.sadd('users', username)
        return 'username:%s,password:%s' % (username, password)

    return redirect(url_for('login'))

# 添加用户
@app.context_processor
def add_function():
    def convert_to_yuan(crystal_values):
        if crystal_values is None:
            return '待统计'
        if crystal_values >= 10000:
            return str(int(crystal_values / 1000) / 10) + '元'
        return str(crystal_values) + '个'

    # 获取设备类型
    def get_device_type(device_code, model_code):
        if device_code == 421:
            return model_code
        elif device_code == 321:
            return model_code
        return '不知道'

    def int2ip(int_ip):
        return socket.inet_ntoa(struct.pack("I", int_ip))
    
    def convert_to_yuanjiaofen(crystal_values):
        return int(crystal_values / 100) / 100

    return dict(convert_to_yuan=convert_to_yuan, get_device_type=get_device_type, int2ip=int2ip,convert_to_yuanjiaofen=convert_to_yuanjiaofen)

# 显示消息框
@app.context_processor
def message_box():
    if session is None or session.get('user_info') is None:
        return dict()
    user = session.get('user_info')

    msgs_key = 'user_messages:%s' % user.get('username')

    msg_box = list()
    msg_count = 0
    for b_msg_id in r_session.lrange(msgs_key, 0, -1):
        msg_key = 'user_message:%s' % b_msg_id.decode('utf-8')
        b_msg = r_session.get(msg_key)
        if b_msg is None:
            r_session.lrem(msgs_key, msg_key)
            continue

        msg = json.loads(b_msg.decode('utf-8'))
        if msg.get('is_read'):
            continue

        if len(msg.get('content')) > 41:
            msg['content'] = msg.get('content')[:30] + '...'
        else:
            msg['content'] = msg.get('content')[:30]
        msg_count += 1
        if not len(msg_box) > 3:
            msg_box.append(msg)

    return dict(msg_box=msg_box, msg_count=msg_count)
@app.context_processor
def plugins_code():
    config_key = '%s:%s' % ('user', 'system')
    config_info = json.loads(r_session.get(config_key).decode('utf-8'))
    return dict(comments_code=config_info.get('plugin_comments'),statistics_code=config_info.get('plugin_statistics'))

@app.context_processor
def accounts_count():
    count_key = 'count:accounts';
    b_count_info = r_session.get(count_key)
    if b_count_info is not None:
        return dict(accounts_count=json.loads(b_count_info.decode('utf-8')))
    users = r_session.scard('users')
    accounts = 0
    accountsk = 0
    for name in r_session.smembers('users'):
        accounts_key = 'accounts:%s' % name.decode('utf-8')
        for acct in r_session.smembers(accounts_key):
            account_key = 'account:%s:%s' % (name.decode('utf-8'), acct.decode("utf-8"))
            account_data_key = account_key + ':data'
            account_data_value = r_session.get(account_data_key)
            if account_data_value is None: continue
            account_info = json.loads(account_data_value.decode("utf-8"))
            for i in account_info.get('device_info'):
                accountsk += 1

        accounts += r_session.scard(accounts_key)
    accounts_count = dict(users=users, accounts=accounts, accountsk=accountsk)
    r_session.setex(count_key, 120,json.dumps(accounts_count))
    return dict(accounts_count=accounts_count)

@app.context_processor
def header_info():
    if session is None or session.get('user_info') is None:
        return dict()

    user = session.get('user_info')

    username = user.get('username')
    user_key = 'user:%s' % username
    user_info = json.loads(r_session.get(user_key).decode('utf-8'))
    config_key = '%s:%s' % ('user', 'system')
    config_info = json.loads(r_session.get(config_key).decode('utf-8'))

    str_today = datetime.now().strftime('%Y-%m-%d')
    key = 'user_data:%s:%s' % (user.get('username'), str_today)

    data = dict(balance=0,uncollect=0,income=0)

    b_data = r_session.get(key)
    if b_data is not None:
        data['balance'] = json.loads(b_data.decode('utf-8')).get('balance')
        data['uncollect'] = json.loads(b_data.decode('utf-8')).get('uncollect')
        data['income'] = json.loads(b_data.decode('utf-8')).get('income')

    if 'is_admin' not in user_info.keys() or not user_info['is_admin']:
        if 'expire_date' in user_info.keys():
            expire_date=datetime.strptime(user_info['expire_date'],'%Y-%m-%d').date()
            data['expire_info']='账户有效期：%s' % user_info['expire_date']
            today = datetime.strptime(datetime.now().strftime('%Y-%m-%d'),'%Y-%m-%d')
            expire_date_3day = (today + timedelta(days=3)).date()
            if expire_date <= expire_date_3day:
                if expire_date == today.date():
                    data['expired']='您的账户已过有效期：%s，我们将为您继续保留本账户7天，请联系管理员续时' % user_info['expire_date']
                else:
                    data['expired']='您的账户将于%s过期，请及时联系管理员续时' % user_info['expire_date']

    b_api_error_info = r_session.get('api_error_info')
    if b_api_error_info is not None:
        data['api_error_info'] = b_api_error_info.decode('utf-8')

    return data

# 收支分析
@app.route('/money')
@requires_auth
def moneyAnalyzer():
    user = session.get('user_info')
    username = user.get('username')

    user_key = '%s:%s' % ('user', username)
    user_info = json.loads(r_session.get(user_key).decode('utf-8'))

    data_money = dict(balance=0,sevenDaysAverage=0,total_income_money=0,daily_profit=0,daily_outcome_total=0,outcome_total=0,estimated_recover_days=0)
    # 获取数据并计算近7日平均收入
    value = 0
    counter=0
    today = datetime.today()
    for b_data in r_session.mget(
            *['user_data:%s:%s' % (username, (today + timedelta(days=i)).strftime('%Y-%m-%d')) for i in range(-7, 0)]):
        if b_data is None:
            continue
        counter+=1
        data_money = json.loads(b_data.decode('utf-8'))
        value+=data_money.get('pdc')
    if counter!=0:
        data_money['sevenDaysAverage']=value/counter

    str_today = datetime.now().strftime('%Y-%m-%d')
    key = 'user_data:%s:%s' % (username, str_today)
    b_data = r_session.get(key)
    if b_data is not None:
        data_money['balance'] = json.loads(b_data.decode('utf-8')).get('balance')
        data_money['income'] = json.loads(b_data.decode('utf-8')).get('income')

    try:
        data_money['total_income_money'] = data_money['income'] - user_info['withdrawn_money_modify']*10000
    except KeyError:
        data_money['total_income_money'] = 0
    try:
        data_money['daily_profit'] = data_money['sevenDaysAverage']-user_info['daily_outcome']*10000
    except KeyError:
        data_money['daily_profit'] = 0
    try:
        startDay=datetime.strptime(user_info['daily_outcome_start_date'],'%Y-%m-%d')
        days_delta = (datetime.now()-startDay).days
    except KeyError:
        days_delta=0
    try:
        data_money['daily_outcome_total'] = user_info['daily_outcome']*days_delta*10000
    except KeyError:
        data_money['daily_outcome_total'] = 0
    try:
        data_money['outcome_total'] = data_money['daily_outcome_total'] + (user_info['hardware_outcome'] + user_info['other_outcome'])*10000
    except KeyError:
        data_money['outcome_total'] = 0
    data_money['total_profit'] = (data_money['total_income_money'] - data_money['outcome_total'])
    if data_money['daily_profit']!=0:
        data_money['estimated_recover_days'] = int(data_money['total_profit']/data_money['daily_profit'])*(-1)

    return render_template('money.html', data_money=data_money,user_info=user_info)

@app.route('/post_comment', methods=['POST'])
@requires_auth
def post_comment():
    user = session.get('user_info')
    chat = {'author':user.get('username'),
            'date':datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'message':request.values.get('message')}
    if len(request.values.get('message')) > 0:
        r_session.lpush('comments_list',json.dumps(chat))
    return redirect(url_for('comments'))

@app.route('/submit_feedback', methods=['POST'])
@requires_auth
def submit_feedback():
    user = session.get('user_info')
    subject = request.values.get('subject')
    content = str(request.values.get('content')).replace('\n','<br/>')
    config_key = '%s:%s' % ('user', 'system')
    config_info = json.loads(r_session.get(config_key).decode('utf-8'))
    receiver = config_info.get('feedback_user')
    if receiver is None:
        session['error_message']='管理员尚未配置工单处理账户，请敦促管理员~'
        return redirect(url_for('comments'))
    session['info_message']=send_msg(receiver,subject,content,3600 * 24 * 31,user.get('username'))
    return redirect(url_for('comments'))

@app.route('/get_comments')
@requires_auth
def get_comments():
    r_session.ltrim('comments_list',0,10000)
    comments_list=r_session.lrange('comments_list',0,100)
    recent_chat=[]
    for i in range(0,len(comments_list)):
        if comments_list[i] is None:
            break
        chat=json.loads(comments_list[i].decode('utf-8'))
        recent_chat.append(chat)
    return Response(json.dumps(dict(messages=recent_chat)), mimetype='application/json')

@app.route('/comments')
@requires_auth
def comments():
    err_msg = None
    if session.get('error_message') is not None:
        err_msg = session.get('error_message')
        session['error_message'] = None
    info_msg = None
    if session.get('info_message') is not None:
        info_msg = session.get('info_message')
        session['info_message'] = None
    return render_template('comments.html',err_msg=err_msg,info_msg=info_msg)

@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404
