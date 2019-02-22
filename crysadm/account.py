# 迅雷帐号绑定html页面
__author__ = 'powergx'
from flask import request, Response, render_template, session, url_for, redirect
from crysadm import app, r_session
from auth import requires_admin, requires_auth
import json
import time
import threading
from util import md5
from login import login
from datetime import datetime ,timedelta

# 显示所有绑定的迅雷会员帐号
@app.route('/accounts')
@requires_auth
def accounts():
    user = session.get('user_info')
    err_msg = None
    if session.get('error_message') is not None:
        err_msg = session.get('error_message')
        session['error_message'] = None
    info_msg = None
    if session.get('info_message') is not None:
        info_msg = session.get('info_message')
        session['info_message'] = None
    if session.get('action') is not None:
        action = session.get('action')
        session['action'] = None
    else:
        action='one'

    accounts_key = 'accounts:%s' % user.get('username')

    account_s = list()
    for acct in sorted(r_session.smembers(accounts_key)):
        account_key = 'account:%s:%s' % (user.get('username'), acct.decode("utf-8"))
        account_info = json.loads(r_session.get(account_key).decode("utf-8"))
        account_info_show = {}
        account_info_show['account_name']=account_info.get('account_name')
        account_info_show['username']=account_info.get('username')
        if account_info.get('username') is None:
            account_info_show['username']=''
        else:
            account_info_show['username']=account_info.get('username')
        account_info_show['user_id']=account_info.get('user_id')
        if account_info.get('remark_name') is None:
            account_info['remark_name'] = ''
        account_info_show['remark_name']='''
<form id="form_''' + account_info_show['user_id'] + '''" role="form" action="/account/set_remark_name" method="post">
    <input type="hidden" name="user_id" value="''' + account_info_show['user_id'] + '''" />
    <input placeholder="备注名" name="remark_name" autocomplete="off" type="text" value=\'''' + account_info.get('remark_name') + '''' onchange="submitRemarkName($('#form_''' + account_info_show['user_id'] + ''''));">
</form>
    '''
        account_info_show['status']=account_info.get('status')
        account_info_show['createdtime']=account_info.get('createdtime')
        account_info_show['operation']='''
<form style="float:left;margin-right: 10px;" role="form" action="/account/del/''' + account_info_show['user_id'] + '''" method="post">
    <button type="submit" onclick="javascript:return confirm('确认要删除此账号?')"  class="btn btn-outline btn-danger btn-xs">删除</button>
</form>
    '''
        if account_info.get('active'):
            account_info_show['active'] = 'O'
            account_info_show['operation']=account_info_show['operation']+'''
<form style="float:left;" role="form" action="/account/inactive/''' + account_info_show['user_id'] + '''" method="post">
    <button type="submit" class="btn btn-outline btn-default btn-xs">停止</button>
</form>
    '''
        else:
            account_info_show['active'] = 'X'
            account_info_show['operation']=account_info_show['operation']+'''
        <form style="float:left;" role="form" action="/account/active/''' + account_info_show['user_id'] + '''" method="post">
            <button type="submit" class="btn btn-outline btn-success btn-xs">启用</button>
        </form>
    '''
        account_s.append(account_info_show)

    return render_template('accounts.html', error_message=err_msg, info_message=info_msg, accounts=account_s ,action=action)

def async_account_addmore(list_valid,user):
    for item in list_valid:
        account_name = item[0]
        password = item[1]
        md5_password = md5(password)
        accounts_key = 'accounts:%s' % user.get('username')

        user_key = '%s:%s' % ('user', user.get('username'))
        user_info = json.loads(r_session.get(user_key).decode('utf-8'))
        account_no = r_session.scard(accounts_key) + 1
        if user_info.get('account_limit') is not None and user_info['account_limit'] < account_no:
            session['error_message']='账户数量已达上限，无法完成添加'
            return redirect(url_for('accounts'))
        if account_no is not None:
            if account_no >= user.get('total_account_point'):
                session['error_message']='账户余额不足，无法完成添加'
                return redirect(url_for('accounts'))
            elif account_no >= user.get('max_account_no'):
                user_info['max_account_no'] = account_no
                days=int(user_info.get('total_account_point')/user_info.get('max_account_no'))
                if days<36500:
                    user_info['expire_date'] = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
                else:
                    user_info['expire_date'] = (datetime.now() + timedelta(days=36500)).strftime('%Y-%m-%d')
                r_session.set(user_key, json.dumps(user_info))
        login_result = login(account_name, md5_password, app.config.get('ENCRYPT_PWD_URL'))
        time.sleep(2)
        if login_result.get('errorCode') != 0:
            continue

        xl_session_id = login_result.get('sessionID')
        xl_nick_name = login_result.get('nickName')
        xl_user_name = login_result.get('userName')
        xl_user_id = str(login_result.get('userID'))
        xl_user_new_no = str(login_result.get('userNewNo'))
        xl_account_name = account_name
        xl_password = md5_password
    
        r_session.sadd(accounts_key, xl_user_id)
    
        account_key = 'account:%s:%s' % (user.get('username'), xl_user_id)
        xl_account_data = dict(session_id=xl_session_id, nick_name=xl_nick_name, username=xl_user_name,
                               user_id=xl_user_id, user_new_no=xl_user_new_no, account_name=xl_account_name,
                               password=xl_password, active=True, status='OK',
                               createdtime=datetime.now().strftime('%Y-%m-%d %H:%M'))
        r_session.set(account_key, json.dumps(xl_account_data))
    
# 绑定一堆新的迅雷会员帐号
@app.route('/account/addmore', methods=['POST'])
@requires_auth
def account_addmore():
    accounts = request.values.get('accounts')
    accounts = accounts.replace('\r','\n')
    listall = accounts.split('\n')
    list_valid=[]
    err_msg=''
    session['action']='more'
    for item in listall:
        if len(item) > 2 and item.find('|') != -1:
            pair=item.split('|')
            if len(pair) == 2:
                list_valid.append(pair)
            else:
                err_msg = err_msg + '账户:%s，格式错误<br />' % pair[0]
    if err_msg=='':
        user = session.get('user_info')
        session['error_message']=None
        session['info_message']='已经在后台添加所有账户，请稍后检查添加结果'
        threading.Thread(target=async_account_addmore, args=(list_valid,user,)).start()
    else:
        session['error_message']=err_msg
    return redirect(url_for('accounts'))    

# 绑定一个新的迅雷会员帐号
@app.route('/account/add', methods=['POST'])
@requires_auth
def account_add():
    session['action']='one'

    account_name = request.values.get('xl_username')
    password = request.values.get('xl_password')
    md5_password = md5(password)

    user = session.get('user_info')

    accounts_key = 'accounts:%s' % user.get('username')

    user_key = '%s:%s' % ('user', user.get('username'))
    user_info = json.loads(r_session.get(user_key).decode('utf-8'))
    account_no = r_session.scard(accounts_key) + 1
    if user_info.get('account_limit') is not None and user_info['account_limit'] < account_no:
        session['error_message']='账户数量已达上限，无法完成添加'
        return redirect(url_for('accounts'))
    if account_no is not None:
        if account_no >= user_info.get('total_account_point'):
            session['error_message']='账户余额不足，无法完成添加'
            return redirect(url_for('accounts'))
        elif account_no >= user_info.get('max_account_no'):
            user_info['max_account_no'] = account_no
            days=int(user_info.get('total_account_point') / user_info.get('max_account_no'))
            if days<36500:
                user_info['expire_date'] = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
            else:
                user_info['expire_date'] = (datetime.now() + timedelta(days=36500)).strftime('%Y-%m-%d')
            r_session.set(user_key, json.dumps(user_info))

    login_result = login(account_name, md5_password, app.config.get('ENCRYPT_PWD_URL'))
    if login_result.get('errorCode') != 0:
        error_message = login_result.get('errorDesc')
        session['error_message'] = '登陆失败，错误信息：%s。' % error_message
        return redirect(url_for('accounts'))

    xl_session_id = login_result.get('sessionID')
    xl_nick_name = login_result.get('nickName')
    xl_user_name = login_result.get('userName')
    xl_user_id = str(login_result.get('userID'))
    xl_user_new_no = str(login_result.get('userNewNo'))
    xl_account_name = account_name
    xl_password = md5_password

    r_session.sadd(accounts_key, xl_user_id)

    account_key = 'account:%s:%s' % (user.get('username'), xl_user_id)
    xl_account_data = dict(session_id=xl_session_id, nick_name=xl_nick_name, username=xl_user_name,
                           user_id=xl_user_id, user_new_no=xl_user_new_no, account_name=xl_account_name,
                           password=xl_password, active=True, status='OK',
                           createdtime=datetime.now().strftime('%Y-%m-%d %H:%M'))
    r_session.set(account_key, json.dumps(xl_account_data))

    return redirect(url_for('accounts'))

# 删除绑定的迅雷会员帐号
@app.route('/account/del/<xl_id>', methods=['POST'])
@requires_auth
def account_del(xl_id):
    user = session.get('user_info')
    accounts_key = 'accounts:%s' % user.get('username')
    account_key = 'account:%s:%s' % (user.get('username'), xl_id)
    account_data_key = account_key+':data'
    r_session.srem(accounts_key, xl_id)
    r_session.delete(account_key)
    r_session.delete(account_data_key)
    user_key = '%s:%s' % ('user', user.get('username'))
    user_info = json.loads(r_session.get(user_key).decode('utf-8'))
    account_no = r_session.scard(accounts_key)
    if account_no is not None:
        if account_no > 0:
            days=int(user_info.get('total_account_point')/account_no)
            if days<36500:
                user_info['expire_date'] = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
            else:
                user_info['expire_date'] = (datetime.now() + timedelta(days=36500)).strftime('%Y-%m-%d')
        r_session.set(user_key, json.dumps(user_info))
    return redirect(url_for('accounts'))

# 停止一个已经绑定的迅雷会员帐号
@app.route('/account/inactive/<xl_id>', methods=['POST'])
@requires_auth
def account_inactive(xl_id):
    user = session.get('user_info')

    account_key = 'account:%s:%s' % (user.get('username'), xl_id)
    account_info = json.loads(r_session.get(account_key).decode("utf-8"))
    account_info['active'] = False
    r_session.set(account_key, json.dumps(account_info))

    return redirect(url_for('accounts'))

# 激活一个已经停止的迅雷会员帐号
@app.route('/account/active/<xl_id>', methods=['POST'])
@requires_auth
def account_activel(xl_id):
    user = session.get('user_info')

    account_key = 'account:%s:%s' % (user.get('username'), xl_id)
    account_info = json.loads(r_session.get(account_key).decode("utf-8"))
    account_info['active'] = True
    r_session.set(account_key, json.dumps(account_info))

    return redirect(url_for('accounts'))

# 停止所有已经绑定的迅雷会员帐号
@app.route('/accounts/inactive_all', methods=['POST'])
@requires_auth
def account_inactive_all():
    user = session.get('user_info')

    accounts_key = 'accounts:%s' % user.get('username')
    for acct in sorted(r_session.smembers(accounts_key)):
        account_key = 'account:%s:%s' % (user.get('username'), acct.decode("utf-8"))
        account_info = json.loads(r_session.get(account_key).decode("utf-8"))
        account_info['active'] = False
        r_session.set(account_key, json.dumps(account_info))

    return redirect(url_for('accounts'))

# 激活所有已经停止的迅雷会员帐号
@app.route('/accounts/active_all', methods=['POST'])
@requires_auth
def account_activel_all():
    user = session.get('user_info')

    accounts_key = 'accounts:%s' % user.get('username')
    for acct in sorted(r_session.smembers(accounts_key)):
        account_key = 'account:%s:%s' % (user.get('username'), acct.decode("utf-8"))
        account_info = json.loads(r_session.get(account_key).decode("utf-8"))
        account_info['active'] = True
        r_session.set(account_key, json.dumps(account_info))

    return redirect(url_for('accounts'))

# 设置备注名
@app.route('/account/set_remark_name', methods=['POST'])
@requires_auth
def account_set_remark_name():
    user_id = request.values.get('user_id')
    remark_name = request.values.get('remark_name')
    user = session.get('user_info')
    account_key = 'account:%s:%s' % (user.get('username'), user_id)
    account_info = json.loads(r_session.get(account_key).decode("utf-8"))
    account_info['remark_name'] = remark_name
    r_session.set(account_key, json.dumps(account_info))
    r_session.delete('id_map:%s' % user.get('username'))
    return 'success'
