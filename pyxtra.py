#!/usr/bin/env python3

# Author: liron.li <liron.li@outlook.com>.
"""
    使用说明：
        1. chmod a+x pyxtra.py
        2. 使用root用户执行，否则请确保对相关目录有读写执行权限
        3. 将备份还原到远程，需开启服务免密登录
        4. 需安装 rsync
    eg:
        1. 全量备份
            ./pyxtra.py backup --type=base --user=USER --password=PASSWORD
        2. 增量备份
            ./pyxtra.py backup --type=incr --user=USER --password=PASSWORD
        3. 准备备份
            ./pyxtra.py prepare --user=USER --password=PASSWORD
        4. 还原备份到远程
            ./pyxtra.py restore --target_user=USER --target_host=TARGET_HOST
        5. 还原备份到本地
            ./pyxtra.py restore --local=1

    xtrabackup文档：https://www.percona.com/doc/percona-xtrabackup/LATEST/index.html
"""

import os
import subprocess
import argparse
import time

parser = argparse.ArgumentParser()
parser.add_argument('action', help='操作类型 backup|prepare|restore')
parser.add_argument('--type', help='备份类型, base or incr', required=False)
parser.add_argument('--user', help='mysql user', required=False, default='root')
parser.add_argument('--password', help='mysql password', required=False, default='123456')
parser.add_argument('--target_dir', help='备份存储目录', required=False, default='/mysql_bak')
parser.add_argument('--target_user', help='目标服务器用户', required=False)
parser.add_argument('--target_host', help='目标服务器host', required=False)
parser.add_argument('--local', help='是否本地执行', required=False)
args = parser.parse_args()


class Xtrabackup(object):
    # 停止mysql
    MYSQL_STOP_CMD = 'service mysql stop'
    # 重启mysql
    MYSQL_RESTART_CMD = 'service mysql restart'
    # 修改mysql目录权限
    CHOWN_MYSQL_DIR_CMD = 'chown -R mysql:mysql /var/lib/mysql'
    # xtrabackup 备份命令
    BACKUP_CMD = 'xtrabackup --user={} --password={} --backup --target-dir={}'
    # 存放备份的目录
    BACKUP_BASE_DIR = '/mysql_bak'
    # 增量备份命令
    INCR_BACKUP_CMD = 'xtrabackup --user={} --password={} --backup --target-dir={} --incremental-basedir={}'

    def __init__(self, **kwargs):
        self.user = kwargs.get('user')
        self.password = kwargs.get('password')
        self.target_dir = kwargs.get('target_dir')
        self.target_user = kwargs.get('target_user')
        self.target_host = kwargs.get('target_host')

        self.base_log_file = os.path.join(self.target_dir, 'base.log')
        self.incr_log_file = os.path.join(self.target_dir, 'incr.log')

        # 如果base目录不存在则创建
        if not os.path.exists(self.target_dir):
            os.makedirs(self.target_dir)

    def base_backup(self):
        """
        全量备份
        :return:
        """
        target_dir = os.path.join(self.target_dir,
                                  '{}-base'.format(time.strftime('%Y-%m-%d-%H-%M-%S')))
        _cmd = self.BACKUP_CMD.format(self.user, self.password, target_dir)

        exitcode, data = subprocess.getstatusoutput(_cmd)
        if exitcode == 0:
            self.clear_inrc_bak()  # 如果全量备份成功则清除之前的增量备份
            self.backup_log(self.base_log_file, target_dir, '>')
        print(data)

    def clear_inrc_bak(self):
        """
        清空增量备份
        :return:
        """
        subprocess.getstatusoutput('cat {} | xargs rm -rf'.format(self.incr_log_file))
        subprocess.getstatusoutput('cat {} | xargs rm -rf'.format(self.base_log_file))
        subprocess.getstatusoutput('rm -rf {}'.format(self.incr_log_file))

    def inc_backup(self):
        """
        增量备份
        :return:
        """
        target_dir = os.path.join(self.target_dir,
                                  '{}-inc'.format(time.strftime('%Y-%m-%d-%H-%M-%S')))
        basedir = self.choose_incr_basedir()

        _cmd = self.INCR_BACKUP_CMD.format(self.user, self.password, target_dir, basedir)

        exitcode, data = subprocess.getstatusoutput(_cmd)
        print(_cmd)
        if exitcode == 0:
            self.backup_log(self.incr_log_file, target_dir)
        print(data)

    def backup_log(self, file, data, operate='>>'):
        """
        记录备份状态
        :param file:
        :param data:
        :param operate:
        :return:
        """
        data = data.strip()
        if data:
            subprocess.getstatusoutput('echo {} {} {}'.format(data, operate, file))

    def choose_incr_basedir(self):
        """
        选择上一次的备份点
        :return:
        """
        # 先从增量备份记录中取， 如果没有再从全量备份记录取，再没有会报错
        exitcode, data = subprocess.getstatusoutput('tail -n1 {}'.format(self.incr_log_file))
        if exitcode != 0:
            exitcode, data = subprocess.getstatusoutput('tail -n1 {}'.format(self.base_log_file))
            if exitcode != 0:  # 如果没有全量备份则执行全量备份
                self.base_backup()
                return self.choose_incr_basedir()
            else:
                return data.strip()
        else:
            return data.strip()

    def prepare(self):
        """
        准备备份
        :return:
        """
        base_list = self.read_log_to_list(self.base_log_file)
        incr_list = self.read_log_to_list(self.incr_log_file)
        base_bak = ''

        if len(base_list) == 0:
            print('log file is empty!')
            return False

        if len(base_list) > 0:
            base_bak = base_list.pop().strip()
            _cmd = 'xtrabackup --prepare --apply-log-only --target-dir={}'.format(base_bak)
            os.system(_cmd)

        if len(incr_list) > 0 and base_bak:
            end_incr_bak = incr_list.pop()

            for incr_bak in incr_list:
                # 依次将增量备份应用到全量备份中
                _cmd = 'xtrabackup --prepare --apply-log-only --target-dir={} --incremental-dir={}'.format(base_bak,
                                                                                                           incr_bak)
                os.system(_cmd)
            # 最后一个增量备份不需要 --apply-log-only 参数
            os.system('xtrabackup --prepare --target-dir={} --incremental-dir={}'.format(base_bak, end_incr_bak))

    def read_log_to_list(self, path):
        """
        读取文件为list
        :param path:
        :return:
        """
        try:
            with open(path, 'r') as f:
                return f.readlines()
        except IOError:
            return []

    def restore(self):
        """
        将备份还原到指定服务器上
        :return:
        """
        # 准备备份文件
        self.prepare()
        base_dir = self.read_log_to_list(self.base_log_file).pop().strip() + '/'

        if self.target_host and self.target_user:
            # 停止远程的mysql
            os.system('ssh {}@{} "{}"'.format(self.target_user, self.target_host, self.MYSQL_STOP_CMD))
            # 同步备份
            _rsync_cmd = 'rsync -avrP {} {}@{}:/var/lib/mysql'.format(base_dir, self.target_user, self.target_host)
            os.system(_rsync_cmd)
            # 更改目录权限
            os.system('ssh {}@{} "{}"'.format(self.target_user, self.target_host, self.CHOWN_MYSQL_DIR_CMD))
            # 重启mysql
            os.system('ssh {}@{} "{}"'.format(self.target_user, self.target_host, self.MYSQL_RESTART_CMD))
        else:
            # local
            os.system(self.MYSQL_STOP_CMD)
            os.system('rsync -avrP {} /var/lib/mysql'.format(base_dir))
            os.system(self.CHOWN_MYSQL_DIR_CMD)
            os.system(self.MYSQL_RESTART_CMD)


if __name__ == '__main__':
    cmd = Xtrabackup(
        user=args.__dict__.get('user'),
        password=args.__dict__.get('password'),
        target_dir=args.__dict__.get('target_dir'),
        target_host=args.__dict__.get('target_host'),
        target_user=args.__dict__.get('target_user')
    )
    # cmd.inc_backup()
    _action = args.__dict__.get('action')
    if _action == 'backup':
        _type = args.__dict__.get('type', 'base')
        if _type == 'base':
            cmd.base_backup()
        elif _type == 'incr':
            cmd.inc_backup()
        else:
            print('错误: 无效的 type 值')
    elif _action == 'prepare':
        cmd.prepare()
    elif _action == 'restore':
        if args.__dict__.get('local'):
            cmd.restore()
        else:
            if not args.__dict__.get('target_user') or not args.__dict__.get('target_host'):
                print('缺少 target_user target_host 参数')
            else:
                cmd.restore()
    elif _action == 'test':
        cmd.prepare()
    else:
        print('错误: 无效的 action 值')
