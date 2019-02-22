# Html － 我的矿机
__author__ = 'powergx'
from flask import request, Response, render_template, session, url_for, redirect
from crysadm import app, r_session
from auth import requires_admin, requires_auth
import json
import requests
import threading
from urllib.parse import urlparse, parse_qs, unquote
import time
from datetime import datetime
import re
from api import ubus_cd, collect, exec_draw_cash, api_sys_getEntry, api_steal_search, api_steal_collect, api_steal_summary, api_getaward, get_mine_info

# 加载矿机主页面
@app.route('/excavators')
@requires_auth
def excavators():
    user = session.get('user_info')
    user_key = '%s:%s' % ('user', user.get('username'))
    user_info = json.loads(r_session.get(user_key).decode('utf-8'))
    rows_key = '%s:%s' % ('rows', user.get('username'))
    b_rows_info = r_session.get(rows_key)
    if b_rows_info is None:
        rows_info = set(["phone", "mid", "device_name", "hardware_model", "system_version", "dcdn_upload_speed", "dcdn_download_speed", "space_used", "status", "dcdn_upnp_status", "dcdn_upnp_message", "ip", "password"])
    else:
        rows_info = set(json.loads(b_rows_info.decode('utf-8')))
    rows_today_key = '%s:%s' % ('rows_today', user.get('username'))
    b_rows_today_info = r_session.get(rows_today_key)
    if b_rows_today_info is None:
        rows_today_info = set(["phone","display_name","pdc","td_s","s","td_box_pdc","td_not_in_a","td_c","r_can_use","r_h_a","updated_time"])
    else:
        rows_today_info = set(json.loads(b_rows_today_info.decode('utf-8')))
    err_msg = None
    if session.get('error_message') is not None:
        err_msg = session.get('error_message')
        session['error_message'] = None

    info_msg = None
    if session.get('info_message') is not None:
        info_msg = session.get('info_message')
        session['info_message'] = None

    accounts_key = 'accounts:%s' % user.get('username')
    accounts = list()
    devices = list()

    show_drawcash = not (r_session.get('can_drawcash') is None or
                         r_session.get('can_drawcash').decode('utf-8') == '0')
    for acct in r_session.smembers(accounts_key):
        account_key = 'account:%s:%s' % (user.get('username'), acct.decode("utf-8"))
        account_data_key = account_key + ':data'
        account_data_value = r_session.get(account_data_key)
        account_info = json.loads(r_session.get(account_key).decode("utf-8"))
        if account_data_value is not None:
            account_info['data'] = json.loads(account_data_value.decode("utf-8"))
        if 'root_passwd' in user_info.keys() and 'data' in account_info.keys() and 'device_info' in account_info['data'].keys():
            for dev in account_info['data']['device_info']:
                if dev['device_id'] in user_info['root_passwd'].keys():
                    dev['password']=user_info['root_passwd'][dev['device_id']]
        account_info_show={}
        if user_info.get('is_show_byname') == 0:
            account_info_show['display_name']=account_info.get('remark_name')
        elif user_info.get('is_show_byname') == 1:
            account_info_show['display_name']=account_info.get('account_name')
        else:
            account_info_show['display_name']=account_info.get('username')
        if account_info_show['display_name'] is None:
            account_info_show['display_name'] = ''
        if 'data' not in account_info.keys():
            continue
        if 'phone' not in account_info['data']['privilege'].keys():
            account_info_show['phone']=''
        else:
            account_info_show['phone'] = account_info['data']['privilege']['phone']
        account_info_show['pdc'] = account_info['data']['mine_info']['dev_m']['pdc']
        account_info_show['td_s'] = account_info['data']['mine_info']['td_s']
        account_info_show['s'] = account_info['data']['mine_info']['s']
        account_info_show['td_s'] = account_info['data']['mine_info']['td_s']
        account_info_show['td_box_pdc'] = account_info['data']['mine_info']['td_box_pdc']
        account_info_show['td_not_in_a'] = account_info['data']['mine_info']['td_not_in_a']
        account_info_show['td_c'] = account_info['data']['mine_info']['td_c']
        if 'r_can_use' in account_info['data']['income'].keys():
            account_info_show['r_can_use'] = '%.2f元' % (int(account_info['data']['income']['r_can_use'])/10000.0)
        else:
            account_info_show['r_can_use'] = '未知'
        if 'r_h_a' in account_info['data']['income'].keys():
            account_info_show['r_h_a'] = '%.2f元' % (int(account_info['data']['income']['r_h_a'])/10000.0)
        else:
            account_info_show['r_h_a'] = '未知'
        account_info_show['updated_time'] = account_info['data']['updated_time']
        account_info_show['operation'] = ''
        if show_drawcash:
            account_info_show['operation'] = '''
<form role="form" style="margin-left: 3px;float:right;" action="/drawcash/''' + account_info['user_id'] + '''" method="post">
    <button type="submit" style="margin: 0px;" onclick="javascript:return confirm('确认要提现?')" class="btn btn-info btn-xs">提现</button>
</form>
    '''
        account_info_show['operation'] = account_info_show['operation'] + '''
<form role="form" style="margin-left: 3px;float:right;" action="/getaward/''' + account_info['user_id'] + '''" method="post">
    <button type="submit" style="margin: 0px;" onclick="javascript:return confirm('确认要转盘一次?')" class="btn btn-info btn-xs">转盘</button>
</form>
<form role="form" style="margin-left: 3px;float:right;" action="/searcht/''' + account_info['user_id'] + '''" method="post">
    <button type="submit" style="margin: 0px;" onclick="javascript:return confirm('确认要进攻一次?')" class="btn btn-info btn-xs">进攻</button>
</form>
<form role="form" style="float:right;" action="/collect/''' + account_info['user_id'] + '''" method="post">
    <button type="submit" style="margin: 0px;" onclick="javascript:return confirm('确认要收取水晶?')" class="btn btn-info btn-xs">收取</button>
</form>
    '''
        for dev in account_info['data']['device_info']:
            device={}
            device['phone'] = account_info_show['phone']
            if 'mid' not in account_info['data']['privilege']:
                device['mid'] = ''
            else:
                device['mid'] = account_info['data']['privilege']['mid']
            device['device_name'] = dev['device_name']
            device['hardware_model'] = dev['hardware_model']
            device['system_version'] = dev['system_version']
            device['status'] = ''
            if dev['upgradeable']:
                device['status']='<i class="fa fa-arrow-circle-up" style="color:red;"></i>'
            if dev['paused'] == True:
                device['status'] = '<span class="label label-default">暂停</span>' + device['status']
            elif dev['status'] == 'online':
                device['status'] = '<span class="label label-info">在线</span>' + device['status']
            elif dev['status'] == 'offline':
                device['status'] = '<span class="label label-warning">断网</span>' + device['status']
            else:
                device['status'] = '<span class="label label-warning">异常</span>' + device['status']
            device['dcdn_upnp_status'] = dev['dcdn_upnp_status']
            if 'dcdn_upnp_message' in dev.keys():
                device['dcdn_upnp_message'] = dev['dcdn_upnp_message']
            else:
                device['dcdn_upnp_message'] = '-'
            device['ip'] = dev['ip']
            device['lan_ip'] = dev['lan_ip']
            if 'password' in dev.keys():
                device['password'] = dev['password']
            else:
                device['password'] = '''
<form role="form" action="/admin_root" method="post">
<input type="hidden" name="device_id" value="''' + dev['device_id'] + '''" />
<input type="hidden" name="account_id" value="''' + dev['account_id'] + '''" />
<input type="hidden" name="session_id" value="''' + account_info['session_id'] + '''" />
<button type="submit" style="margin: 0px;" class="btn btn-info btn-xs">计算</button>
</form>
'''
            device['operation'] = '''
<form role="form" action="/admin_device" method="post">
<input type="hidden" name="device_id" value="''' + dev['device_id'] + '''" />
<input type="hidden" name="account_id" value="''' + dev['account_id'] + '''" />
<input type="hidden" name="session_id" value="''' + account_info['session_id'] + '''" />
<button type="submit" style="margin: 0px;" class="btn btn-info btn-xs" onclick="window.open('http://kj.xunlei.com/setting.html?user_id=''' + account_info['user_id'] + '''&session_id=''' + account_info['session_id'] + '''&device_id=''' + dev['device_id'] + '''');return false;">APP</button>
<button type="submit" style="margin: 0px;" class="btn btn-info btn-xs">管理</button>
</form>
'''
            if len(dev.get('dcdn_clients')) == 0:
                device['upload_speed'] = '-'
                device['download_speed'] = '-'
                device['space_used'] = '-'
                devices.append(device)
            else:
                for detail in dev.get('dcdn_clients'):
                    device['upload_speed'] = '%d/%d' % (int(int(detail['upload_speed'])/1024),int(int(detail['upload_speed_max'])/1024))
                    device['download_speed'] = '%d/%d' % (int(int(detail['download_speed'])/1024),int(int(detail['download_speed_max'])/1024))
                    if int(detail['space_quota']) == 0:
                        space_used_percentage = '0'
                    else:
                        space_used_percentage = '%.1f' % (int(detail['space_used'])/float(detail['space_quota'])*100)
                    device['space_used'] =  '''
<div class="progress" style="margin-bottom: 0px;border: 1px solid rgb(35, 198, 200);border-radius: 0px;padding: 1px;">
    <div style="width: '''+ space_used_percentage + '''%" aria-valuemax="100" aria-valuemin="0" aria-valuenow="''' + space_used_percentage + '''" role="progressbar" class="progress-bar progress-bar-info">
    </div>
</div>
<span style="float:left;color:black;margin-top:-19px;margin-left:2px">''' + ('%d/%d' % (int(int(detail['space_used'])/1024/1024/1024),int(int(detail['space_quota'])/1024/1024/1024))) + '''</span>
<span style="float:right;color:black;margin-top:-19px;margin-right:2px">''' + space_used_percentage + '''%</span>
'''
                    devices.append(device)
        accounts.append(account_info_show)
    devices.sort(key=lambda dev : dev['device_name'])
    return render_template('excavators.html', err_msg=err_msg, info_msg=info_msg, accounts=accounts, devices=devices,
                           rows_info=rows_info,rows_today_info=rows_today_info,
                           show_drawcash=show_drawcash)
# 重发收益报告
@app.route('/resend_report')
@requires_auth
def resend_report():
    user = session.get('user_info')
    resend_key = '%s:%s' % ('last_resend', user.get('username'))
    if r_session.get(resend_key) is not None:
        session['error_message'] = '您的请求过于频繁，请稍后再尝试。'
        return redirect(url_for('excavators'))
    mail_key = '%s:%s' % ('user_income_mail', user.get('username'))
    b_mail = r_session.get(mail_key)
    if b_mail is None:
        session['error_message'] = '您的收益报告尚未生成，请开启自动报告或等待系统生成。'
        return redirect(url_for('excavators'))
    r_session.rpush('mail_queue',b_mail)
    session['info_message'] = '您的收益报告已经加入邮件发送队列，请等待系统发送'
    r_session.setex(resend_key, 3600, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    return redirect(url_for('excavators'))

# 加载选择列界面
@app.route('/excavators_setting')
@requires_auth
def excavators_setting():
    user = session.get('user_info')
    rows_key = '%s:%s' % ('rows', user.get('username'))
    b_rows_info = r_session.get(rows_key)
    rows_today_key = '%s:%s' % ('rows_today', user.get('username'))
    b_rows_today_info = r_session.get(rows_today_key)
    if b_rows_info is None:
        rows_info = set(["phone", "mid", "device_name", "hardware_model", "system_version", "dcdn_upload_speed", "dcdn_download_speed", "space_used", "status", "dcdn_upnp_status", "dcdn_upnp_message", "ip", "password"])
    else:
        rows_info = set(json.loads(b_rows_info.decode('utf-8')))
    if b_rows_today_info is None:
        rows_today_info = set(["phone","display_name","pdc","td_s","s","td_box_pdc","td_not_in_a","td_c","r_can_use","r_h_a","updated_time"])
    else:
        rows_today_info = set(json.loads(b_rows_today_info.decode('utf-8')))
    return render_template('excavators_setting.html', rows_info=rows_info, rows_today_info=rows_today_info)

# 选择列
@app.route('/excavators_select_row/<value>', methods=['POST'])
@requires_auth
def excavators_select_row(value):
    user = session.get('user_info')
    rows = request.form.getlist('rows')
    if value == 'today':
        rows_key = '%s:%s' % ('rows_today', user.get('username'))
    elif value == 'device':
        rows_key = '%s:%s' % ('rows', user.get('username'))
    else:
        session['error_message']='参数错误'
        return redirect(url_for('excavators'))
    r_session.set(rows_key, json.dumps(rows))
    return redirect(url_for('excavators'))

@app.route('/excavators_sort')
@requires_auth
def excavators_sort():
    user = session.get('user_info')
    user_key = '%s:%s' % ('user', user.get('username'))
    user_info = json.loads(r_session.get(user_key).decode('utf-8'))
    if request.args.get('sort') is not None:
        if 'sort_by' in user_info.keys() and user_info['sort_by'] == request.args.get('sort'):
            user_info['sort_reverse'] = not user_info['sort_reverse']
        user_info['sort_by'] = request.args.get('sort')
    elif 'sort_reverse' not in user_info.keys():
        user_info['sort_reverse']=False
    r_session.set(user_key, json.dumps(user_info))
    return redirect(url_for('excavators'))

# 正则过滤+URL转码
def regular_html(info):
    regular = re.compile('<[^>]+>')
    url = unquote(info)
    return regular.sub("", url)

# 手动日记记录
def red_log(clas, type, id, gets, user=None):
    if user is None:
        user = session.get('user_info')
        record_key = '%s:%s' % ('record', user.get('username'))
    else:
        record_key = '%s:%s' % ('record', user)
    record_info = json.loads(r_session.get(record_key).decode('utf-8'))

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

# 收取水晶[id]
@app.route('/collect/<user_id>', methods=['POST'])
@requires_auth
def collect_id(user_id):
    user = session.get('user_info')
    account_key = 'account:%s:%s' % (user.get('username'), user_id)
    account_info = json.loads(r_session.get(account_key).decode("utf-8"))

    session_id = account_info.get('session_id')
    user_id = account_info.get('user_id')

    cookies = dict(sessionid=session_id, userid=str(user_id))

    mine_info = get_mine_info(cookies)
    r = collect(cookies)
    if r.get('rd') != 'ok':
        log = '%s' % r.get('rd')
        session['error_message'] = log
        return redirect(url_for('excavators'))
    else:
        log = '收取:%s水晶.' % mine_info.get('td_not_in_a')
        session['info_message'] = log
    red_log('手动执行', '收取', user_id, log)
    account_data_key = account_key + ':data'
    account_data_value = json.loads(r_session.get(account_data_key).decode("utf-8"))
    account_data_value.get('mine_info')['td_not_in_a'] = 0
    r_session.set(account_data_key, json.dumps(account_data_value))

    return redirect(url_for('excavators'))

def async_collect_all(username):
    for b_user_id in r_session.smembers('accounts:%s' % username):

        account_key = 'account:%s:%s' % (username, b_user_id.decode("utf-8"))
        account_info = json.loads(r_session.get(account_key).decode("utf-8"))

        session_id = account_info.get('session_id')
        user_id = account_info.get('user_id')

        cookies = dict(sessionid=session_id, userid=str(user_id))
        mine_info = get_mine_info(cookies)
        time.sleep(5)
        r = collect(cookies)
        if r.get('rd') != 'ok':
            log = '%s' % r.get('rd')
        else:
            log = '收取:%s水晶.' % mine_info.get('td_not_in_a')
            account_data_key = account_key + ':data'
            account_data_value = json.loads(r_session.get(account_data_key).decode("utf-8"))
            account_data_value.get('mine_info')['td_not_in_a'] = 0
            r_session.set(account_data_key, json.dumps(account_data_value))
        red_log('手动执行', '收取', user_id, log, username)
    
# 收取水晶[all]
@app.route('/collect/all', methods=['POST'])
@requires_auth
def collect_all():
    user = session.get('user_info')
    username = user.get('username')

    threading.Thread(target=async_collect_all, args=(username,)).start()
    session['info_message'] = '已经全部安排收取水晶，请至少等待（5*账号数）秒后，检查日志查询结果'

    return redirect(url_for('excavators'))

# 幸运转盘[id]
@app.route('/getaward/<user_id>', methods=['POST'])
@requires_auth
def getaward_id(user_id):
    user = session.get('user_info')
    account_key = 'account:%s:%s' % (user.get('username'), user_id)
    account_info = json.loads(r_session.get(account_key).decode("utf-8"))

    session_id = account_info.get('session_id')
    user_id = account_info.get('user_id')

    cookies = dict(sessionid=session_id, userid=str(user_id))
    r = api_getaward(cookies)
    if r.get('rd') != 'ok':
        session['error_message'] = r.get('rd')
        red_log('手动执行', '转盘', user_id, r.get('rd'))
        return redirect(url_for('excavators'))
    else:
        session['info_message'] = '获得:%s  下次转需要:%s秘银.<br />' % (regular_html(r.get('tip')), r.get('cost'))
        red_log('手动执行', '转盘', user_id, '获得:%s' % regular_html(r.get('tip')))
    account_data_key = account_key + ':data'
    account_data_value = json.loads(r_session.get(account_data_key).decode("utf-8"))
    account_data_value.get('mine_info')['td_not_in_a'] = 0
    r_session.set(account_data_key, json.dumps(account_data_value))

    return redirect(url_for('excavators'))

def async_getaward_all(username):
    for b_user_id in r_session.smembers('accounts:%s' % username):

        account_key = 'account:%s:%s' % (username, b_user_id.decode("utf-8"))
        account_info = json.loads(r_session.get(account_key).decode("utf-8"))

        session_id = account_info.get('session_id')
        user_id = account_info.get('user_id')

        cookies = dict(sessionid=session_id, userid=str(user_id))
        r = api_getaward(cookies)
        if r.get('rd') != 'ok':
            red_log('手动执行', '转盘', user_id, r.get('rd'), username)
        else:
            red_log('手动执行', '转盘', user_id, '获得:%s' % regular_html(r.get('tip')), username)
            account_data_key = account_key + ':data'
            account_data_value = json.loads(r_session.get(account_data_key).decode("utf-8"))
            account_data_value.get('mine_info')['td_not_in_a'] = 0
            r_session.set(account_data_key, json.dumps(account_data_value))
    
# 幸运转盘[all]
@app.route('/getaward/all', methods=['POST'])
@requires_auth
def getaward_all():
    user = session.get('user_info')
    username = user.get('username')

    threading.Thread(target=async_getaward_all, args=(username,)).start()
    session['info_message'] = '已经全部安排幸运转盘，请稍后检查日志查询结果'

    return redirect(url_for('excavators'))

# 秘银进攻[id]
@app.route('/searcht/<user_id>', methods=['POST'])
@requires_auth
def searcht_id(user_id):
    user = session.get('user_info')
    account_key = 'account:%s:%s' % (user.get('username'), user_id)
    account_info = json.loads(r_session.get(account_key).decode("utf-8"))

    session_id = account_info.get('session_id')
    user_id = account_info.get('user_id')

    cookies = dict(sessionid=session_id, userid=str(user_id))
    r = check_searcht(cookies)
    if r.get('r') != 0:
        session['error_message'] = regular_html(r.get('rd'))
        red_log('手动执行', '进攻', user_id, regular_html(r.get('rd')))
        return redirect(url_for('excavators'))
    else:
        session['info_message'] = '获得:%s秘银.' % r.get('s')
        red_log('手动执行', '进攻', user_id, '获得:%s秘银.' % r.get('s'))
    account_data_key = account_key + ':data'
    account_data_value = json.loads(r_session.get(account_data_key).decode("utf-8"))
    account_data_value.get('mine_info')['td_not_in_a'] = 0
    r_session.set(account_data_key, json.dumps(account_data_value))

    return redirect(url_for('excavators'))

def async_searcht_all(username):
    for b_user_id in r_session.smembers('accounts:%s' % username):

        account_key = 'account:%s:%s' % (username, b_user_id.decode("utf-8"))
        account_info = json.loads(r_session.get(account_key).decode("utf-8"))

        session_id = account_info.get('session_id')
        user_id = account_info.get('user_id')

        cookies = dict(sessionid=session_id, userid=str(user_id))
        r = check_searcht(cookies)
        if r.get('r') != 0:
            red_log('手动执行', '进攻', user_id, regular_html(r.get('rd')), username)
        else:
            red_log('手动执行', '进攻', user_id, '获得:%s秘银.' % r.get('s'), username)
            account_data_key = account_key + ':data'
            account_data_value = json.loads(r_session.get(account_data_key).decode("utf-8"))
            account_data_value.get('mine_info')['td_not_in_a'] = 0
            r_session.set(account_data_key, json.dumps(account_data_value))

# 秘银进攻[all]
@app.route('/searcht/all', methods=['POST'])
@requires_auth
def searcht_all():
    user = session.get('user_info')
    username = user.get('username')

    threading.Thread(target=async_searcht_all, args=(username,)).start()
    session['info_message'] = '已经全部安排秘银进攻，请稍后检查日志查询结果'

    return redirect(url_for('excavators'))

# 执行进攻函数
def check_searcht(cookies):
    t = api_sys_getEntry(cookies)
    if t.get('r') != 0:
        return dict(r='-1', rd='Forbidden')
    if t.get('steal_free') > 0:
        steal_info = api_steal_search(cookies)
        if steal_info.get('r') != 0:
            return steal_info
        r = api_steal_collect(cookies=cookies, searcht_id=steal_info.get('sid'))
        if r.get('r') != 0:
            return dict(r='-1', rd='Forbidden')
        api_steal_summary(cookies=cookies, searcht_id=steal_info.get('sid'))
        return r
    return dict(r='-1', rd='体力值为零')

# 用户提现[id]
@app.route('/drawcash/<user_id>', methods=['POST'])
@requires_auth
def drawcash_id(user_id):
    user = session.get('user_info')
    account_key = 'account:%s:%s' % (user.get('username'), user_id)
    account_info = json.loads(r_session.get(account_key).decode("utf-8"))

    session_id = account_info.get('session_id')
    user_id = account_info.get('user_id')

    cookies = dict(sessionid=session_id, userid=str(user_id))
    r = exec_draw_cash(cookies)
    red_log('手动执行', '提现', user_id, r.get('rd'))
    if r.get('r') != 0:
        session['error_message'] = r.get('rd')
        return redirect(url_for('excavators'))
    else:
        session['info_message'] = r.get('rd')
    account_data_key = account_key + ':data'
    account_data_value = json.loads(r_session.get(account_data_key).decode("utf-8"))
    account_data_value.get('income')['r_can_use'] -= int(account_data_value.get('income')['r_can_use'])
    r_session.set(account_data_key, json.dumps(account_data_value))

    return redirect(url_for('excavators'))

def async_drawcash_all(username):
    for b_user_id in r_session.smembers('accounts:%s' % username):

        account_key = 'account:%s:%s' % (username, b_user_id.decode("utf-8"))
        account_info = json.loads(r_session.get(account_key).decode("utf-8"))

        session_id = account_info.get('session_id')
        user_id = account_info.get('user_id')

        cookies = dict(sessionid=session_id, userid=str(user_id))
        r = exec_draw_cash(cookies)
        red_log('手动执行', '提现', user_id, r.get('rd'), username)
        if r.get('r') == 0:
            account_data_key = account_key + ':data'
            account_data_value = json.loads(r_session.get(account_data_key).decode("utf-8"))
            account_data_value.get('income')['r_can_use'] -= int(account_data_value.get('income')['r_can_use'])
            r_session.set(account_data_key, json.dumps(account_data_value))
    
# 用户提现[all]
@app.route('/drawcash/all', methods=['POST'])
@requires_auth
def drawcash_all():
    user = session.get('user_info')
    username = user.get('username')

    threading.Thread(target=async_drawcash_all, args=(username,)).start()
    session['info_message'] = '已经全部安排提现，请稍后检查日志查询提现结果'

    return redirect(url_for('excavators'))

def async_stop_device_all(user):
    accounts_key = 'accounts:%s' % user.get('username')
    for acct in r_session.smembers(accounts_key):
        account_key = 'account:%s:%s' % (user.get('username'), acct.decode("utf-8"))
        account_data_key = account_key + ':data'
        account_data_value = r_session.get(account_data_key)
        account_info = json.loads(r_session.get(account_key).decode("utf-8"))
        if account_data_value is not None:
            data = json.loads(account_data_value.decode("utf-8"))
            if 'device_info' in data.keys():
                for device in data['device_info']:
                    if device['status'] == 'offline':
                        continue
                    session_id = account_info['session_id']
                    device_id = device['device_id']
                    account_id = device['account_id']
                    ubus_cd(session_id, account_id, ["dcdn", "stop", {}], '&device_id=%s' % device_id)
                    time.sleep(5)
    
# 一键暂停全部设备
@app.route('/stop_device_all', methods=['POST'])
@requires_auth
def stop_device_all():
    user = session.get('user_info')
    threading.Thread(target=async_stop_device_all, args=(user,)).start()
    session['info_message']='已经安排暂停全部设备，请至少等待（5*账号数）秒后，检查状态'
    return redirect(url_for('excavators'))

# 暂停设备按钮
@app.route('/stop_device', methods=['POST'])
@requires_auth
def stop_device():
    device_id = request.values.get('device_id')
    session_id = request.values.get('session_id')
    account_id = request.values.get('account_id')

    ubus_cd(session_id, account_id, ["dcdn", "stop", {}], '&device_id=%s' % device_id)

    session['device_id'] = device_id
    session['session_id'] = session_id
    session['account_id'] = account_id
    session['info_message'] = '设备已紧急叫停'
    return render_admin_device()

def async_start_device_all(user):
    accounts_key = 'accounts:%s' % user.get('username')
    for acct in r_session.smembers(accounts_key):
        account_key = 'account:%s:%s' % (user.get('username'), acct.decode("utf-8"))
        account_data_key = account_key + ':data'
        account_data_value = r_session.get(account_data_key)
        account_info = json.loads(r_session.get(account_key).decode("utf-8"))
        if account_data_value is not None:
            data = json.loads(account_data_value.decode("utf-8"))
            if 'device_info' in data.keys():
                for device in data['device_info']:
                    if device['status'] == 'offline':
                        continue
                    session_id = account_info['session_id']
                    device_id = device['device_id']
                    account_id = device['account_id']
                    ubus_cd(session_id, account_id, ["dcdn", "start", {}], '&device_id=%s' % device_id)
                    time.sleep(5)
    
# 一键启动全部设备
@app.route('/start_device_all', methods=['POST'])
@requires_auth
def start_device_all():
    user = session.get('user_info')
    threading.Thread(target=async_start_device_all, args=(user,)).start()
    session['info_message']='已经安排启动全部设备，请至少等待（5*账号数）秒后，检查状态'
    return redirect(url_for('excavators'))

# 启动设备按钮
@app.route('/start_device', methods=['POST'])
@requires_auth
def start_device():
    device_id = request.values.get('device_id')
    session_id = request.values.get('session_id')
    account_id = request.values.get('account_id')

    ubus_cd(session_id, account_id, ["dcdn", "start", {}], '&device_id=%s' % device_id)

    session['device_id'] = device_id
    session['session_id'] = session_id
    session['account_id'] = account_id
    session['info_message'] = '设备已启动成功'
    return render_admin_device()

def async_upgrade_device_all(user):
    accounts_key = 'accounts:%s' % user.get('username')
    for acct in r_session.smembers(accounts_key):
        account_key = 'account:%s:%s' % (user.get('username'), acct.decode("utf-8"))
        account_data_key = account_key + ':data'
        account_data_value = r_session.get(account_data_key)
        account_info = json.loads(r_session.get(account_key).decode("utf-8"))
        if account_data_value is not None:
            data = json.loads(account_data_value.decode("utf-8"))
            if 'device_info' in data.keys():
                for device in data['device_info']:
                    if not device['upgradeable']:
                        continue
                    session_id = account_info['session_id']
                    device_id = device['device_id']
                    account_id = device['account_id']
                    ubus_cd(session_id, account_id, ["upgrade", "start", {}], '&device_id=%s' % device_id)
                    ubus_cd(session_id, account_id, ["upgrade", "get_progress", {}], '&device_id=%s' % device_id)
                    time.sleep(5)

# 一键升级全部设备按钮
@app.route('/upgrade_device_all', methods=['POST'])
@requires_auth
def upgrade_device_all():
    user = session.get('user_info')
    threading.Thread(target=async_upgrade_device_all, args=(user,)).start()
    session['info_message']='已经安排所有可升级设备升级，请至少等待（5*账号数）秒后，检查升级状态'
    return redirect(url_for('excavators'))

# 升级设备按钮
@app.route('/upgrade_device', methods=['POST'])
@requires_auth
def upgrade_device():
    device_id = request.values.get('device_id')
    session_id = request.values.get('session_id')
    account_id = request.values.get('account_id')

    ubus_cd(session_id, account_id, ["upgrade", "start", {}], '&device_id=%s' % device_id)
    ubus_cd(session_id, account_id, ["upgrade", "get_progress", {}], '&device_id=%s' % device_id)

    session['device_id'] = device_id
    session['session_id'] = session_id
    session['account_id'] = account_id
    session['info_message'] = '矿机已安排升级'
    return render_admin_device()

def async_reboot_device_all(user):
    accounts_key = 'accounts:%s' % user.get('username')
    for acct in r_session.smembers(accounts_key):
        account_key = 'account:%s:%s' % (user.get('username'), acct.decode("utf-8"))
        account_data_key = account_key + ':data'
        account_data_value = r_session.get(account_data_key)
        account_info = json.loads(r_session.get(account_key).decode("utf-8"))
        if account_data_value is not None:
            data = json.loads(account_data_value.decode("utf-8"))
            if 'device_info' in data.keys():
                for device in data['device_info']:
                    if device['status'] == 'offline':
                        continue
                    session_id = account_info['session_id']
                    device_id = device['device_id']
                    account_id = device['account_id']
                    ubus_cd(session_id, account_id, ["mnt", "reboot", {}], '&device_id=%s' % device_id)
                    time.sleep(5)
    
# 一键重启全部设备按钮
@app.route('/reboot_device_all', methods=['POST'])
@requires_auth
def reboot_device_all():
    user = session.get('user_info')
    threading.Thread(target=async_reboot_device_all, args=(user,)).start()
    session['info_message']='已经安排所有可升级设备重启，请至少等待（5*账号数）秒后，检查重启状态'
    return redirect(url_for('excavators'))

# 重启设备按钮
@app.route('/reboot_device', methods=['POST'])
@requires_auth
def reboot_device():
    device_id = request.values.get('device_id')
    session_id = request.values.get('session_id')
    account_id = request.values.get('account_id')

    ubus_cd(session_id, account_id, ["mnt", "reboot", {}], '&device_id=%s' % device_id)

    session['device_id'] = device_id
    session['session_id'] = session_id
    session['account_id'] = account_id
    session['info_message'] = '矿机已安排重启'
    return render_admin_device()

# 设置挖矿计划
@app.route('/set_device_schedule', methods=['POST'])
@requires_auth
def set_device_schedule():
    device_id = request.values.get('device_id')
    session_id = request.values.get('session_id')
    account_id = request.values.get('account_id')

    schedule_text = request.values.get('schedule_text')
    schedules = schedule_text.replace('\r','\n').replace(' ','')
    listall = schedules.split('\n')
    list_valid=[]
    session['error_message']=''
    session['action']='pattern'
    try:
        for item in listall:
            nodes=item.split(',')
            if len(nodes) >= 2:
                time_span=nodes[0].split('-')
                if len(time_span) <= 1:
                    continue
                time_from = int(time_span[0])
                time_to = int(time_span[1])
                if time_from >= time_to or time_to > 24:
                    continue
                schedule={'from' : time_from, 'to' : time_to}
                params={}
                if nodes[1] == '全速':
                    schedule['type']='unlimit'
                elif nodes[1] == '智能':
                    schedule['type']='automatic'
                elif nodes[1] == '限速':
                    schedule['type']='manual'
                    if len(nodes) >= 3:
                        speed_limits=nodes[2].split('-')
                        if len(speed_limits) <= 1:
                            continue
                        download_limit = int(speed_limits[0])
                        upload_limit = int(speed_limits[1])
                        params['download_speed']=download_limit
                        params['upload_speed']=upload_limit
                else:
                    continue
                schedule['params']=params
                list_valid.append(schedule)
    except ValueError:
        session['error_message'] = session['error_message'] + session['error_message'] + '日程格式错误，数字必须为整数。'

    schedule_param={"hours":list_valid}
    ubus_cd(session_id, account_id, ["xqos", "set_schedule", schedule_param], '&device_id=%s' % device_id)
    session['info_message']='矿机计划设置已提交'
    session['device_id'] = device_id
    session['session_id'] = session_id
    session['account_id'] = account_id
    return render_admin_device()

# 恢复出厂设置设备按钮
@app.route('/reset_device', methods=['POST'])
@requires_auth
def reset_device():
    device_id = request.values.get('device_id')
    session_id = request.values.get('session_id')
    account_id = request.values.get('account_id')

    ubus_cd(session_id, account_id, ["mnt", "reset", {}], '&device_id=%s' % device_id)

    session['device_id'] = device_id
    session['session_id'] = session_id
    session['account_id'] = account_id
    session['info_message']='设备已恢复出厂设置'
    return render_admin_device()

def async_enable_upnp_all(user):
    accounts_key = 'accounts:%s' % user.get('username')
    for acct in r_session.smembers(accounts_key):
        account_key = 'account:%s:%s' % (user.get('username'), acct.decode("utf-8"))
        account_data_key = account_key + ':data'
        account_data_value = r_session.get(account_data_key)
        account_info = json.loads(r_session.get(account_key).decode("utf-8"))
        if account_data_value is not None:
            data = json.loads(account_data_value.decode("utf-8"))
            if 'device_info' in data.keys():
                for device in data['device_info']:
                    if device['status'] == 'offline':
                        continue
                    session_id = account_info['session_id']
                    device_id = device['device_id']
                    account_id = device['account_id']
                    ubus_cd(session_id, account_id, ["dcdn","set_upnp",{"enabled":True}], '&device_id=%s' % device_id)
                    time.sleep(5)
    
# 一键开启全部设备UPNP
@app.route('/enable_upnp_all', methods=['POST'])
@requires_auth
def enable_upnp_all():
    user = session.get('user_info')
    threading.Thread(target=async_enable_upnp_all, args=(user,)).start()
    session['info_message']='已经安排设备开启UPNP，请至少等待（5*账号数）秒后，检查状态'
    return redirect(url_for('excavators'))

# UPNP开启按钮
@app.route('/enable_upnp', methods=['POST'])
@requires_auth
def enable_upnp():
    device_id = request.values.get('device_id')
    session_id = request.values.get('session_id')
    account_id = request.values.get('account_id')
    session['action']='pattern'

    ubus_cd(session_id, account_id, ["dcdn","set_upnp",{"enabled":True}], '&device_id=%s' % device_id)

    session['device_id'] = device_id
    session['session_id'] = session_id
    session['account_id'] = account_id
    session['info_message']='设备已开启UPNP'
    return render_admin_device()

def async_disable_upnp_all(user):
    accounts_key = 'accounts:%s' % user.get('username')
    for acct in r_session.smembers(accounts_key):
        account_key = 'account:%s:%s' % (user.get('username'), acct.decode("utf-8"))
        account_data_key = account_key + ':data'
        account_data_value = r_session.get(account_data_key)
        account_info = json.loads(r_session.get(account_key).decode("utf-8"))
        if account_data_value is not None:
            data = json.loads(account_data_value.decode("utf-8"))
            if 'device_info' in data.keys():
                for device in data['device_info']:
                    if device['status'] == 'offline':
                        continue
                    session_id = account_info['session_id']
                    device_id = device['device_id']
                    account_id = device['account_id']
                    ubus_cd(session_id, account_id, ["dcdn","set_upnp",{"enabled":False}], '&device_id=%s' % device_id)
                    time.sleep(5)
    
# 一键禁用全部设备UPNP
@app.route('/disable_upnp_all', methods=['POST'])
@requires_auth
def disable_upnp_all():
    user = session.get('user_info')
    threading.Thread(target=async_disable_upnp_all, args=(user,)).start()
    session['info_message']='已经安排所有设备禁用UPNP，请至少等待（5*账号数）秒后，检查状态'
    return redirect(url_for('excavators'))

# UPNP关闭按钮
@app.route('/disable_upnp', methods=['POST'])
@requires_auth
def disable_upnp():
    device_id = request.values.get('device_id')
    session_id = request.values.get('session_id')
    account_id = request.values.get('account_id')
    session['action']='pattern'

    ubus_cd(session_id, account_id, ["dcdn","set_upnp",{"enabled":False}], '&device_id=%s' % device_id)

    session['device_id'] = device_id
    session['session_id'] = session_id
    session['account_id'] = account_id
    session['info_message']='设备已关闭UPNP'
    return render_admin_device()

def async_umount_disk_all(user):
    accounts_key = 'accounts:%s' % user.get('username')
    for acct in r_session.smembers(accounts_key):
        account_key = 'account:%s:%s' % (user.get('username'), acct.decode("utf-8"))
        account_data_key = account_key + ':data'
        account_data_value = r_session.get(account_data_key)
        account_info = json.loads(r_session.get(account_key).decode("utf-8"))
        if account_data_value is not None:
            data = json.loads(account_data_value.decode("utf-8"))
            if 'device_info' in data.keys():
                for device in data['device_info']:
                    if device['status'] == 'offline':
                        continue
                    session_id = account_info['session_id']
                    device_id = device['device_id']
                    account_id = device['account_id']
                    ubus_cd(session_id, account_id, ["mnt", "umount_usb", {}], '&device_id=%s' % device_id)
                    time.sleep(5)
    
# 一键弹出全部磁盘
@app.route('/umount_disk_all', methods=['POST'])
@requires_auth
def umount_disk_all():
    user = session.get('user_info')
    threading.Thread(target=async_umount_disk_all, args=(user,)).start()
    session['info_message']='已经安排所有设备弹出磁盘，请至少等待（5*账号数）秒后，检查状态'
    return redirect(url_for('excavators'))

# 弹出磁盘按钮
@app.route('/umount_disk', methods=['POST'])
@requires_auth
def umount_disk():
    device_id = request.values.get('device_id')
    session_id = request.values.get('session_id')
    account_id = request.values.get('account_id')
    session['action']='pattern'

    ubus_cd(session_id, account_id, ["mnt", "umount_usb", {}], '&device_id=%s' % device_id)

    session['device_id'] = device_id
    session['session_id'] = session_id
    session['account_id'] = account_id
    session['info_message']='设备已开启UPNP'
    return render_admin_device()

# 定位设备按钮
@app.route('/noblink_device', methods=['POST'])
@requires_auth
def noblink_device():
    device_id = request.values.get('device_id')
    session_id = request.values.get('session_id')
    account_id = request.values.get('account_id')

    threading.Thread(target=noblink_device_process, args=(device_id, session_id, account_id)).start()

    session['device_id'] = device_id
    session['session_id'] = session_id
    session['account_id'] = account_id
    session['info_message'] = '定位命令已下发，设备指示灯将闪烁40秒'
    return render_admin_device()

def noblink_device_process(device_id, session_id, account_id):
    for i in range(20):# 循环20次
        ubus_cd(session_id, account_id, ["mnt", "noblink", {}], '&device_id=%s' % device_id)#闪
        time.sleep(2)
        ubus_cd(session_id, account_id, ["mnt", "blink", {}], '&device_id=%s' % device_id)#不闪

# 设置设备名称
@app.route('/set_device_name', methods=['POST'])
@requires_auth
def set_device_name():
    device_id = request.values.get('device_id')
    session_id = request.values.get('session_id')
    account_id = request.values.get('account_id')
    new_name = request.values.get('new_name')

    ubus_cd(session_id, account_id, ["server", "set_device_name", {"device_name": new_name, "device_id": device_id}])

    return json.dumps(dict(status='success'))


# 计算设备ROOT密码
# ROOT技术提供：掌柜
# 显著位置
# http://www.renyiai.com
# 显著位置
@app.route('/admin_root', methods=['POST'])
@requires_auth
def admin_root():
    import hashlib
    import base64
    user = session.get('user_info')
    user_key = '%s:%s' % ('user', user.get('username'))
    user_info = json.loads(r_session.get(user_key).decode('utf-8'))
    action = None
    if session.get('action') is not None:
        action = session.get('action')
        session['action'] = None
    if True or 'root_no' in user_info.keys() and user_info['root_no'] != 0:
        user_info['root_no'] = 0
        device_id = request.values.get('device_id')
        session_id = request.values.get('session_id')
        account_id = request.values.get('account_id')
        dev = ubus_cd(session_id, account_id, ["server", "get_device", {"device_id": device_id}])
        if dev is not None:
            if 'result' in dev.keys():
                sn=dev['result'][1]['device_sn']
                mac=dev['result'][1]['mac_address']
                key='%s%s%s'%(sn,mac,'i8e%Fvj24nz024@d!c')
                m=hashlib.md5()
                m.update(key.encode('utf-8'))
                md5=m.digest()
                passwd=base64.b64encode(md5).decode('utf-8')
                passwd=passwd[0:8]
                passwd=passwd.replace('+','-')
                passwd=passwd.replace('/','_')
                if 'root_passwd' not in user_info.keys():
                    user_info['root_passwd']={}
                user_info['root_passwd'][device_id]=passwd
                user_info['root_no']=user_info['root_no'] - 0
                r_session.set(user_key, json.dumps(user_info))
            else:
                session['error_message']='获取ROOT所需信息失败'
        else:
            session['error_message']='请选择一个需要ROOT密码的设备'
        return redirect(url_for('excavators'))
    session['error_message']='您的账户没有ROOT机会了，请联系管理员获取。'
    return redirect(url_for('excavators'))

# 渲染设备页面
def render_admin_device():
    user = session.get('user_info')

    err_msg = None
    if session.get('error_message') is not None:
        err_msg = session.get('error_message')
        session['error_message'] = None

    info_msg = None
    if session.get('info_message') is not None:
        info_msg = session.get('info_message')
        session['info_message'] = None
    action = None
    if session.get('action') is not None:
        action = session.get('action')
        session['action'] = None
    if session.get('device_id') is not None:
        device_id = session.get('device_id')
        session['device_id'] = None
    if session.get('session_id') is not None:
        session_id = session.get('session_id')
        session['session_id'] = None
    if session.get('account_id') is not None:
        account_id = session.get('account_id')
        session['account_id'] = None

    dev = ubus_cd(session_id, account_id, ["server", "get_device", {"device_id": device_id}])
    #return json.dumps(dev)
    schedule_text=''
    for schedule in dev['result'][1]['schedule_hours']:
        schedule_text = '%s%s-%s' % (schedule_text,schedule['from'],schedule['to'])
        if schedule['type']=='unlimit':
            schedule_text = '%s,%s\r\n' % (schedule_text,'全速')
        elif schedule['type']=='automatic':
            schedule_text = '%s,%s\r\n' % (schedule_text,'智能')
        else:
            schedule_text = '%s,%s,%s-%s\r\n' % (schedule_text,'限速',schedule['params']['download_speed'],schedule['params']['upload_speed'])
    return render_template('excavators_info.html', err_msg=err_msg, info_msg=info_msg, action=action, device_id=device_id, session_id=session_id, account_id=account_id, dev=dev,schedule_text=schedule_text)

# 加载设备页面
@app.route('/admin_device', methods=['POST'])
@requires_auth
def admin_device():
    user = session.get('user_info')

    session['device_id'] = request.values.get('device_id')
    session['session_id'] = request.values.get('session_id')
    session['account_id'] = request.values.get('account_id')

    return render_admin_device()
