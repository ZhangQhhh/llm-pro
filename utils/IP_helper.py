from flask import request

def get_client_ip():
    # 检查 X-Forwarded-For 头
    if request.headers.get('X-Forwarded-For'):
        return request.headers['X-Forwarded-For'].split(',')[0].strip()
    # 检查 X-Real-IP 头
    if request.headers.get('X-Real-IP'):
        return request.headers['X-Real-IP']
    # 默认使用 remote_addr
    return request.remote_addr
