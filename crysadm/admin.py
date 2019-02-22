# Html － Crysadm 管理员界面
__author__ = 'powergx'
from flask import request, Response, render_template, session, url_for, redirect
from crysadm import app, r_session
from auth import requires_admin, requires_auth
import json
from util import hash_password
import uuid
from datetime import datetime, timedelta
import re
import random
from message import send_msg

# 系统管理 => 用户管理
@app.route('/admin/user')
@requires_admin
def admin_user():
    user_filter = ''
    if session.get('user_filter') is not None:
        user_filter = session.get('user_filter')
        session['user_filter'] = None

    err_msg = None
    if session.get('error_message') is not None:
        err_msg = session.get('error_message')
        session['error_message'] = None

    info_msg = None
    if session.get('info_message') is not None:
        info_msg = session.get('info_message')
        session['info_message'] = None

    users = set()

    for b_user in r_session.mget(*['user:%s' % name.decode('utf-8') for name in sorted(r_session.smembers('users'))]):
        if b_user is None:
            continue
        user = json.loads(b_user.decode('utf-8'))
        user['is_online'] = r_session.exists('user:%s:is_online' % user.get('username')) # 临时寄存数据
        user_show={}
        user_show['username'] = user.get('username')
        if user.get('email') is None:
            user['email']=''
        user_show['email'] = user.get('email')
        user_show['created_time'] = user.get('created_time')
        if user.get('expire_date') is None:
            user['expire_date']=''
        user_show['expire_date'] = user.get('expire_date')
        if user.get('login_time') is None:
            user['login_time']=''
        user_show['login_time'] = user.get('login_time')
        if user.get('max_account_no') is None:
            user['max_account_no']=''
        user_show['max_account_no'] = user.get('max_account_no')
        if user['is_online']:
            user_show['is_online'] = '<span class="label label-info">在线</span>'
        else:
            user_show['is_online'] = '<span class="label label-danger">离线</span>'
        if user['active']:
            user_show['active'] = 'O'
        else:
            user_show['active'] = 'X'
        if user.get('is_admin'):
            user_show['is_admin']='O'
        else:
            user_show['is_admin']='X'
        user_show['collector']='''
<div class="btn-group">
    <div style="display: inline-block">
        <button aria-expanded="false" data-toggle="dropdown" class="btn ''' + ('btn-warning' if user.get('collector')==None else 'btn-info') + ''' btn-xs dropdown-toggle">
            ''' + ('未配置' if user.get('collector')==None else user.get('collector')) + '''<span class="caret"></span>
        </button>
        <ul class="dropdown-menu">
    '''
        for server in r_session.smembers('collector_working'):
            server=server.decode('utf-8')
            user_show['collector']=user_show['collector'] + '''
            <li>
                <form style="margin:5px 5px 0px 5px" role="form" action="/admin/change_property/collector/''' + server + '/' + user['username'] + '''" method="post">
                    <button type="submit" class="btn btn-outline btn-primary btn-block">''' + server + '''</button>
                </form>
            </li>
    '''
        user_show['collector']=user_show['collector'] + '''
        </ul>
    </div>
</div>
'''
        user_show['operation']='''
<div style="display: inline-block">
    <a href="/admin_user/''' + user['username'] + '''" class="btn btn-outline btn-default btn-xs">编辑</a>
</div>
<form style="display: inline-block" role="form" action="/admin/login_as/''' + user['username'] + '''" method="post">
    <button type="submit" class="btn btn-outline btn-default btn-xs">登陆</button>
</form>
    '''
        json_user=json.dumps(user_show)
        if user_filter == '':
            users.add(json_user)
            continue
        user_filters=set(user_filter.split())
        users.add(json_user)
        if '在线' in user_filters:
            user_filters.remove('在线')
            if not user['is_online']:
                users.discard(json_user)
        if '离线' in user_filters:
            user_filters.remove('离线')
            if user['is_online']:
                users.discard(json_user)
        if '禁用' in user_filters:
            user_filters.remove('禁用')
            if user['active']:
                users.discard(json_user)
        if '启用' in user_filters:
            user_filters.remove('启用')
            if not user['active']:
                users.discard(json_user)
        if '快过期' in user_filters:
            user_filters.remove('快过期')
            if user['expire_date'] != '' and datetime.strptime(user['expire_date'],'%Y-%m-%d').date() > (datetime.now() + timedelta(days=7)).date():
                users.discard(json_user)
            elif 'is_admin'  in user.keys() and user['is_admin']:
                users.discard(json_user)
        if '已过期' in user_filters:
            user_filters.remove('已过期')
            if user['expire_date'] != '' and datetime.strptime(user['expire_date'],'%Y-%m-%d').date() > datetime.now().date():
                users.discard(json_user)
            elif 'is_admin'  in user.keys() and user['is_admin']:
                users.discard(json_user)
        if '新用户' in user_filters:
            user_filters.remove('新用户')
            if 'created_time' in user.keys() and datetime.strptime(user['created_time'],'%Y-%m-%d %H:%M:%S').date() <= (datetime.now() + timedelta(days=-3)).date():
                users.discard(json_user)
        if '老用户' in user_filters:
            user_filters.remove('老用户')
            if 'created_time' in user.keys() and datetime.strptime(user['created_time'],'%Y-%m-%d %H:%M:%S').date() > (datetime.now() + timedelta(days=-3)).date():
                users.discard(json_user)
        if '无矿机' in user_filters:
            user_filters.remove('无矿机')
            accounts_count = r_session.smembers('accounts:%s' % user.get('username'))
            if accounts_count is not None and len(accounts_count) != 0:
                users.discard(json_user)
        if '未启用矿机' in user_filters:
            user_filters.remove('未启用矿机')
            accounts = r_session.smembers('accounts:%s' % user.get('username'))
            if accounts is not None and len(accounts) != 0:
                has_active_account = False
                for b_xl_account in accounts:
                    xl_account = b_xl_account.decode('utf-8')
                    account = json.loads(r_session.get('account:%s:%s' % (user.get('username'), xl_account)).decode('utf-8'))
                    if account.get('active'):
                        has_active_account = True
                        break
                if has_active_account:
                    users.discard(json_user)
            else:
                users.discard(json_user)
        if user_filters:
            for c in user_filters:
                if json_user.find(c) == -1:
                    users.discard(json_user)
    user_list=list()
    for user in users:
        user_list.append(json.loads(user))
    user_list.sort(key=lambda k: k['username'])
    user_list.sort(key=lambda k: k['is_admin'],reverse=True)
    return render_template('admin_user.html',users=user_list,err_msg=err_msg,info_msg=info_msg,user_filter=user_filter)

# 系统管理 => 通知管理
@app.route('/admin/message')
@requires_admin
def admin_message():
    return render_template('admin_message.html')

# 系统管理 => 邀请管理
@app.route('/admin/invitation')
@requires_admin
def admin_invitation():
    pub_inv_codes = r_session.smembers('public_invitation_codes')

    inv_codes = r_session.smembers('invitation_codes')
    return render_template('admin_invitation.html', inv_codes=inv_codes, public_inv_codes=pub_inv_codes)

# 系统管理 => 邀请管理 => 生成邀请码
@app.route('/generate/inv_code', methods=['POST'])
@requires_admin
def generate_inv_code():
    _chars = "0123456789ABCDEF"
    r_session.smembers('invitation_codes')

    for i in range(0, 30 - r_session.scard('invitation_codes')):
        r_session.sadd('invitation_codes', ''.join(random.sample(_chars, 10)))

    return redirect(url_for('admin_invitation'))

# 系统管理 => 邀请管理 => 生成公开邀请码
@app.route('/generate/pub_inv_code', methods=['POST'])
@requires_admin
def generate_pub_inv_code():
    _chars = "0123456789ABCDEF"
    r_session.smembers('public_invitation_codes')

    for i in range(0, 15 - r_session.scard('public_invitation_codes')):
        key = ''.join(random.sample(_chars, 10))
        r_session.sadd('public_invitation_codes', key)

    return redirect(url_for('admin_invitation'))

# 系统管理 => 充值管理
@app.route('/admin/recharge_cards')
@requires_admin
def recharge_cards():
    err_msg = None
    if session.get('error_message') is not None:
        err_msg = session.get('error_message')
        session['error_message'] = None
    recharge_cards=[]
    for code in r_session.smembers('recharge_card_codes'):
        b_card = r_session.get('recharge_card:%s' % code.decode('utf-8'))
        if b_card is not None:
            card=json.loads(b_card.decode('utf-8'))
            if card.get('status') == '待售':
                card['operation']='''
<form style="display: inline-block" role="form" action="/admin/card_sold/''' + card['code'] + '''" method="post">
    <button type="submit" class="btn btn-outline btn-default btn-xs">售出</button>
</form>
    '''
            elif card.get('status') == '售出':
                card['operation']='''
<form style="display: inline-block" role="form" action="/admin/card_delete/''' + card['code'] + '''" method="post">
    <button type="submit" class="btn btn-outline btn-default btn-xs">销毁</button>
</form>
    '''
            card['code']='卡号:%s'%card['code']
            card['key']='密码:%s'%card['key']
            recharge_cards.append(card)
    used_cards=[]
    for code in r_session.smembers('used_card_codes'):
        b_card = r_session.get('used_card:%s' % code.decode('utf-8'))
        if b_card is not None:
            card=json.loads(b_card.decode('utf-8'))
            used_cards.append(card)
    return render_template('admin_recharge.html',err_msg=err_msg,recharge_cards=recharge_cards,used_cards=used_cards)

# 系统管理 => 邀请管理 => 售出充值卡
@app.route('/admin/card_sold/<code>', methods=['POST'])
@requires_admin
def card_sold(code):
    b_card = r_session.get('recharge_card:%s' % code)
    if b_card is not None:
        card=json.loads(b_card.decode('utf-8'))
        card['status']='售出'
        r_session.set('recharge_card:%s' % code, json.dumps(card))
    return redirect(url_for('recharge_cards'))

# 系统管理 => 邀请管理 => 销毁充值卡
@app.route('/admin/card_delete/<code>', methods=['POST'])
@requires_admin
def card_delete(code):
    r_session.srem('recharge_card_codes',code)
    r_session.delete('recharge_card:%s' % code)
    return redirect(url_for('recharge_cards'))

# 系统管理 => 邀请管理 => 生成充值卡
@app.route('/generate/recharge_cards', methods=['POST'])
@requires_admin
def generate_recharge_cards():
    name = request.values.get('name')
    points = request.values.get('points')
    num = request.values.get('num')
    try:
        if int(num) <= 0:
            session['error_message']='数量填写错误'
            return redirect(url_for('recharge_cards'))
        if int(points) <= 0:
            session['error_message']='点数填写错误'
            return redirect(url_for('recharge_cards'))
        for i in range(0, int(num)):
            _chars = "0123456789ABCDEF"
            card_code=''.join(random.sample(_chars, 16))
            if r_session.sismember('recharge_card_codes',card_code) or  r_session.sismember('used_card_codes',card_code):
                continue
            card={}
            card['key']=''.join(random.sample(_chars, 16))
            card['code']=card_code
            card['points']=int(points)
            card['name']=name
            card['status']='待售'
            r_session.sadd('recharge_card_codes', card_code)
            r_session.set('recharge_card:%s' % card_code, json.dumps(card))
    except Exception as e:
        session['error_message']=e
    return redirect(url_for('recharge_cards'))

# 系统管理 => 用户管理 => 登陆其它用户
@app.route('/admin/login_as/<username>', methods=['POST'])
@requires_admin
def generate_login_as(username):
    user_info = r_session.get('%s:%s' % ('user', username))

    user = json.loads(user_info.decode('utf-8'))
    user['login_as_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if user.get('log_as_body') is not None:
        if len(user.get('log_as_body')) > 0:
            r_session.set('%s:%s' % ('record', username), json.dumps(dict(diary=user.get('log_as_body')))) # 创建新通道,转移原本日记
            user['log_as_body'] = []

    if r_session.get('%s:%s' % ('record', username)) is None:
        r_session.set('%s:%s' % ('record', username), json.dumps(dict(diary=[]))) # 创建缺失的日记

    r_session.set('%s:%s' % ('user', username), json.dumps(user))
    session['admin_user_info'] = session.get('user_info')
    session['user_info'] = user

    return redirect(url_for('dashboard'))

# 系统管理 => 用户管理 => 编辑用户资料
@app.route('/admin_user/<username>')
@requires_admin
def admin_user_management(username):
    err_msg = None
    if session.get('error_message') is not None:
        err_msg = session.get('error_message')
        session['error_message'] = None

    user = json.loads(r_session.get('user:%s' % username).decode('utf-8'))

    return render_template('user_management.html', user=user, err_msg=err_msg)

# 系统管理 => 用户管理 => 编辑用户资料 => 修改密码
@app.route('/admin/change_password/<username>', methods=['POST'])
@requires_admin
def admin_change_password(username):
    n_password = request.values.get('new_password')

    if len(n_password) < 8:
        session['error_message'] = '密码必须8位以上.'
        return redirect(url_for(endpoint='admin_user_management', username=username))

    user_key = '%s:%s' % ('user', username)
    user_info = json.loads(r_session.get(user_key).decode('utf-8'))

    user_info['password'] = hash_password(n_password)
    r_session.set(user_key, json.dumps(user_info))

    return redirect(url_for(endpoint='admin_user_management', username=username))

# 系统管理 => 参数配置 => 重启所有自动任务
@app.route('/admin/restart_auto_task', methods=['POST'])
@requires_admin
def admin_restart_auto_task():
    config_key = '%s:%s' % ('user', 'system')
    config_info = json.loads(r_session.get(config_key).decode('utf-8'))
    config_info['restart_flag'] = True
    r_session.set(config_key, json.dumps(config_info))
    session['action'] = 'auto_task'
    session['error_message'] = '自动任务已经全部安排重启'
    return redirect(url_for('system_config'))

# 系统管理 => 用户管理 => 编辑用户资料 => 修改其它属性
@app.route('/admin/change_property/<field>/<value>/<username>', methods=['POST'])
@requires_admin
def admin_change_property(field, value, username):
    user_key = '%s:%s' % ('user', username)
    user_info = json.loads(r_session.get(user_key).decode('utf-8'))

    if field == 'is_admin':
        user_info['is_admin'] = True if value == '1' else False
    elif field == 'active':
        user_info['active'] = True if value == '1' else False
    elif field == 'collector':
        user_info['collector'] = value
        r_session.set(user_key, json.dumps(user_info))
        return redirect(url_for('admin_user'))
    elif field == 'feedback_user':
        session['action'] = 'info'
        value=str(request.values.get(field))
        if r_session.get('%s:%s' % ('user', value)) is None:
            session['error_message']='该用户不存在'
            return redirect(url_for('system_config'))
        user_info['feedback_user']=value
        r_session.set(user_key, json.dumps(user_info))
        return redirect(url_for('system_config'))
    elif field == 'master_mail_usetls':
        user_info['master_mail_usetls'] = int(value)
        session['action'] = 'info'
        r_session.set(user_key, json.dumps(user_info))
        return redirect(url_for('system_config'))
    elif field.endswith('_interval') or field == 'trial_period':
        try:
            if int(str(request.values.get(field))) >= 1:
                user_info[field] = int(str(request.values.get(field)))
                r_session.set(user_key, json.dumps(user_info))
        except Exception as e:
            session['error_message']=e
        return redirect(url_for('system_config'))
    elif field.find('_mail_') != -1:
        session['action'] = 'info'
        user_info[field] = str(request.values.get(field))
        r_session.set(user_key, json.dumps(user_info))
        return redirect(url_for('system_config'))
    elif field.find('plugin_') != -1:
        session['action'] = 'plugin'
        user_info[field] = str(request.values.get('code'))
        r_session.set(user_key, json.dumps(user_info))
        return redirect(url_for('system_config'))
    r_session.set(user_key, json.dumps(user_info))

    return redirect(url_for(endpoint='admin_user_management', username=username))

# 系统管理 => 用户管理 => 编辑用户资料 => 提示信息
@app.route('/admin/change_user_info/<username>', methods=['POST'])
@requires_admin
def admin_change_user_info(username):
    account_limit = request.values.get('account_limit')
    root_no = request.values.get('root_no')
    total_account_point = request.values.get('total_account_point')
    r = r"^[0-9]\d*$"

    if re.match(r, account_limit) is None:
        session['error_message'] = '迅雷账号限制必须为整数.'
        return redirect(url_for(endpoint='admin_user_management', username=username))

    if re.match(r, total_account_point) is None:
        session['error_message'] = '剩余点数必须为整数.'
        return redirect(url_for(endpoint='admin_user_management', username=username))

    if re.match(r, root_no) is None:
        session['error_message'] = '剩余ROOT次数必须为整数'
        return redirect(url_for(endpoint='admin_user_management', username=username))
    
    if not 0 < int(account_limit) < 1001:
        session['error_message'] = '迅雷账号限制必须为 1~1000.'
        return redirect(url_for(endpoint='admin_user_management', username=username))
    if not 0 <= int(root_no) <= 2000:
        session['error_message'] = '剩余ROOT次数必须为 0~2000.'
        return redirect(url_for(endpoint='admin_user_management', username=username))

    user_key = '%s:%s' % ('user', username)
    user_info = json.loads(r_session.get(user_key).decode('utf-8'))

    user_info['total_account_point'] = int(total_account_point)
    if user_info.get('max_account_no') is not None and user_info.get('max_account_no') > 0:
        days=int(user_info.get('total_account_point')/user_info.get('max_account_no'))
        if days<36500:
            user_info['expire_date'] = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
        else:
            user_info['expire_date'] = (datetime.now() + timedelta(days=36500)).strftime('%Y-%m-%d')
    user_info['root_no'] = int(root_no)
    user_info['account_limit'] = int(account_limit)
    r_session.set(user_key, json.dumps(user_info))

    return redirect(url_for(endpoint='admin_user_management', username=username))

# 系统管理 => 用户管理 => 删除用户
@app.route('/admin/del_user/<username>', methods=['GET'])
@requires_admin
def admin_del_user(username):
    if r_session.get('%s:%s' % ('user', username)) is None:
        session['error_message'] = '账号不存在'
        return redirect(url_for(endpoint='admin_user', username=username))

    # do del user
    r_session.delete('%s:%s' % ('user', username))
    r_session.delete('%s:%s' % ('record', username))
    r_session.delete('%s:%s' % ('extra_info', username))
    r_session.delete('%s:%s' % ('rows', username))
    r_session.delete('%s:%s' % ('payment', username))
    r_session.srem('users', username)
    r_session.srem('email', username)
    for b_account_id in r_session.smembers('accounts:' + username):
        account_id = b_account_id.decode('utf-8')
        r_session.delete('account:%s:%s' % (username, account_id))
        r_session.delete('account:%s:%s:data' % (username, account_id))
    r_session.delete('accounts:' + username)

    for key in r_session.keys('user_data:%s:*' % username):
        r_session.delete(key.decode('utf-8'))

    return redirect(url_for('admin_user'))

def del_user(username):
    # do del user
    r_session.delete('%s:%s' % ('user', username))
    r_session.delete('%s:%s' % ('record', username))
    r_session.delete('%s:%s' % ('extra_info', username))
    r_session.delete('%s:%s' % ('rows', username))
    r_session.delete('%s:%s' % ('payment', username))
    r_session.srem('users', username)
    r_session.srem('email', username)
    for b_account_id in r_session.smembers('accounts:' + username):
        account_id = b_account_id.decode('utf-8')
        r_session.delete('account:%s:%s' % (username, account_id))
        r_session.delete('account:%s:%s:data' % (username, account_id))
    r_session.delete('accounts:' + username)

    for key in r_session.keys('user_data:%s:*' % username):
        r_session.delete(key.decode('utf-8'))

# 系统管理 -> 用户管理 -> 删除筛选
@app.route('/admin/del_filter', methods=['POST'])
@requires_admin
def del_filter():
    usernames = request.values.get('selection').split()
    for username in usernames:
        del_user(username)
    return redirect(url_for('admin_user'))

# 系统管理 -> 用户管理 -> 添加
@app.route('/admin/add_user')
@requires_admin
def add_user():
    err_msg = None
    if session.get('error_message') is not None:
        err_msg = session.get('error_message')
        session['error_message'] = None
    return render_template('admin_register.html',err_msg=err_msg)
    
# 系统管理 -> 用户管理 -> 添加
@app.route('/admin/register_user', methods=['POST'])
@requires_admin
def register_user():
    email = request.values.get('username')
    username = request.values.get('username')
    password = request.values.get('password')
    re_password = request.values.get('re_password')
    r = r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)"
    if re.match(r, email) is None:
        session['error_message'] = '邮箱地址格式不正确.'
        return redirect(url_for('add_user'))
    if username == '':
        session['error_message'] = '账号名不能为空。'
        return redirect(url_for('add_user'))
    if r_session.get('%s:%s' % ('user', username)) is not None:
        session['error_message'] = '该账号名已存在。'
        return redirect(url_for('add_user'))
    if password != re_password:
        session['error_message'] = '密码输入不一致.'
        return redirect(url_for('add_user'))
    if len(password) < 8:
        session['error_message'] = '密码必须8位及以上.'
        return redirect(url_for('add_user'))
    if r_session.sismember('email', email):
        session['error_message'] = '该邮件地址已被注册.'
        return redirect(url_for('add_user'))
    config_key = '%s:%s' % ('user', 'system')
    config_info = json.loads(r_session.get(config_key).decode('utf-8'))
    if 'trial_period' not in config_info.keys():
        config_info['trial_period'] = 14
    user = dict(username=username, password=hash_password(password), id=str(uuid.uuid1()),
                active=True, is_admin=False, max_account_no=1, email=email,total_account_point=config_info['trial_period'],
                created_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    days=int(user.get('total_account_point')/user.get('max_account_no'))
    if days<36500:
        user['expire_date'] = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
    else:
        user['expire_date'] = (datetime.now() + timedelta(days=36500)).strftime('%Y-%m-%d')
    r_session.set('%s:%s' % ('user', user.get('username')), json.dumps(user))
    r_session.set('%s:%s' % ('record', user.get('username')), json.dumps(dict(diary=[])))
    r_session.sadd('users', user.get('username'))
    r_session.sadd('email', user.get('email'))
    session['info_message'] = '注册成功'
    return redirect(url_for('admin_user'))

# 系统管理 -> 用户管理 -> 搜索过滤
@app.route('/admin/user_list_filter', methods=['POST'])
@requires_admin
def user_list_filter():
    session['user_filter'] = request.values.get('user_list_filter')
    return redirect(url_for('admin_user'))

# 系统管理 => 通知管理 => 发送通知
@app.route('/admin/message/send', methods=['POST'])
@requires_admin
def admin_message_send():
    send_type = request.values.get('type')
    to = request.values.get('to')
    subject = request.values.get('subject')
    summary = request.values.get('summary')
    content = request.values.get('content')

    if subject == '':
        session['error_message'] = '标题为必填。'
        return redirect(url_for('admin_message'))

    if to == '':
        session['error_message'] = '收件方必填。'
        return redirect(url_for('admin_message'))

    if summary == '':
        session['error_message'] = '简介必填'
        return redirect(url_for('admin_message'))

    send_content = '{:<30}'.format(summary) + content
    if send_type=='message':
        user = session.get('user_info')
        if to == 'all':
            for b_username in r_session.smembers('users'):
                send_msg(b_username.decode('utf-8'), subject, send_content, 3600 * 24 * 31, user.get('username'))
    
        else:
            send_msg(to, subject, send_content, 3600 * 24 * 31,user.get('username'))
    else:
        from mailsand import send_email
        from mailsand import validateEmail
        to_set=set(to.split(';'))
        to_list=list()
        for email in to_set:
            if validateEmail(email) == 1:
                to_list.append(email)
        config_key = '%s:%s' % ('user', 'system')
        config_info = json.loads(r_session.get(config_key).decode('utf-8'))
        mail = dict()
        mail['to'] = ",".join(to_list)
        mail['subject'] = subject
        mail['text'] = send_content
        if not send_email(mail,config_info):
            session['error_message']='发送失败，请检查邮件配置'
        
    return redirect(url_for(endpoint='admin_message'))

@app.route('/admin/test_email', methods=['POST'])
@requires_admin
def test_email():
    from mailsand import send_email
    from mailsand import validateEmail
    config_key = '%s:%s' % ('user', 'system')
    config_info = json.loads(r_session.get(config_key).decode('utf-8'))

    user = session.get('user_info')
    user_key = '%s:%s' % ('user', user.get('username'))
    user_info = json.loads(r_session.get(user_key).decode('utf-8'))

    session['action'] = 'info'
    if 'email' not in user_info.keys() or not validateEmail(user_info["email"]):
       session['error_message']='该账户的提醒邮件地址设置不正确，无法测试'
       return redirect(url_for('system_config'))
    mail = dict()
    mail['to'] = user_info['email']
    mail['subject'] = '云监工-测试邮件'
    mail['text'] = '这只是一个测试邮件，你更应该关注的不是这里面写了什么。不是么？'
    if not send_email(mail,config_info):
        session['error_message']='发送失败，请检查邮件配置'
    return redirect(url_for('system_config'))


@app.route('/admin/settings')
@requires_admin
def system_config():
    config_key = '%s:%s' % ('user', 'system')
    config_info = json.loads(r_session.get(config_key).decode('utf-8'))

    err_msg = None
    if session.get('error_message') is not None:
        err_msg = session.get('error_message')
        session['error_message'] = None
    action = None
    if session.get('action') is not None:
        action = session.get('action')
        session['action'] = None

    return render_template('admin_settings.html', user_info=config_info, err_msg=err_msg, action=action)

# 站点监控 => 站点记录
@app.route('/guest')
@requires_admin
def admin_guest():
    guest_as = []

    guest_key = 'guest'
    if r_session.get(guest_key) is None:
        r_session.set(guest_key, json.dumps(dict(diary=[])))
    guest_info = json.loads(r_session.get(guest_key).decode('utf-8'))

    for row in guest_info.get('diary'):
        if (datetime.now() - datetime.strptime(row.get('time'), '%Y-%m-%d %H:%M:%S')).days < 2:
            guest_as.append(row)
    guest_as.reverse()

    return render_template('guest.html', guest_as=guest_as)

# 系统管理 => 删除站点记录
@app.route('/guest/delete')
@requires_admin
def admin_guest_delete():

    guest_key = 'guest'
    guest_info = json.loads(r_session.get(guest_key).decode('utf-8'))

    guest_info['diary'] = []

    r_session.set(guest_key, json.dumps(guest_info))

    return redirect(url_for('admin_guest'))

# 站点监控 => 邀请记录
@app.route('/guest/invitation')
@requires_admin
def guest_invitation():
    public_as = []

    public_key = 'invitation'
    if r_session.get(public_key) is None:
        r_session.set(public_key, json.dumps(dict(diary=[])))
    public_info = json.loads(r_session.get(public_key).decode('utf-8'))

    for row in public_info.get('diary'):
        if (datetime.now() - datetime.strptime(row.get('time'), '%Y-%m-%d %H:%M:%S')).days < 7:
            public_as.append(row)
    public_as.reverse()

    return render_template('guest_invitation.html', public_as=public_as)

# 站点监控 => 删除邀请记录
@app.route('/guest/invitation/delete')
@requires_admin
def guest_invitation_delete():

    public_key = 'invitation'
    public_info = json.loads(r_session.get(public_key).decode('utf-8'))

    public_info['diary'] = []

    r_session.set(public_key, json.dumps(public_info))

    return redirect(url_for('guest_invitation'))

@app.route('/debug_ubus', methods=['POST'])
@requires_admin
def admin_debug_ubus():
    from api import ubus_cd
    try:
        session_id=request.values.get('session_id')
        account_id=request.values.get('account_id')
        command=request.values.get('command')
        action=request.values.get('action')
        params=request.values.get('params')
        extra_url=request.values.get('extra_url')
        session['info_message'] = ubus_cd(session_id, account_id, ["%s" % command,"%s" % action,json.loads(params)], extra_url)
        session['ubus_params']={
            'session_id':session_id,
            'account_id':account_id,
            'command':command,
            'action':action,
            'params':params,
            'extra_url':extra_url
        }
    except RuntimeError as e:
        session['error_message'] = json.dumps(e)
    return redirect(url_for('admin_debug'))

@app.route('/debug_api', methods=['POST'])
@requires_admin
def admin_debug_api():
    from api import api_post
    from api import api_get
    try:
        session_id=request.values.get('session_id')
        account_id=request.values.get('account_id')
        url=request.values.get('url')
        method=request.values.get('method')
        params=request.values.get('params')
        cookies = dict(sessionid=session_id, userid=str(account_id))
        if method == 'GET':
            session['info_message'] = api_get(cookies,url,json.loads(params)).decode('utf-8')
        else:
            session['info_message'] = json.dumps(api_post(cookies,url,json.loads(params)))
        session['api_params']={
            'session_id':session_id,
            'account_id':account_id,
            'url':url,
            'method':method,
            'params':params
        }
    except RuntimeError as e:
        session['error_message'] = json.dumps(e)
    return redirect(url_for('admin_debug'))

# 系统管理 => 清除全部账户点数
@app.route('/database/clear_all_points', methods=['POST'])
@requires_admin
def clear_all_points():
    for name in r_session.smembers('users'):
        user_key = '%s:%s' % ('user', name.decode('utf-8'))
        user_info = json.loads(r_session.get(user_key).decode('utf-8'))
        user_info.pop('total_account_point',0)
        r_session.set(user_key,json.dumps(user_info))
    return redirect(url_for('admin_debug'))

# 系统管理 => 配置全部账户点数
@app.route('/database/set_all_points', methods=['POST'])
@requires_admin
def set_all_points():
    from user import account_log
    for name in r_session.smembers('users'):
        user_key = '%s:%s' % ('user', name.decode('utf-8'))
        user_info = json.loads(r_session.get(user_key).decode('utf-8'))
        if 'total_account_point' not in user_info.keys():
            if 'expire_date' not in user_info.keys():
                user_info['total_account_point'] = config_info['trial_period']
            else:
                user_info['total_account_point'] = user_info['max_account_no'] * (datetime.strptime(user_info['expire_date'],'%Y-%m-%d') - datetime.now()).days
                account_log(user_info.get('username'),'充值点数','充值','原账户时长折算点数:%s' % user_info['total_account_point'])
            if user_info.get('max_account_no') is not None and user_info.get('max_account_no') > 0:
                days=int(user_info.get('total_account_point')/user_info.get('max_account_no'))
                if days<36500:
                    user_info['expire_date'] = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
                else:
                    user_info['expire_date'] = (datetime.now() + timedelta(days=36500)).strftime('%Y-%m-%d')
            r_session.set('user:%s' % user_info.get('username'), json.dumps(user_info))
    return redirect(url_for('admin_debug'))

# 系统管理 => 配置最大账户数量限制
@app.route('/database/set_account_limit', methods=['POST'])
@requires_admin
def set_account_limit():
    for name in r_session.smembers('users'):
        user_key = '%s:%s' % ('user', name.decode('utf-8'))
        user_info = json.loads(r_session.get(user_key).decode('utf-8'))
        user_info['account_limit']=user_info['max_account_no']
        r_session.set(user_key,json.dumps(user_info))	
    return redirect(url_for('admin_debug'))

# 系统管理 => 移除最大账户数量限制
@app.route('/database/clear_account_limit', methods=['POST'])
@requires_admin
def clear_account_limit():
    for name in r_session.smembers('users'):
        user_key = '%s:%s' % ('user', name.decode('utf-8'))
        user_info = json.loads(r_session.get(user_key).decode('utf-8'))
        user_info.pop('account_limit',0)
        r_session.set(user_key,json.dumps(user_info))	
    return redirect(url_for('admin_debug'))

# 系统管理 => 接口调试
@app.route('/debug')
@requires_admin
def admin_debug():
    err_msg = None
    if session.get('error_message') is not None:
        err_msg = session.get('error_message')
        session['error_message'] = None
    info_msg = None
    if session.get('info_message') is not None:
        info_msg = session.get('info_message')
        session['info_message'] = None
    ubus_params={}
    if session.get('ubus_params') is not None:
        ubus_params=session.get('ubus_params')
    api_params={}
    if session.get('api_params') is not None:
        api_params=session.get('api_params')
    return render_template('debug.html',err_msg=err_msg,info_msg=info_msg,ubus_params=ubus_params,api_params=api_params)

# 系统管理 => 关于
@app.route('/about')
@requires_admin
def admin_about():
    import platform
    version = '当前版本：2019-02-10'
    return render_template('about.html', platform=platform, version=version)
