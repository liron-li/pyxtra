# pyxtra
xtrabackup 备份还原自动化脚本


##### 使用说明：
- ```chmod a+x pyxtra.py```
- 使用root用户执行，否则请确保对相关目录有读写执行权限
- 将备份还原到远程，需开启服务免密登录
- 需安装 rsync

##### eg:
- 全量备份
    
 ```./pyxtra.py backup --type=base --user=USER --password=PASSWORD```
- 增量备份

```./pyxtra.py backup --type=incr --user=USER --password=PASSWORD```
- 准备备份
    
```./pyxtra.py prepare --user=USER --password=PASSWORD```
- 还原备份到远程
    
```./pyxtra.py restore --target_user=USER --target_host=TARGET_HOST```
- 还原备份到本地
    
```./pyxtra.py restore --local=1```

- xtrabackup文档：https://www.percona.com/doc/percona-xtrabackup/LATEST/index.html