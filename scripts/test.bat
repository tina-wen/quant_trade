@echo off
REM 禁止生成Python的.pyc缓存文件
set PYTHONDONTWRITEBYTECODE=1

REM 设置用户参数
set usr_name=demo
set init_fund=1000000
set open_code=CU1911
set n_shares=1

REM 数据读取相关配置
set open_col=open
set close_col=close
set strategy=dma

REM 创建日志目录（Windows路径需用反斜杠）
set log_path=logs\%usr_name%\%open_code%_%strategy%
mkdir "%log_path%" 2>nul || echo 目录已存在或创建失败

REM 执行Python回测脚本（注意Windows用^转义特殊字符）
python backtest_exec.py ^
    --usr_name %usr_name% ^
    --init_fund %init_fund% ^
    --code %open_code% ^
    --shares %n_shares% ^
    --start_time 2018-12-15 ^
    --source %close_col% ^
    --end_time 2019-06-16 ^
    --log_dir %log_path% ^
    --trade_strategy %strategy% ^
    --stop_loss 0.1

pause  REM 执行完毕后暂停（调试时可去掉）
